"""
Training-data provenance: bind a checkpoint to the texts it was trained on.

Why this exists
---------------
`manifest.py` ties a score to the exact *weights* it was measured against. That
was not enough. The stage classifier's published macro-F1 of 0.767 matched its
weights perfectly and was still wrong, because nothing recorded which *data*
those weights had seen: the split was rebuilt after training, the old weights
were scored on the new test set, and 311 of its 423 turns turned out to be the
weights' own training data (docs/AUDIT.md, B-01).

So a checkpoint now carries a second record, written by `train.py` beside the
weights: one short hash per training and validation text. With it, "was this
model trained on the thing I am about to test it on?" is a set intersection
rather than an act of memory, and `eval_backends.py` refuses to produce a
comparison when the answer is yes — or when the record is missing, because a
checkpoint that cannot show what it was trained on cannot show it was held out.

What it consumes: the split rows (`text`, and for the test side `call_id` and
`archetype`). What it outputs: `training_data.json` beside the weights, and a
verdict the promotion gate acts on.

Limitations, stated
-------------------
* The match is on exact text after whitespace is collapsed. That is the right
  bar for this corpus, which is de-duplicated globally, so any shared text is a
  shared utterance. It does not see a paraphrase, a shared template or a shared
  scam archetype reached through a different call — those are the split
  builder's job (audit item B-07, task T-38).
* Zero tolerance. A corpus that is *not* de-duplicated will trip the gate on a
  bare "Hello?" appearing on both sides. That is deliberate: a gate that
  forgives a little overlap has to be told how much, and nobody can say.
* `backfill` records what an operator *asserts* a checkpoint was trained on,
  from git history. It cannot prove it, and the record says it was backfilled.

    .venv/bin/python -m ml.evaluation.provenance check
    .venv/bin/python -m ml.evaluation.provenance backfill --rev <git-rev>

Standard library only, on purpose: the serving tests import this, and CI has no
torch.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

ML_DIR = Path(__file__).resolve().parents[1]

PROVENANCE_NAME = "training_data.json"
PROVENANCE_SCHEMA = 1

#: The shape of `backend_comparison.json`. `services/api/engine/classifier.py`
#: holds the same number and refuses any other, and a test asserts the two
#: agree. Schema 1 was the bare `{backend: scores}` map that carried the leak.
COMPARISON_SCHEMA = 2

#: Sixteen hex characters — 64 bits. Enough that two different utterances in a
#: corpus of thousands will not share a key, and a third of the file size of the
#: full digest.
_KEY_HEX = 16

Rows = Sequence[Mapping[str, Any]]


def text_key(text: str) -> str:
    """The identity of one utterance, for membership tests.

    Whitespace is collapsed and nothing else: case, punctuation and script are
    part of what the model saw, and folding them would call two different
    training examples the same one.
    """
    normal = " ".join(text.split())
    return hashlib.sha256(normal.encode("utf-8")).hexdigest()[:_KEY_HEX]


def _digest(keys: Sequence[str]) -> str:
    return hashlib.sha256("\n".join(sorted(keys)).encode("ascii")).hexdigest()


def build(rows_by_split: Mapping[str, Rows], source: str) -> Dict[str, Any]:
    """The record for one training run: every text the weights were fitted or
    early-stopped on. Validation counts — a model selected on a split has seen
    it."""
    keys = sorted({text_key(str(r["text"])) for rows in rows_by_split.values() for r in rows})
    return {
        "schema": PROVENANCE_SCHEMA,
        "source": source,
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "splits": {name: len(rows) for name, rows in rows_by_split.items()},
        "n_texts": len(keys),
        "sha256": _digest(keys),
        "text_keys": keys,
    }


def write(record: Mapping[str, Any], model_dir: Path) -> Path:
    path = model_dir / PROVENANCE_NAME
    path.write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
    return path


def load(model_dir: Path) -> Optional[Dict[str, Any]]:
    """The record beside a checkpoint, or None when there is nothing to trust.

    None covers absent, unreadable, the wrong schema, and a record whose keys
    no longer hash to the digest it carries. All four mean the same thing to
    the gate — this checkpoint cannot show what it was trained on — and a record
    edited by hand to drop the inconvenient keys is the fourth.
    """
    try:
        record = json.loads((model_dir / PROVENANCE_NAME).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(record, dict) or record.get("schema") != PROVENANCE_SCHEMA:
        return None
    keys = record.get("text_keys")
    if not isinstance(keys, list) or not keys or not all(isinstance(k, str) for k in keys):
        return None
    if record.get("sha256") != _digest(keys):
        return None
    return record


def summary(record: Mapping[str, Any]) -> Dict[str, Any]:
    """The record without its keys — what a manifest or a comparison carries."""
    return {k: record[k] for k in ("source", "recorded_at", "splits", "n_texts", "sha256")}


def overlap(record: Mapping[str, Any], test_rows: Rows) -> Dict[str, Any]:
    """How much of a test split the checkpoint was trained on."""
    seen = set(record["text_keys"])
    hits = [r for r in test_rows if text_key(str(r["text"])) in seen]
    totals = Counter(str(r.get("archetype", "unknown")) for r in test_rows)
    leaked = Counter(str(r.get("archetype", "unknown")) for r in hits)
    return {
        "n_test": len(test_rows),
        "overlap_turns": len(hits),
        "overlap_calls": len({r.get("call_id") for r in hits}),
        "test_calls": len({r.get("call_id") for r in test_rows}),
        "by_archetype": {a: {"overlap": leaked[a], "turns": totals[a]} for a in sorted(totals)},
    }


def leak_verdict(
    record: Optional[Mapping[str, Any]], test_rows: Rows
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """May this checkpoint be scored on this test split?

    Returns `(ok, reason, leak_check)`. The reason is a clause that reads on its
    own and after "not promoted:", because `/api/health` shows it both ways.
    """
    if record is None:
        return (
            False,
            f"there is no usable {PROVENANCE_NAME} beside the checkpoint, so nothing "
            "shows it was not trained on the test split",
            None,
        )
    check = overlap(record, test_rows)
    if check["overlap_turns"]:
        return (
            False,
            f"{check['overlap_turns']} of the {check['n_test']} test turns are in the "
            "checkpoint's own training data",
            check,
        )
    return (
        True,
        f"none of the {check['n_test']} test turns is in the checkpoint's training data",
        check,
    )


def comparison_record(
    *,
    status: str,
    reason: str,
    n_test: int,
    results: Mapping[str, Mapping[str, float]],
    leak_check: Optional[Mapping[str, Any]] = None,
    training_data: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """`backend_comparison.json`, schema 2.

    `status` is `valid` (every backend scored, leak check passed), `refused`
    (the checkpoint was not scored; `results` holds the lexical model alone) or
    `no_checkpoint`. The serving side promotes on `valid` and nothing else.
    """
    if status not in ("valid", "refused", "no_checkpoint"):
        raise ValueError(f"unknown comparison status {status!r}")
    return {
        "schema": COMPARISON_SCHEMA,
        "status": status,
        "reason": reason,
        "n_test": n_test,
        "leak_check": dict(leak_check) if leak_check is not None else None,
        "training_data": dict(training_data) if training_data is not None else None,
        "results": {name: dict(scores) for name, scores in results.items()},
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def default_model_dir() -> Path:
    """Where the checkpoint lives — the same answer `services/api/config.py`
    gives, without importing it (this module stays standard-library only)."""
    root = os.environ.get("AEGIS_ARTIFACTS") or os.environ.get("PRESAGE_ARTIFACTS")
    return (Path(root) if root else ML_DIR / "artifacts") / "stage-classifier"


def _jsonl(text: str) -> List[Dict[str, Any]]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def rows_at_rev(rev: str, split: str) -> List[Dict[str, Any]]:
    """One processed split as it was at a git revision."""
    out = subprocess.run(
        ["git", "show", f"{rev}:ml/data/processed/{split}.jsonl"],
        cwd=ML_DIR.parent,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return _jsonl(out.stdout)


def _current(split: str) -> List[Dict[str, Any]]:
    return _jsonl((ML_DIR / "data" / "processed" / f"{split}.jsonl").read_text(encoding="utf-8"))


def _print_check(check: Mapping[str, Any]) -> None:
    print(
        f"test turns in the training data: {check['overlap_turns']} of {check['n_test']} "
        f"({check['overlap_calls']} of {check['test_calls']} calls)"
    )
    for archetype, n in check["by_archetype"].items():
        print(f"  {archetype:28s} {n['overlap']:4d} / {n['turns']}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m ml.evaluation.provenance",
        description="Record, or check, which texts a checkpoint was trained on.",
    )
    parser.add_argument("--model-dir", type=Path, default=None)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="how much of the current test split the checkpoint has seen")
    backfill = sub.add_parser(
        "backfill",
        help="record the training data of a checkpoint trained before this record "
             "existed, from the split as it was at a git revision",
    )
    backfill.add_argument("--rev", required=True, help="git revision the checkpoint was trained at")
    args = parser.parse_args(argv)
    model_dir: Path = args.model_dir or default_model_dir()

    if args.command == "backfill":
        if not (model_dir / "config.json").exists():
            print(f"no checkpoint at {model_dir} — nothing to record")
            return 1
        record = build(
            {"train": rows_at_rev(args.rev, "train"), "val": rows_at_rev(args.rev, "val")},
            source=f"BACKFILLED, asserted not proven: ml/data/processed at git {args.rev}",
        )
        path = write(record, model_dir)
        print(f"wrote {path}: {record['n_texts']} texts from {record['splits']}")
        _print_check(overlap(record, _current("test")))
        return 0

    record = load(model_dir)
    ok, reason, check = leak_verdict(record, _current("test"))
    if check is not None:
        _print_check(check)
    print(f"\n{'OK  ' if ok else 'FAIL'} {reason}")
    return 0 if ok else 2


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
