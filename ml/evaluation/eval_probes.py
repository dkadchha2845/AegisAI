#!/usr/bin/env python3
"""
Score the English probe sets end to end, through `analyze_text`.

    .venv/bin/python ml/evaluation/eval_probes.py [--set dev|heldout|all] [-v]

Why this exists
---------------
The stage split measures one classifier on one turn at a time. A user sees a
verdict, which is the classifier *plus* the passport checks, payment framing
and fusion — and that is where audit item B-08 lived: a textbook English
customs scam read LIKELY_LEGITIMATE because every mechanical check that floors
a score was written in Hinglish. These probes are whole messages with a known
answer, scored the way the Analyze page scores them.

Two sets, kept apart on purpose:
  * `english_dev.jsonl` — what cue changes are tuned against;
  * `english_heldout.jsonl` — written at the same time, before any tuning, and
    scored only to report the result. A rule that only helps dev is a rule
    that memorised dev.

Each set holds scams *and* benign messages written to sit near them (a real
customs-duty notice, a real e-challan, a police awareness SMS), because the
failure this project fears most is a false positive.

`--calls` scores every call in `ml/data/processed` the same way, as a
transcript, so a rule narrowed to stop an English false positive is seen to
cost (or not cost) Hinglish recall. The lexical rules are hand-written, not
trained, so scoring them on every split is sound; the per-split counts are
printed anyway.

What it reports
---------------
Scam recall at SUSPICIOUS or worse (score ≥ 40) and at LIKELY_SCAM (≥ 70), and
the benign false-positive rate at ≥ 40. These are synthetic probes written by
the project, not field data; they are a regression net and a measurement of a
specific gap, not a claim about real-world detection rates.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ML_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ML_DIR.parent))

from services.api.engine.analyzer import analyze_text

PROBES = ML_DIR / "data" / "probes"
SETS = {"dev": "english_dev.jsonl", "heldout": "english_heldout.jsonl"}

#: The two verdict boundaries in `analyzer._verdict_of`.
SUSPICIOUS, LIKELY_SCAM = 40.0, 70.0


def load(name: str) -> List[Dict[str, Any]]:
    path = PROBES / SETS[name]
    return [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]


def score(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for row in rows:
        result = analyze_text(row["text"])
        out.append({**row, "score": result.score, "verdict": result.verdict})
    return out


def load_calls() -> Dict[str, List[Dict[str, Any]]]:
    """Every call in the committed splits, as probe rows, keyed by split."""
    out: Dict[str, List[Dict[str, Any]]] = {}
    for split in ("train", "val", "test"):
        calls: Dict[str, List[dict]] = {}
        path = ML_DIR / "data" / "processed" / f"{split}.jsonl"
        for line in path.open(encoding="utf-8"):
            if line.strip():
                row = json.loads(line)
                calls.setdefault(row["call_id"], []).append(row)
        out[split] = [
            {
                "text": "\n".join(
                    f"{t['speaker']}: {t['text']}"
                    for t in sorted(turns, key=lambda t: t["turn_index"])
                ),
                "is_scam": turns[0]["is_scam"],
                "kind": turns[0]["archetype"],
            }
            for turns in calls.values()
        ]
    return out


def summary(scored: List[Dict[str, Any]]) -> Dict[str, Any]:
    scams = [r for r in scored if r["is_scam"]]
    benign = [r for r in scored if not r["is_scam"]]
    return {
        "n_scam": len(scams),
        "n_benign": len(benign),
        "scam_flagged": sum(r["score"] >= SUSPICIOUS for r in scams),
        "scam_likely": sum(r["score"] >= LIKELY_SCAM for r in scams),
        "benign_flagged": sum(r["score"] >= SUSPICIOUS for r in benign),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--set", choices=[*SETS, "all"], default="all")
    parser.add_argument("--calls", action="store_true",
                        help="score the corpus calls instead of the probes")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    if args.calls:
        groups = load_calls()
    else:
        groups = {name: load(name) for name in (SETS if args.set == "all" else [args.set])}
    for name, rows in groups.items():
        scored = score(rows)
        s = summary(scored)
        print(
            f"{name:8s} scams flagged {s['scam_flagged']}/{s['n_scam']}, "
            f"likely-scam {s['scam_likely']}/{s['n_scam']}; "
            f"benign flagged {s['benign_flagged']}/{s['n_benign']}"
        )
        if args.verbose:
            for r in scored:
                wrong = (r["score"] >= SUSPICIOUS) != r["is_scam"]
                mark = "✗" if wrong else " "
                tag = "SCAM  " if r["is_scam"] else "benign"
                print(f"  {mark} {tag} {r['score']:5.1f} {r['kind']:18s} {r['text'][:70]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
