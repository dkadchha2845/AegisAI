#!/usr/bin/env python3
"""
Experiment 0 — how much of the stage classifier's published score was a leak.

    .venv/bin/python research/experiments/exp0_stage_classifier_leak.py

Writes `research/results/exp0_stage_classifier_leak.json`. Re-running it on the
same weights reproduces that file byte for byte (T-06, audit B-01, D-04).

**The question.** The fine-tuned MuRIL checkpoint was published at macro-F1
0.767. The promotion gate had scored it on a test split rebuilt *after*
training, most of which the weights had been trained on. This measures the
checkpoint, the lexical baseline and their fusion on the turns it had seen and
the turns it had not, so the leak has a size rather than an adjective.

**Two historical splits, read from git.** Nothing here depends on the working
tree's data, which has been rebuilt twice since:

* `e123bd5` — the test split the 0.767 was measured on (the last commit before
  B-07 rebuilt it).
* the revision the checkpoint's provenance record names — the split it was
  trained against, whose test part it never saw.

Each split is cut by the provenance record beside the weights into *all*,
*leaked* (the turn's text is in the training or validation data) and *unseen*.
`n` is reported for every cell; a score with no n is not a result.

**The baseline as it was.** The lexical cues have been revised since (audit
B-08). `lexical@e123bd5` is scored with the cues read from `classifier.py` at
that revision, which is what produced the published comparison; `lexical`
(current) is today's cues, so the effect of later rule changes is visible
rather than silently folded into a historical number. The fused backend is the
checkpoint fused with `lexical@e123bd5`, as it was served then.

**Protocol.** The promotion gate's own: one previous turn of context per
utterance, through `StageClassifier.predict` (`ml/evaluation/eval_backends`).

**Limitations.** Synthetic corpus. Lexical figures are not clean held-out
estimates: its cues were written with the corpus in view (audit D-16). The
leaked/unseen cut is by exact text, so a near-paraphrase of a training turn
counts as unseen — which errs toward flattering the checkpoint, not against it.
"""

from __future__ import annotations

import ast
import contextlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterator, List, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from sklearn.metrics import accuracy_score, f1_score  # noqa: E402

from ml.evaluation import manifest, provenance  # noqa: E402
from ml.evaluation.eval_backends import build_pairs, evaluate  # noqa: E402
from services.api.config import settings  # noqa: E402
from services.api.engine import classifier as classifier_mod  # noqa: E402
from services.api.engine.classifier import (  # noqa: E402
    FusedStageClassifier,
    LexicalStageClassifier,
    MuRILStageClassifier,
)

OUT = ROOT / "research" / "results" / "exp0_stage_classifier_leak.json"
PUBLISHED_SPLIT = "e123bd5"
#: Rounded so a re-run is byte-identical; the fourth decimal is below anything
#: this corpus can resolve.
DIGITS = 4


def _git_show(rev: str, path: str) -> str:
    return subprocess.run(
        ["git", "show", f"{rev}:{path}"], cwd=ROOT, check=True,
        capture_output=True, text=True, encoding="utf-8",
    ).stdout


def cues_at(rev: str) -> Dict[str, list]:
    """The lexical `CUES` table as `classifier.py` had it at `rev`."""
    tree = ast.parse(_git_show(rev, "services/api/engine/classifier.py"))
    for node in tree.body:
        target = node.target if isinstance(node, ast.AnnAssign) else (
            node.targets[0] if isinstance(node, ast.Assign) else None
        )
        if isinstance(target, ast.Name) and target.id == "CUES" and node.value is not None:
            return ast.literal_eval(node.value)
    raise SystemExit(f"no CUES table in classifier.py at {rev}")


@contextlib.contextmanager
def lexical_cues(cues: Dict[str, list]) -> Iterator[None]:
    """Score with another revision's cues. `LexicalStageClassifier.predict`
    reads the module's compiled table at call time, so swapping it is the
    whole change — the scoring code is today's, the rules are the old ones."""
    saved = classifier_mod._COMPILED
    classifier_mod._COMPILED = {
        label: [(re.compile(p, re.I), w) for p, w in pats] for label, pats in cues.items()
    }
    try:
        yield
    finally:
        classifier_mod._COMPILED = saved


def scores(y_true: Sequence[int], y_pred: Sequence[int]) -> Dict[str, float]:
    return {
        # Over the labels present in gold or prediction — the gate's own
        # convention (`eval_backends.report`). Forcing all eight would score a
        # stage a cut never contains as F1 0: the leaked cut has no BENIGN
        # turn, and a checkpoint that labels all 311 correctly would read 0.875.
        "macro_f1": round(float(f1_score(y_true, y_pred, average="macro",
                                         zero_division=0)), DIGITS),
        "accuracy": round(float(accuracy_score(y_true, y_pred)), DIGITS),
    }


def subsets(rows: List[Dict[str, Any]], record: Dict[str, Any]) -> Dict[str, List[int]]:
    """Row indices of each cut, by exact text membership in the record."""
    seen = set(record["text_keys"])
    leaked = [i for i, r in enumerate(rows) if provenance.text_key(str(r["text"])) in seen]
    leaked_set = set(leaked)
    return {
        "all": list(range(len(rows))),
        "leaked": leaked,
        "unseen": [i for i in range(len(rows)) if i not in leaked_set],
    }


def ordered(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Rows in the order `build_pairs` emits pairs, so index i is pair i."""
    by_call: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        by_call.setdefault(row["call_id"], []).append(row)
    return [r for call in by_call.values() for r in sorted(call, key=lambda r: r["turn_index"])]


def run_split(rows: List[Dict[str, Any]], record: Dict[str, Any], backends: Dict[str, Any]) -> Dict[str, Any]:
    rows = ordered(rows)
    pairs = build_pairs(rows)  # context is the previous turn in the whole call
    cuts = subsets(rows, record)
    predictions: Dict[str, tuple] = {}
    for name, (clf, cues) in backends.items():
        with lexical_cues(cues) if cues is not None else contextlib.nullcontext():
            predictions[name] = evaluate(clf, pairs)
    out: Dict[str, Any] = {}
    for cut, idx in cuts.items():
        cell: Dict[str, Any] = {"n": len(idx)}
        for name, (y_true, y_pred) in predictions.items():
            # An empty cut has no score, not a score of zero: the checkpoint's
            # own test split has no leaked turns, which is the point of it.
            cell[name] = (
                scores([y_true[i] for i in idx], [y_pred[i] for i in idx]) if idx else None
            )
        out[cut] = cell
    return out


def main() -> int:
    model_dir = settings.classifier_dir
    record = provenance.load(model_dir)
    if record is None:
        print(f"No provenance record beside {model_dir}; the leak cannot be measured.")
        return 1
    trained_rev = re.search(r"at git (\w+)", record["source"])
    if not trained_rev:
        print(f"The provenance record does not name a git revision: {record['source']!r}")
        return 1

    old_cues = cues_at(PUBLISHED_SPLIT)
    lexical = LexicalStageClassifier()
    muril = MuRILStageClassifier(model_dir)
    backends = {
        f"lexical@{PUBLISHED_SPLIT}": (lexical, old_cues),
        "lexical": (lexical, None),
        "muril": (muril, None),
        f"fused@{PUBLISHED_SPLIT}": (FusedStageClassifier(muril, lexical), old_cues),
    }

    result = {
        "experiment": "exp0_stage_classifier_leak",
        "question": "How much of the stage classifier's published macro-F1 was a train/test leak?",
        "checkpoint": {
            "fingerprint": manifest.fingerprint(model_dir),
            "provenance": provenance.summary(record),
        },
        "protocol": "one previous turn of context per utterance, through StageClassifier.predict "
                    "(ml/evaluation/eval_backends.py); macro-F1 over the stages present in "
                    "gold or prediction, as the gate computes it",
        "cuts": "leaked = the turn's exact text is in the checkpoint's train+val; unseen = not",
        "splits": {
            f"published_test@{PUBLISHED_SPLIT}": run_split(
                provenance.rows_at_rev(PUBLISHED_SPLIT, "test"), record, backends
            ),
            f"own_test@{trained_rev.group(1)}": run_split(
                provenance.rows_at_rev(trained_rev.group(1), "test"), record, backends
            ),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    for split, cuts in result["splits"].items():
        print(f"\n{split}")
        for cut, cell in cuts.items():
            line = "  ".join(
                f"{name} {cell[name]['macro_f1']:.3f}" if cell[name] else f"{name} —"
                for name in backends
            )
            print(f"  {cut:7s} n={cell['n']:4d}  {line}")
    print(f"\nwrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
