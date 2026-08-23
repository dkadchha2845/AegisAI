#!/usr/bin/env python3
"""
AegisAI — turn the raw generated calls into a trainable dataset.

    python build_dataset.py

Produces, in data/processed/:
    train.jsonl / val.jsonl / test.jsonl   utterance-level, for the classifier
    transitions.json                       stage transition matrix, for the twin
    report.md                              class balance and corpus statistics

The one methodological point that matters
-----------------------------------------
Splits are made **by call, never by utterance**. Utterances inside one call
share names, case IDs, amounts, and phrasing tics, so splitting at the
utterance level leaks the test set into training and inflates macro-F1 by a
wide margin. A number produced that way is not a number you can defend to a
judge who asks how you split. Archetypes are stratified across the splits so
each one appears in all three.
"""

from __future__ import annotations

import argparse
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

from aegis.taxonomy import CRITICAL_LABELS, LABELS

HERE = Path(__file__).parent
RAW = HERE / "data" / "raw" / "calls.jsonl"
OUT = HERE / "data" / "processed"


def normalise(text: str) -> str:
    """
    Lowercase and strip punctuation — for near-duplicate detection only.

    Digits are deliberately **kept**. Stripping them collapses "amount daaliye
    450000" and "amount daaliye 250000" into one key, and the de-duplicator
    then deletes most of PAYMENT_EXECUTION — the class the whole demo depends
    on. Numeric variation is signal here, not noise.
    """
    return re.sub(r"[^a-z0-9 ]", "", text.lower()).strip()


def load_calls(path: Path) -> list[dict]:
    calls = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                calls.append(json.loads(line))
    return calls


def split_key(call: dict) -> str:
    """
    The unit that must not straddle a split.

    For paraphrased corpora this is the **gold skeleton**, not the call. Twenty
    variants of one gold call share their sentence structure verbatim -- only
    names, cities and amounts differ -- so splitting them apart puts a
    near-copy of every training sentence into the test set and produces a
    macro-F1 that measures nothing. Grouping by `derived_from` keeps every
    descendant of a skeleton on the same side of the wall.
    """
    return call["seed"].get("derived_from") or call["seed"]["call_id"]


def split_by_call(
    calls: list[dict], n_test_skeletons: int = 8, seed: int = 7
) -> tuple[list, list, list, list[str]]:
    """
    Leave-archetypes-out split. Returns (train, val, test, held_out_skeletons).

    The corpus is 16 hand-written skeletons expanded into variants, and every
    archetype has exactly one skeleton -- so a skeleton cannot be split without
    putting a near-copy of every training sentence into the test set.

    Instead **whole skeletons are held out**. The test set is entire scam types
    the model has never trained on, which measures the thing that actually
    matters: does it recognise coercion, or has it memorised these scripts?
    It is a harder benchmark than a same-archetype split and the only one that
    can be defended when someone asks how the corpus was built.

    Validation is carved from the *training* skeletons' variants. Mild leakage
    is acceptable there -- val only picks the early-stopping epoch, it is never
    reported as a result.
    """
    rng = random.Random(seed)

    groups: dict[str, list[dict]] = defaultdict(list)
    for c in calls:
        groups[split_key(c)].append(c)

    # Hold out a mix of scam and benign skeletons: an all-benign test set would
    # report a flattering number that says nothing about scam detection.
    scam_keys = [k for k, g in groups.items() if g[0]["seed"]["is_scam"]]
    benign_keys = [k for k, g in groups.items() if not g[0]["seed"]["is_scam"]]
    rng.shuffle(scam_keys)
    rng.shuffle(benign_keys)

    n_benign_test = max(1, n_test_skeletons // 4)
    n_scam_test = max(1, n_test_skeletons - n_benign_test)
    held_out = scam_keys[:n_scam_test] + benign_keys[:n_benign_test]

    train_keys = [k for k in groups if k not in set(held_out)]

    test: list[dict] = []
    for k in held_out:
        test += groups[k]

    train: list[dict] = []
    val: list[dict] = []
    for k in train_keys:
        variants = list(groups[k])
        rng.shuffle(variants)
        n_val = max(1, round(len(variants) * 0.15))
        val += variants[:n_val]
        train += variants[n_val:]

    for part in (train, val, test):
        rng.shuffle(part)
    return train, val, test, sorted(held_out)


def to_utterances(calls: list[dict], seen: set[str] | None = None) -> list[dict]:
    """Flatten calls to labelled utterances, dropping near-duplicates."""
    seen = seen if seen is not None else set()
    rows = []
    for call in calls:
        meta = call["seed"]
        for i, turn in enumerate(call["turns"]):
            text = turn["text"].strip()
            key = normalise(text)
            # Short generic acknowledgements ("haan", "ji sir") repeat across
            # every call and carry no stage signal; keeping them all teaches the
            # model to predict the majority class on noise.
            if len(key) < 4 or key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "text": text,
                    "label": turn["stage"],
                    "victim_state": turn["victim_state"],
                    "speaker": turn["speaker"],
                    "turn_index": i,
                    "call_id": meta["call_id"],
                    "archetype": meta["archetype_id"],
                    "is_scam": meta["is_scam"],
                }
            )
    return rows


def fit_transitions(calls: list[dict]) -> dict:
    """
    Fit the Digital Twin: P(next *different* stage | current stage), how long
    the call dwells in each stage, and the distance from each stage to payment.

    Transitions are fitted on the **collapsed** stage sequence — consecutive
    repeats removed. A scammer spends several turns inside one stage, so a
    raw turn-to-turn matrix is ~85% self-transitions and the forecast chip
    would read "NEXT: ISOLATION" while already in ISOLATION. That is not a
    forecast, it is a status label. Collapsing makes the model answer the
    question the demo actually asks: what comes *after* this.

    Dwell time is kept separately, and is what converts a forecast into an
    ETA: turns-remaining-in-stage plus turns-to-payment, times seconds/turn.

    Laplace smoothing keeps unseen transitions at a small non-zero probability
    so the forecast never asserts 0% or 100% — a chip claiming 100% confidence
    is a chip nobody believes.
    """
    counts: dict[str, Counter] = {lab: Counter() for lab in LABELS}
    dwell: dict[str, list[int]] = defaultdict(list)
    turns_to_payment: dict[str, list[int]] = defaultdict(list)

    for call in calls:
        stages = [t["stage"] for t in call["turns"]]

        # Collapse to (stage, run_length) so both signals fall out of one pass.
        runs: list[tuple[str, int]] = []
        for s in stages:
            if runs and runs[-1][0] == s:
                runs[-1] = (s, runs[-1][1] + 1)
            else:
                runs.append((s, 1))

        for stage, length in runs:
            dwell[stage].append(length)
        for (a, _), (b, _) in zip(runs, runs[1:]):
            counts[a][b] += 1

        # Turns from the first occurrence of each stage to the first payment turn.
        try:
            pay_idx = stages.index("PAYMENT_EXECUTION")
        except ValueError:
            continue
        first_seen: dict[str, int] = {}
        for i, stage in enumerate(stages[:pay_idx]):
            first_seen.setdefault(stage, i)
        for stage, i in first_seen.items():
            turns_to_payment[stage].append(pay_idx - i)

    def _median(xs: list[int]) -> int:
        return sorted(xs)[len(xs) // 2]

    alpha = 0.5
    matrix: dict[str, dict[str, float]] = {}
    for src in LABELS:
        total = sum(counts[src].values()) + alpha * len(LABELS)
        matrix[src] = {dst: (counts[src][dst] + alpha) / total for dst in LABELS}

    return {
        "matrix": matrix,
        "dwell_turns": {
            s: {"median": _median(v), "n": len(v)} for s, v in dwell.items()
        },
        "eta_to_payment": {
            s: {"median_turns": _median(v), "p25": sorted(v)[len(v) // 4], "n": len(v)}
            for s, v in turns_to_payment.items()
        },
        "raw_counts": {k: dict(v) for k, v in counts.items()},
        "note": (
            "matrix is over collapsed stage runs (self-transitions excluded); "
            "dwell_turns gives the median number of utterances spent in a stage"
        ),
    }


def write_jsonl(rows: list[dict], path: Path) -> None:
    with path.open("w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def report(splits: dict[str, list[dict]], calls: list[dict], trans: dict,
           held_out: list[str]) -> str:
    lines = ["# AegisAI corpus report", ""]
    lines.append(f"- Calls: **{len(calls)}** "
                 f"({sum(c['seed']['is_scam'] for c in calls)} scam / "
                 f"{sum(not c['seed']['is_scam'] for c in calls)} benign)")
    total = sum(len(v) for v in splits.values())
    lines.append(f"- Utterances after de-duplication: **{total}**")
    lines.append(f"- **Leave-archetypes-out split.** {len(held_out)} whole skeletons "
                 "are held out for test; the model never trains on them.")
    lines.append("- Held out: " + ", ".join(f"`{h}`" for h in held_out))
    lines.append("- Validation is carved from training skeletons (used only for "
                 "early stopping, never reported).")
    lines.append("")

    lines.append("## Class distribution")
    lines.append("")
    lines.append("| Stage | train | val | test |")
    lines.append("|---|---:|---:|---:|")
    counters = {k: Counter(r["label"] for r in v) for k, v in splits.items()}
    for lab in LABELS:
        lines.append(
            f"| {lab} | {counters['train'][lab]} | "
            f"{counters['val'][lab]} | {counters['test'][lab]} |"
        )
    lines.append("")

    warnings = []
    for lab in LABELS:
        if counters["train"][lab] < 60:
            warnings.append(
                f"`{lab}` has only {counters['train'][lab]} training examples — "
                "generate more calls before trusting its recall."
            )
    for lab in CRITICAL_LABELS:
        if counters["test"][lab] < 15:
            warnings.append(
                f"`{lab}` has only {counters['test'][lab]} test examples — its "
                "recall figure will be too noisy to quote."
            )
    if warnings:
        lines.append("## Warnings")
        lines.append("")
        lines += [f"- {w}" for w in warnings]
        lines.append("")

    lines.append("## Digital Twin — top transitions")
    lines.append("")
    lines.append("| From | Most likely next | p |")
    lines.append("|---|---|---:|")
    for src in LABELS:
        dst, p = max(trans["matrix"][src].items(), key=lambda kv: kv[1])
        lines.append(f"| {src} | {dst} | {p:.2f} |")
    lines.append("")

    if trans["eta_to_payment"]:
        lines.append("## Median turns to payment")
        lines.append("")
        lines.append("| Stage | median turns | n |")
        lines.append("|---|---:|---:|")
        for stage, d in sorted(
            trans["eta_to_payment"].items(), key=lambda kv: kv[1]["median_turns"]
        ):
            lines.append(f"| {stage} | {d['median_turns']} | {d['n']} |")
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the AegisAI training dataset.")
    ap.add_argument("--raw", type=Path, default=RAW)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    if not args.raw.exists():
        print(f"No corpus at {args.raw}. Run generate_calls.py first.")
        return 1

    calls = load_calls(args.raw)
    if len(calls) < 20:
        print(f"Only {len(calls)} calls — generate more before building.")
        return 1

    args.out.mkdir(parents=True, exist_ok=True)
    train_c, val_c, test_c, held_out = split_by_call(calls, seed=args.seed)

    # De-duplicate globally, filling train first, so a duplicated utterance is
    # dropped from val/test rather than from train.
    seen: set[str] = set()
    splits = {
        "train": to_utterances(train_c, seen),
        "val": to_utterances(val_c, seen),
        "test": to_utterances(test_c, seen),
    }
    for name, rows in splits.items():
        write_jsonl(rows, args.out / f"{name}.jsonl")

    # The twin is fitted on training calls only — fitting it on everything
    # would leak the test set into the forecast metrics.
    trans = fit_transitions(train_c)
    (args.out / "transitions.json").write_text(json.dumps(trans, indent=2))

    text = report(splits, calls, trans, held_out)
    (args.out / "report.md").write_text(text)
    print(text)
    print(f"\nWritten to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
