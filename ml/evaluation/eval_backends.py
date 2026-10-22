#!/usr/bin/env python3
"""
Compare the fine-tuned classifier against the lexical fallback, on the same
held-out test set, through the same serving interface.

    .venv/bin/python ml/evaluation/eval_backends.py

Why this exists
---------------
`train.py` reports the fine-tuned model's test score. It does not tell you
whether that score is any *good*, because there is no baseline next to it. The
lexical classifier is the thing the API actually serves when the checkpoint is
absent, so it is the baseline that matters: shipping a fine-tuned model that
loses to it would be worse than shipping nothing, and you cannot know which
without measuring both the same way.

Both are evaluated through `StageClassifier.predict`, not through their
internals, so this measures what the API will actually do — including the
speaker-tagged context join, which is exactly the thing most likely to be
wrong.

What it refuses to do
---------------------
Score a checkpoint on data it was trained on. This script once did exactly
that: the split was rebuilt after training, the old weights were scored on the
new test set, and the macro-F1 of 0.767 it wrote down was a leak — 311 of the
423 test turns were the weights' own training data (docs/AUDIT.md, B-01).

So before the checkpoint is loaded, `provenance.leak_verdict` compares the test
split against the record `train.py` leaves beside the weights. If any test turn
is in it, or there is no record, the checkpoint is **not scored**: the script
writes the refusal and its reason where the comparison would have gone, and
exits non-zero. The lexical model is still scored, and the API serves it. It
is not trained, so no test turn is in its weights — but its cues are written by
hand with the corpus in view, and were last revised (audit B-08) after reading
lines from archetypes that now sit in the test split. Its figure is a
regression measure for this code, not a clean held-out estimate (audit D-16).

When the check passes, three backends are scored, not two: the fused model is
what the API actually serves when a checkpoint is promoted, so it is the one
promotion is decided on.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from sklearn.metrics import classification_report, f1_score

# ML_DIR, not Path(__file__).parent: this script moved into a subdirectory of
# ml/, so data and artifacts are one level up. Deriving them from a named
# anchor keeps a future move from silently pointing at the wrong corpus.
ML_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ML_DIR.parent))

from ml.evaluation import manifest as manifest_mod
from ml.evaluation import provenance
from ml.training.train import LABELS, load_split
from services.api.config import settings
from services.api.engine.classifier import (
    COMPARISON_PATH,
    FusedStageClassifier,
    LexicalStageClassifier,
    MuRILStageClassifier,
)

#: The serving path's own answer, not a second derivation of it: the gate must
#: score the checkpoint the API would load, and write where the API will read.
#: (`AEGIS_ARTIFACTS` moves both.)
ARTIFACTS = settings.classifier_dir

#: Exit status when the checkpoint was not scored. Distinct from 1 so a caller
#: can tell "the gate refused" from "the script crashed".
EXIT_REFUSED = 2


def build_pairs(rows: list[dict]) -> list[tuple[str, str, str, str, str]]:
    """(text, speaker, prev_text, prev_speaker, gold) in call order."""
    by_call: dict[str, list[dict]] = {}
    for row in rows:
        by_call.setdefault(row["call_id"], []).append(row)

    out = []
    for call_rows in by_call.values():
        call_rows.sort(key=lambda r: r["turn_index"])
        for i, row in enumerate(call_rows):
            prev = call_rows[i - 1] if i else None
            out.append((
                row["text"],
                row["speaker"],
                prev["text"] if prev else "",
                prev["speaker"] if prev else "VICTIM",
                row["label"],
            ))
    return out


def evaluate(clf, pairs) -> tuple[list[int], list[int]]:
    y_true, y_pred = [], []
    index = {label: i for i, label in enumerate(LABELS)}
    for text, speaker, prev_text, prev_speaker, gold in pairs:
        pred = clf.predict(
            text,
            history=[prev_text] if prev_text else None,
            speaker=speaker,
            previous_speaker=prev_speaker,
        )
        y_true.append(index[gold])
        y_pred.append(index[pred.label])
    return y_true, y_pred


def report(name: str, y_true, y_pred) -> dict:
    macro = f1_score(y_true, y_pred, average="macro", zero_division=0)
    print(f"\n=== {name}: macro-F1 {macro:.4f} ===")
    print(classification_report(
        y_true, y_pred, target_names=LABELS,
        labels=range(len(LABELS)), zero_division=0, digits=3,
    ))
    return {
        "macro_f1": float(macro),
        "weighted_f1": float(f1_score(y_true, y_pred, average="weighted", zero_division=0)),
    }


def main() -> int:
    test_rows = load_split("test")
    pairs = build_pairs(test_rows)
    print(f"held-out test turns: {len(pairs)}")

    # The lexical model has no training data, so there is nothing for it to
    # have leaked from. It is scored unconditionally.
    results = {}
    y_true, y_pred = evaluate(LexicalStageClassifier(), pairs)
    results["lexical"] = report("lexical fallback", y_true, y_pred)

    if not (ARTIFACTS / "config.json").exists():
        print(f"\nno checkpoint at {ARTIFACTS} — run ml/training/train.py first")
        _write_comparison(provenance.comparison_record(
            status="no_checkpoint",
            reason="no fine-tuned checkpoint was present when the gate ran",
            n_test=len(pairs),
            results=results,
        ))
        return 0

    trained_on = provenance.load(ARTIFACTS)
    ok, reason, leak_check = provenance.leak_verdict(trained_on, test_rows)
    training_data = provenance.summary(trained_on) if trained_on is not None else None

    if ok:
        muril = MuRILStageClassifier(ARTIFACTS)
        y_true, y_pred = evaluate(muril, pairs)
        results["muril"] = report("fine-tuned MuRIL", y_true, y_pred)
        y_true, y_pred = evaluate(FusedStageClassifier(muril, LexicalStageClassifier()), pairs)
        results["fused"] = report("fused (MuRIL + lexical) — what the API would serve", y_true, y_pred)

        best = max(results, key=lambda k: results[k]["macro_f1"])
        print(f"\n{'=' * 60}")
        print(f"leak check passed: {reason}")
        print(f"winner on held-out data: {best}")
        if results["fused"]["macro_f1"] < results["lexical"]["macro_f1"]:
            print(
                "\nThe fused model loses to the lexical baseline on data the\n"
                "checkpoint has not seen, so it will not be promoted. That is a\n"
                "data problem, not a training bug: generate more, more varied\n"
                "calls before retraining."
            )
    else:
        print(f"\n{'=' * 60}")
        print(f"REFUSED: {reason}.")
        print(
            "The checkpoint was not scored, because a score on data it was\n"
            "trained on is not a measurement. The API will serve the lexical\n"
            "model. See docs/AUDIT.md, B-01."
        )
        if leak_check is not None:
            for archetype, n in leak_check["by_archetype"].items():
                print(f"  {archetype:28s} {n['overlap']:4d} / {n['turns']} turns trained on")

    _write_comparison(provenance.comparison_record(
        status="valid" if ok else "refused",
        reason=reason,
        n_test=len(pairs),
        results=results,
        leak_check=leak_check,
        training_data=training_data,
    ))

    # Bind this outcome to the exact weights it is about — a score, or a
    # refusal — so neither can be mistaken for a statement about another model.
    manifest = manifest_mod.build(
        model_dir=ARTIFACTS,
        results=results,
        split="test",
        n_examples=len(pairs),
        status="valid" if ok else "refused",
        reason=reason,
        leak_check=leak_check,
        training_data=training_data,
    )
    path = manifest_mod.write(manifest, ARTIFACTS.parent)
    print(f"wrote {path}")
    print(f"checkpoint fingerprint: "
          f"{manifest['fingerprint']['combined_sha256'][:16]}…")
    return 0 if ok else EXIT_REFUSED


def _write_comparison(record: dict) -> None:
    COMPARISON_PATH.write_text(json.dumps(record, indent=2) + "\n")
    print(f"\nwrote {COMPARISON_PATH}")


if __name__ == "__main__":
    sys.exit(main())
