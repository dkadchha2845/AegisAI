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
judge who asks how you split.

And splits are made **by archetype**, so every scam type sits in exactly one
of train, validation and test (audit B-07). The previous builder held out
call *skeletons*; three archetypes have more than one skeleton, so
`kyc_expiry` was in all three splits and `loan_app_harassment` and
`genuine_police` in both validation and test — the split was called
leave-archetypes-out and was not. `services/api/tests/test_dataset_split.py`
now asserts the disjointness on the committed files.
"""

from __future__ import annotations

import argparse
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

from aegis_core.taxonomy import CRITICAL_LABELS, LABELS

# ML_DIR, not Path(__file__).parent: this script moved into a subdirectory of
# ml/, so data and artifacts are one level up. Deriving them from a named
# anchor keeps a future move from silently pointing at the wrong corpus.
ML_DIR = Path(__file__).resolve().parents[1]
RAW = ML_DIR / "data" / "raw" / "calls.jsonl"
OUT = ML_DIR / "data" / "processed"


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
    # UTF-8, explicitly: two calls once carried a Windows-1252 byte and the
    # default encoding of whatever machine ran this decided whether it worked.
    with path.open(encoding="utf-8") as f:
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


#: Target share of *turns* in each split. The archetypes are of very different
#: sizes (1 call to 22), so the split fills toward these rather than counting
#: archetypes.
TEST_SHARE = 0.25
VAL_SHARE = 0.15
#: How many seeds the builder will try for a split that meets every constraint
#: before giving up. Deterministic: the first seed (from `seed` upward) that
#: works is the one used, and the report records it.
MAX_SEED_TRIES = 500
#: Archetypes that always train. `digital_arrest` is the scam the live product
#: is built around: holding it out would leave the Digital Twin — fitted on
#: training calls only — with no digital-arrest transitions at all, and any
#: retrain with no example of the call it exists to stop. Pinning it is a
#: product decision, stated here and in the report, not a tuning of the
#: benchmark: the test set still contains only archetypes never trained on.
PINNED_TRAIN = frozenset({"digital_arrest"})
#: Benign calls validation and test must each hold. "Both classes present"
#: was met by a single call, and the seed-8 split had exactly one benign call
#: in each — which left a call-level false-positive rate unmeasurable on
#: either (audit B-09). Five is a floor, not a target: whole benign archetypes
#: run to twenty calls, so a split that meets it holds far more.
MIN_BENIGN_CALLS = 5


def _turns(calls: list[dict]) -> int:
    return sum(len(c["turns"]) for c in calls)


def _labels(calls: list[dict]) -> set[str]:
    return {t["stage"] for c in calls for t in c["turns"]}


def _try_split(
    groups: dict[str, list[dict]], rng: random.Random
) -> tuple[list[str], list[str], list[str]]:
    """One attempt: fill test, then validation, toward their target shares with
    whole archetypes, two scam to one benign so neither split is one-sided, and
    skipping any archetype that would overshoot the share by more than a fifth.
    Everything left is training."""
    total = sum(_turns(g) for g in groups.values())
    free = [a for a in groups if a not in PINNED_TRAIN]
    scam = [a for a in free if groups[a][0]["seed"]["is_scam"]]
    benign = [a for a in free if not groups[a][0]["seed"]["is_scam"]]
    rng.shuffle(scam)
    rng.shuffle(benign)

    def fill(share: float) -> list[str]:
        target = share * total
        chosen: list[str] = []
        size = 0
        pattern = ("scam", "scam", "benign")
        k = 0
        tries = 0
        while size < 0.9 * target and (scam or benign) and tries < 4 * len(groups):
            tries += 1
            pool = scam if (pattern[k % 3] == "scam" and scam) or not benign else benign
            k += 1
            archetype = pool[-1]
            n = _turns(groups[archetype])
            if size + n > 1.2 * target:
                # Too big for what is left of this share: rotate it to the front
                # of its pool so a smaller one gets the next turn.
                pool.insert(0, pool.pop())
                continue
            pool.pop()
            chosen.append(archetype)
            size += n
        return chosen

    test = fill(TEST_SHARE)
    val = fill(VAL_SHARE)
    train = scam + benign + sorted(PINNED_TRAIN & set(groups))
    return train, val, test


def split_by_call(
    calls: list[dict], seed: int = 7
) -> tuple[list, list, list, dict[str, list[str]]]:
    """Leave-archetypes-out split. Returns (train, val, test, archetypes_by_split).

    Whole archetypes are assigned to one split each, so the test set is scam
    types the model has never seen in any form — which measures whether it
    recognises coercion, rather than whether it has memorised these scripts.
    Validation is archetype-disjoint too: it picks the early-stopping epoch, and
    a validation set that shares archetypes with training rewards the same
    memorisation the test set is there to expose.

    A split is accepted only if both validation and test contain every one of
    the eight stages, scam calls, and at least `MIN_BENIGN_CALLS` benign calls;
    seeds are tried in order from `seed` until one does.
    """
    groups: dict[str, list[dict]] = defaultdict(list)
    for c in calls:
        groups[c["seed"]["archetype_id"]].append(c)

    for attempt in range(MAX_SEED_TRIES):
        rng = random.Random(seed + attempt)
        train_a, val_a, test_a = _try_split(groups, rng)
        parts = {
            "train": [c for a in train_a for c in groups[a]],
            "val": [c for a in val_a for c in groups[a]],
            "test": [c for a in test_a for c in groups[a]],
        }
        ok = all(
            _labels(parts[p]) >= set(LABELS)
            and any(c["seed"]["is_scam"] for c in parts[p])
            and sum(not c["seed"]["is_scam"] for c in parts[p]) >= MIN_BENIGN_CALLS
            for p in ("val", "test")
        ) and _labels(parts["train"]) >= set(LABELS)
        if ok:
            for part in parts.values():
                rng.shuffle(part)
            chosen = {"train": sorted(train_a), "val": sorted(val_a), "test": sorted(test_a),
                      "seed": [str(seed + attempt)]}
            return parts["train"], parts["val"], parts["test"], chosen

    raise SystemExit(
        f"No archetype split within {MAX_SEED_TRIES} seeds gives validation and test "
        f"every stage and {MIN_BENIGN_CALLS} benign calls. Generate more varied calls "
        "before building."
    )


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
           held_out: dict[str, list[str]]) -> str:
    lines = ["# AegisAI corpus report", ""]
    lines.append(f"- Calls: **{len(calls)}** "
                 f"({sum(c['seed']['is_scam'] for c in calls)} scam / "
                 f"{sum(not c['seed']['is_scam'] for c in calls)} benign)")
    total = sum(len(v) for v in splits.values())
    lines.append(f"- Utterances after de-duplication: **{total}**")
    # Some generated calls are templated variants whose every turn duplicates
    # an earlier call's; they contribute nothing and are in no split. Said here
    # so "338 calls" and the model card's per-split call counts are not read
    # as disagreeing.
    used = {r["call_id"] for rows in splits.values() for r in rows}
    lines.append(f"- Calls contributing at least one utterance: **{len(used)}** "
                 f"({len(calls) - len(used)} were entirely near-duplicates of earlier calls)")
    lines.append("- **Leave-archetypes-out split.** Every archetype (scam type) sits in "
                 "exactly one split; the model never sees a test archetype in any form. "
                 f"Seed {held_out['seed'][0]}.")
    for name in ("test", "val"):
        lines.append(f"- {name.capitalize()} archetypes ({len(held_out[name])}): "
                     + ", ".join(f"`{h}`" for h in held_out[name]))
    lines.append(f"- Train archetypes: {len(held_out['train'])} "
                 f"(always including {', '.join(f'`{a}`' for a in sorted(PINNED_TRAIN))}, "
                 "the scam the live product is built around)")
    lines.append("- Validation is archetype-disjoint from training too; it picks the "
                 "early-stopping epoch and is never reported.")
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
