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

from ml.evaluation import manifest as manifest_mod  # noqa: E402
from ml.training.train import LABELS, load_split  # noqa: E402
from services.api.engine.classifier import (  # noqa: E402
    LexicalStageClassifier,
    MuRILStageClassifier,
)

ARTIFACTS = ML_DIR / "artifacts" / "stage-classifier"


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
    pairs = build_pairs(load_split("test"))
    print(f"held-out test turns: {len(pairs)}")

    results = {}
    y_true, y_pred = evaluate(LexicalStageClassifier(), pairs)
    results["lexical"] = report("lexical fallback", y_true, y_pred)

    if (ARTIFACTS / "config.json").exists():
        y_true, y_pred = evaluate(MuRILStageClassifier(ARTIFACTS), pairs)
        results["muril"] = report("fine-tuned MuRIL", y_true, y_pred)
    else:
        print(f"\nno checkpoint at {ARTIFACTS} — run ml/training/train.py first")

    if len(results) == 2:
        best = max(results, key=lambda k: results[k]["macro_f1"])
        delta = abs(results["muril"]["macro_f1"] - results["lexical"]["macro_f1"])
        print(f"\n{'=' * 60}")
        print(f"winner on held-out archetypes: {best}  (Δ macro-F1 {delta:.4f})")
        if best == "lexical":
            print(
                "\nThe fine-tuned model loses to the baseline on unseen archetypes.\n"
                "That is a data problem, not a training bug: 320 synthetic calls\n"
                "from a seeded grid let the model memorise archetypes instead of\n"
                "learning the stages. Generate more, more varied calls before\n"
                "promoting the checkpoint to default."
            )

    (ARTIFACTS.parent / "backend_comparison.json").write_text(json.dumps(results, indent=2))
    print(f"\nwrote {ARTIFACTS.parent / 'backend_comparison.json'}")

    # Bind these numbers to the exact weights they were measured against.
    # A metrics file with nothing tying it to a model is how this project ended
    # up serving a lexical fallback for weeks on a stale 0.221, and how
    # stage-classifier/metrics.json still claims 0.269 for a 0.767 checkpoint.
    if "muril" in results:
        manifest = manifest_mod.build(
            model_dir=ARTIFACTS,
            results=results,
            split="test",
            n_examples=len(pairs),
        )
        path = manifest_mod.write(manifest, ARTIFACTS.parent)
        print(f"wrote {path}")
        print(f"checkpoint fingerprint: "
              f"{manifest['fingerprint']['combined_sha256'][:16]}…")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
