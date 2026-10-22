"""
The fused classifier gives one answer per input, in every process (audit B-12).

It broke ties by iterating a `set` of label strings, whose order Python
randomises per process (`PYTHONHASHSEED`). The same turn could be labelled
differently by two workers, and two runs of the promotion gate scored the fused
model 0.654 and 0.689 on one split. Ties are not rare: a lexical model that
matched nothing is near-uniform. Each process here has a different hash seed.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

PROBE = """
import sys
sys.path.insert(0, {root!r})
from services.api.engine.classifier import LABELS, FusedStageClassifier, StagePrediction

class Flat:
    backend = "flat"
    checkpoint_backed = False
    def predict(self, *args, **kwargs):
        dist = {{label: 1 / len(LABELS) for label in LABELS}}
        return StagePrediction(LABELS[0], dist[LABELS[0]], dist, "flat")

print(FusedStageClassifier(Flat(), Flat()).predict("anything").label)
"""


def test_a_tie_is_broken_the_same_way_in_every_process() -> None:
    labels = set()
    for seed in ("1", "2", "3", "4", "5", "6"):
        out = subprocess.run(
            [sys.executable, "-c", PROBE.format(root=str(ROOT))],
            env={**os.environ, "PYTHONHASHSEED": seed},
            capture_output=True, text=True, check=True,
        )
        labels.add(out.stdout.strip().splitlines()[-1])
    assert len(labels) == 1, f"one input, several labels across processes: {sorted(labels)}"


def test_the_tie_goes_to_the_first_label_in_the_taxonomy() -> None:
    from services.api.engine.classifier import LABELS

    out = subprocess.run(
        [sys.executable, "-c", PROBE.format(root=str(ROOT))],
        capture_output=True, text=True, check=True,
    )
    assert out.stdout.strip().splitlines()[-1] == LABELS[0]
