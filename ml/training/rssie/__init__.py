"""
AegisAI Module 1 — RSSIE model package.

The spec's Section 6: a shared MuRIL encoder feeding a BiLSTM/lightweight
transformer sequence head, with a multi-head classifier producing scam
probability, scam type, current stage, and financial transfer risk.

Separate from `ml/training/train.py`, which trains the single-head stage classifier that
`services/api/engine/classifier.py` already serves. That model is untouched:
it is the fallback path, it is what the existing regression suite covers, and
replacing it in the same change as adding four new heads would make any
regression impossible to attribute.
"""

from .labels import (
    SCAM_TYPES,
    STAGES,
    scam_type_of_archetype,
    transfer_risk_of_stage,
)

__all__ = [
    "SCAM_TYPES",
    "STAGES",
    "scam_type_of_archetype",
    "transfer_risk_of_stage",
]
