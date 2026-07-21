#!/usr/bin/env python3
"""
PRESAGE — corpus quality validation.

    python validate_corpus.py                    # validate raw/calls.jsonl
    python validate_corpus.py --processed        # validate the split dataset

Checks:
  - Malformed conversations (missing fields, invalid values)
  - Duplicate conversations (exact normalised text match)
  - Near-duplicates (Jaccard similarity > 0.85)
  - Class imbalance warnings
  - Stage ordering anomalies in scam calls
  - Devanagari contamination
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).parent
RAW = HERE / "data" / "raw" / "calls.jsonl"
PROCESSED = HERE / "data" / "processed"

sys.path.insert(0, str(HERE))
from presage.taxonomy import LABELS  # noqa: E402
from presage.schema import VICTIM_STATES  # noqa: E402

_LABELS = set(LABELS)
_STATES = set(VICTIM_STATES)
_DEVANAGARI = re.compile(r"[\u0900-\u097F]")


def normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", text.lower()).strip()


def tokenset(text: str) -> set[str]:
    return set(normalise(text).split())


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def load_calls(path: Path) -> list[dict]:
    calls = []
    with path.open() as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                calls.append(json.loads(line))
            except json.JSONDecodeError:
                print(f"  WARNING: line {i} is not valid JSON, skipping")
    return calls


def validate_calls(calls: list[dict]) -> dict:
    """Validate raw calls.jsonl. Returns a summary dict."""
    issues: list[str] = []
    stage_counts: Counter = Counter()
    archetype_counts: Counter = Counter()
    scam_count = 0
    benign_count = 0

    # For near-dup detection: collect full-call text
    call_texts: list[tuple[str, str]] = []  # (call_id, normalised full text)

    for ci, call in enumerate(calls):
        cid = call.get("seed", {}).get("call_id", f"call_{ci}")
        is_scam = call.get("seed", {}).get("is_scam", None)

        if is_scam is True:
            scam_count += 1
        elif is_scam is False:
            benign_count += 1
        else:
            issues.append(f"{cid}: missing or invalid is_scam field")

        archetype = call.get("seed", {}).get("archetype_id", "UNKNOWN")
        archetype_counts[archetype] += 1

        turns = call.get("turns")
        if not turns or not isinstance(turns, list):
            issues.append(f"{cid}: missing or empty turns")
            continue

        if len(turns) < 4:
            issues.append(f"{cid}: only {len(turns)} turns (suspiciously short)")

        full_text_parts = []
        seen_stages: list[str] = []
        has_caller = False
        has_victim = False

        for ti, turn in enumerate(turns):
            speaker = turn.get("speaker", "")
            text = turn.get("text", "")
            stage = turn.get("stage", "")
            state = turn.get("victim_state", "")

            if speaker == "CALLER":
                has_caller = True
            elif speaker == "VICTIM":
                has_victim = True
            else:
                issues.append(f"{cid} turn {ti}: invalid speaker '{speaker}'")

            if not text or not text.strip():
                issues.append(f"{cid} turn {ti}: empty text")

            if stage not in _LABELS:
                issues.append(f"{cid} turn {ti}: invalid stage '{stage}'")
            else:
                stage_counts[stage] += 1
                seen_stages.append(stage)

            if state not in _STATES:
                issues.append(f"{cid} turn {ti}: invalid victim_state '{state}'")

            if _DEVANAGARI.search(text):
                issues.append(f"{cid} turn {ti}: contains Devanagari script")

            full_text_parts.append(normalise(text))

        if not has_caller:
            issues.append(f"{cid}: no CALLER turns")
        if not has_victim:
            issues.append(f"{cid}: no VICTIM turns")

        # Check stage ordering for scam calls
        if is_scam and seen_stages:
            stage_order = {
                "GREETING": 0, "AUTHORITY_CLAIM": 1, "FEAR_INDUCTION": 2,
                "ISOLATION": 3, "VERIFICATION_DEMAND": 4,
                "PAYMENT_SETUP": 5, "PAYMENT_EXECUTION": 6, "BENIGN": -1,
            }
            # Check if PAYMENT_EXECUTION appears before FEAR_INDUCTION
            pay_idx = next(
                (i for i, s in enumerate(seen_stages) if s == "PAYMENT_EXECUTION"), None
            )
            fear_idx = next(
                (i for i, s in enumerate(seen_stages) if s == "FEAR_INDUCTION"), None
            )
            if pay_idx is not None and fear_idx is not None and pay_idx < fear_idx:
                issues.append(
                    f"{cid}: PAYMENT_EXECUTION appears before FEAR_INDUCTION "
                    "(unusual stage ordering)"
                )

        call_texts.append((cid, " ".join(full_text_parts)))

    # Exact duplicates
    text_to_ids: dict[str, list[str]] = defaultdict(list)
    for cid, text in call_texts:
        text_to_ids[text].append(cid)
    exact_dups = {k: v for k, v in text_to_ids.items() if len(v) > 1}
    if exact_dups:
        for text, ids in list(exact_dups.items())[:5]:
            issues.append(f"EXACT DUPLICATE: {', '.join(ids[:3])} ({len(ids)} copies)")

    # Near-duplicate detection (sample-based for performance)
    near_dups = 0
    tokens_list = [(cid, tokenset(text)) for cid, text in call_texts]
    # Check a sample: first 500 pairs
    checked = 0
    for i in range(min(len(tokens_list), 200)):
        for j in range(i + 1, min(len(tokens_list), 200)):
            sim = jaccard(tokens_list[i][1], tokens_list[j][1])
            if sim > 0.85:
                near_dups += 1
                if near_dups <= 3:
                    issues.append(
                        f"NEAR-DUPLICATE (Jaccard={sim:.2f}): "
                        f"{tokens_list[i][0]} <-> {tokens_list[j][0]}"
                    )
            checked += 1

    return {
        "total_calls": len(calls),
        "scam": scam_count,
        "benign": benign_count,
        "total_turns": sum(len(c.get("turns", [])) for c in calls),
        "stage_counts": dict(stage_counts.most_common()),
        "archetype_counts": dict(archetype_counts.most_common()),
        "exact_duplicates": len(exact_dups),
        "near_duplicates_found": near_dups,
        "near_duplicates_checked_pairs": checked,
        "issues": issues,
    }


def validate_processed(directory: Path) -> dict:
    """Validate the processed train/val/test splits."""
    splits = {}
    for name in ("train", "val", "test"):
        path = directory / f"{name}.jsonl"
        if not path.exists():
            print(f"  WARNING: {path} does not exist")
            continue
        rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
        counts = Counter(r["label"] for r in rows)
        splits[name] = {"total": len(rows), "per_class": dict(counts)}

    warnings = []
    if "train" in splits:
        for label in LABELS:
            n = splits["train"]["per_class"].get(label, 0)
            if n < 60:
                warnings.append(
                    f"{label}: only {n} training examples (need >= 60 for reliable recall)"
                )
    if "test" in splits:
        for label in LABELS:
            n = splits["test"]["per_class"].get(label, 0)
            if n < 15:
                warnings.append(
                    f"{label}: only {n} test examples (F1 too noisy to quote)"
                )

    return {"splits": splits, "warnings": warnings}


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate the PRESAGE corpus.")
    ap.add_argument("--raw", type=Path, default=RAW)
    ap.add_argument("--processed", action="store_true", help="validate splits too")
    args = ap.parse_args()

    print("=" * 60)
    print("PRESAGE Corpus Validation Report")
    print("=" * 60)

    if args.raw.exists():
        calls = load_calls(args.raw)
        result = validate_calls(calls)

        print(f"\n--- Raw Corpus: {args.raw} ---")
        print(f"Total calls: {result['total_calls']} "
              f"({result['scam']} scam / {result['benign']} benign)")
        print(f"Total turns: {result['total_turns']}")
        print(f"Exact duplicates: {result['exact_duplicates']}")
        print(f"Near-duplicates found: {result['near_duplicates_found']} "
              f"(checked {result['near_duplicates_checked_pairs']} pairs)")

        print("\n--- Stage Distribution (across all turns) ---")
        for label in LABELS:
            n = result["stage_counts"].get(label, 0)
            bar = "#" * (n // 20)
            flag = " [!]" if n < 100 else ""
            print(f"  {label:24s} {n:5d} {bar}{flag}")

        print("\n--- Archetype Distribution ---")
        for arch, n in sorted(result["archetype_counts"].items(),
                              key=lambda kv: -kv[1]):
            print(f"  {arch:30s} {n:4d}")

        if result["issues"]:
            print(f"\n--- Issues ({len(result['issues'])}) ---")
            for issue in result["issues"][:30]:
                print(f"  [!] {issue}")
            if len(result["issues"]) > 30:
                print(f"  ... and {len(result['issues']) - 30} more")
        else:
            print("\n[OK] No issues found!")
    else:
        print(f"\n[!] Raw corpus not found at {args.raw}")

    if args.processed:
        print(f"\n--- Processed Splits: {PROCESSED} ---")
        if PROCESSED.exists():
            presult = validate_processed(PROCESSED)
            for name, info in presult["splits"].items():
                print(f"\n  {name}: {info['total']} utterances")
                for label in LABELS:
                    n = info["per_class"].get(label, 0)
                    print(f"    {label:24s} {n:4d}")

            if presult["warnings"]:
                print("\n  Warnings:")
                for w in presult["warnings"]:
                    print(f"    [!] {w}")
        else:
            print(f"  [!] Directory not found")

    print("\n" + "=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
