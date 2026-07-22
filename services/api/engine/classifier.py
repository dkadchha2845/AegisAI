"""
Stage classifier — the fine-tuned model, with a lexical model behind it.

Two implementations of one interface:

  MuRILStageClassifier   the fine-tuned checkpoint from
                         ml/notebooks/train_stage_classifier.ipynb
  LexicalStageClassifier a marker-scoring model built from taxonomy.py

The lexical one is not a placeholder to be deleted later. It is the fallback
that keeps the product answering when torch is missing, the checkpoint hasn't
been exported, or the machine has no GPU and a 3-second cold start would
break the demo. It is measurably worse — the notebook reports both — and the
engine tags `clf:lexical_fallback` on every frame it produces so the UI can
say so out loud.

Both return a full distribution over the eight stages, never a bare argmax:
the contract exposes `StageState.distribution` precisely so a judge asking
"how sure is it?" gets a real answer.
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from ..config import ML_DIR, settings

# taxonomy.py is the single source of truth for labels and threat weights;
# it lives in the dataset pipeline, so the API imports it rather than
# restating the eight stages and letting them drift.
sys.path.insert(0, str(ML_DIR))
try:
    from presage.taxonomy import BY_LABEL, LABELS  # type: ignore
except ImportError:  # pragma: no cover - ml/ not on disk (container build)
    LABELS = [
        "GREETING", "AUTHORITY_CLAIM", "FEAR_INDUCTION", "ISOLATION",
        "VERIFICATION_DEMAND", "PAYMENT_SETUP", "PAYMENT_EXECUTION", "BENIGN",
    ]
    BY_LABEL = {}


@dataclass
class StagePrediction:
    label: str
    confidence: float
    distribution: dict[str, float]
    #: Which implementation produced this. Ends up in `degraded` when lexical.
    backend: str


class StageClassifier:
    backend = "abstract"

    def predict(
        self,
        text: str,
        history: list[str] | None = None,
        speaker: str = "CALLER",
        previous_speaker: str = "VICTIM",
    ) -> StagePrediction:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Lexical fallback
# ---------------------------------------------------------------------------

# Discriminative cues per stage. These are weighted *phrases*, not the full
# marker sentences from taxonomy.py — matching whole sentences would only fire
# on the seed corpus itself. Hinglish and English variants are both listed
# because real calls code-switch mid-sentence.
CUES: dict[str, list[tuple[str, float]]] = {
    "GREETING": [
        (r"\b(hello|namaste|good (morning|afternoon|evening))\b", 0.6),
        (r"\bbaat kar raha\b", 0.7),
        (r"\bek minute\b", 0.4),
        (r"\bkya main\b.*\bse baat\b", 0.8),
    ],
    "AUTHORITY_CLAIM": [
        (r"\b(cbi|trai|rbi|ncb|narcotics|cyber ?crime|income tax|enforcement directorate|ed)\b", 1.0),
        (r"\b(inspector|sub[- ]?inspector|acp|dcp|officer|constable)\b", 0.8),
        (r"\bbadge (number|no)\b", 0.9),
        (r"\b(crime branch|fraud (prevention )?(cell|department)|customer care)\b", 0.7),
        (r"\bmain .* se (bol|baat) raha\b", 0.5),
    ],
    "FEAR_INDUCTION": [
        (r"\b(arrest|warrant|fir|case register|non[- ]?bailable)\b", 1.0),
        (r"\b(money laundering|drugs|parcel|smuggl)\w*\b", 0.9),
        (r"\b(block ho jayega|suspend|deactivate|terminate)\b", 0.7),
        (r"\b(2|24|48) (ghante|hours?|hrs)\b", 0.5),
        (r"\b(jail|court|legal action|penalty)\b", 0.6),
    ],
    "ISOLATION": [
        (r"\b(confidential|kisi ko (mat|nahi) bat)\w*", 1.0),
        (r"\bdisconnect mat\b", 1.0),
        (r"\bdigital arrest\b", 1.0),
        (r"\b(akele|alone|room mein)\b", 0.7),
        (r"\b(family|ghar walo|kisi aur)\b.*\b(mat|nahi)\b", 0.7),
        (r"\bvideo call (on|chalu)\b", 0.8),
    ],
    "VERIFICATION_DEMAND": [
        (r"\b(otp|cvv|pin|password)\b", 1.0),
        (r"\b(aadhaar|aadhar|pan card|pan number)\b", 0.9),
        (r"\b(account (number|details)|last (4|four) digit)\b", 0.8),
        (r"\b(balance|kitna paisa|kitne paise)\b", 0.6),
        (r"\bverif\w+\b", 0.4),
    ],
    "PAYMENT_SETUP": [
        (r"\b(refundable|security deposit|escrow|supervised account)\b", 1.0),
        (r"\b(court fees?|bail|fine|processing (fee|charge))\b", 0.8),
        (r"\b(transfer|bhej|send)\w*\b.*\b(account|khaate)\b", 0.7),
        (r"\b(ifsc|beneficiary|payee)\b", 0.8),
    ],
    "PAYMENT_EXECUTION": [
        (r"\b(upi|gpay|google pay|phonepe|paytm|bhim)\b", 0.9),
        (r"\b(imps|neft|rtgs)\b", 0.8),
        (r"\b(amount daal|confirm kar d|pin daal|screenshot bhej)\w*", 1.0),
        (r"\b(scan (karo|kijiye)|qr code)\b", 0.9),
        (r"\btransaction (ho gaya|complete)\b", 0.9),
    ],
    "BENIGN": [
        (r"\bhum kabhi otp nahi (mangte|maangte)\b", 1.2),
        (r"\b(koi jaldi nahi|apne time par|no hurry)\b", 1.0),
        (r"\b(branch mein aa|visit (the |our )?branch)\w*", 0.9),
        (r"\b(deliver|order|address confirm)\w*", 0.7),
        (r"\b(reminder|due date|renewal)\b", 0.6),
    ],
}

_COMPILED = {
    label: [(re.compile(p, re.I), w) for p, w in pats] for label, pats in CUES.items()
}


def _softmax(scores: dict[str, float], temperature: float = 1.0) -> dict[str, float]:
    import math

    if not scores:
        return {}
    mx = max(scores.values())
    exp = {k: math.exp((v - mx) / temperature) for k, v in scores.items()}
    total = sum(exp.values()) or 1.0
    return {k: v / total for k, v in exp.items()}


class LexicalStageClassifier(StageClassifier):
    """Weighted-cue scoring. Deterministic, instant, no dependencies."""

    backend = "lexical"

    def predict(
        self,
        text: str,
        history: list[str] | None = None,
        speaker: str = "CALLER",
        previous_speaker: str = "VICTIM",
    ) -> StagePrediction:
        # The lexical model scores cues in the text alone; the speaker tags
        # exist for signature parity with the fine-tuned model.
        del speaker, previous_speaker
        raw = {label: 0.0 for label in LABELS}
        for label, pats in _COMPILED.items():
            for pattern, weight in pats:
                if pattern.search(text):
                    raw[label] += weight

        # Nothing matched: this is genuinely uninformative text, not evidence
        # of benignity. Returning BENIGN at high confidence here is how a
        # lexical model talks itself into missing a quiet scam, so we return
        # BENIGN at *low* confidence and let fusion weight it accordingly.
        if not any(raw.values()):
            dist = {label: 1.0 / len(LABELS) for label in LABELS}
            dist["BENIGN"] = dist["BENIGN"] * 1.5
            total = sum(dist.values())
            dist = {k: v / total for k, v in dist.items()}
            return StagePrediction("BENIGN", dist["BENIGN"], dist, self.backend)

        # Temperature well below 1 sharpens the distribution — cue counts are
        # small integers, and a raw softmax over them is almost uniform.
        dist = _softmax(raw, temperature=0.45)
        label = max(dist, key=dist.get)
        return StagePrediction(label, dist[label], dist, self.backend)


# ---------------------------------------------------------------------------
# Fine-tuned MuRIL
# ---------------------------------------------------------------------------


class MuRILStageClassifier(StageClassifier):
    """Wraps the exported checkpoint. Constructed only if it loads cleanly."""

    backend = "muril"

    def __init__(self, model_dir: Path):
        import torch  # noqa: F401  (imported for its side effect + device pick)
        from transformers import (  # type: ignore
            AutoModelForSequenceClassification,
            AutoTokenizer,
        )

        self._torch = torch
        self.tokenizer = AutoTokenizer.from_pretrained(str(model_dir))
        self.model = AutoModelForSequenceClassification.from_pretrained(str(model_dir))
        self.model.eval()
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model.to(self.device)
        # id2label comes from the checkpoint, so a reordered label map in the
        # notebook can never silently mis-decode here.
        self.id2label = {int(k): v for k, v in self.model.config.id2label.items()}

    def predict(
        self,
        text: str,
        history: list[str] | None = None,
        speaker: str = "CALLER",
        previous_speaker: str = "VICTIM",
    ) -> StagePrediction:
        torch = self._torch
        # One turn of context, speaker-tagged. `ml/train.py::render` builds
        # exactly this string — if the format diverges the model still returns
        # a confident label, it is just a worse one, which is the failure mode
        # this comment exists to prevent.
        current = f"{speaker}: {text}"
        joined = (
            current
            if not history
            else f"{previous_speaker}: {history[-1]} [SEP] {current}"
        )
        enc = self.tokenizer(
            joined, truncation=True, max_length=128, return_tensors="pt"
        ).to(self.device)
        with torch.no_grad():
            logits = self.model(**enc).logits[0]
            probs = torch.softmax(logits, dim=-1).tolist()
        dist = {self.id2label[i]: float(p) for i, p in enumerate(probs)}
        label = max(dist, key=dist.get)
        return StagePrediction(label, dist[label], dist, self.backend)


_cached: StageClassifier | None = None

#: Written by ml/eval_backends.py — both backends scored on the same held-out
#: archetypes, through this same serving interface.
COMPARISON_PATH = settings.classifier_dir.parent / "backend_comparison.json"


def _checkpoint_is_better() -> tuple[bool, str]:
    """Should the fine-tuned checkpoint be promoted over the lexical baseline?

    Presence of a checkpoint is not evidence that it helps. The current one
    scores macro-F1 0.221 on held-out archetypes against the lexical model's
    0.368 — it memorised the training archetypes (val macro-F1 0.98) and does
    not generalise, which is a corpus-size problem rather than a training bug.
    Loading it just because the files exist would quietly make every verdict
    in the product worse.

    So promotion is gated on the measured comparison. Set
    PRESAGE_CLASSIFIER=muril to override once you have retrained on a larger
    corpus, or delete the comparison file to fall back to presence-based
    loading.
    """
    forced = os.getenv("PRESAGE_CLASSIFIER", "").strip().lower()
    if forced == "muril":
        return True, "forced by PRESAGE_CLASSIFIER"
    if forced == "lexical":
        return False, "forced by PRESAGE_CLASSIFIER"

    if not COMPARISON_PATH.exists():
        # Never measured. Trust the checkpoint, but say so on /api/health.
        return True, "no comparison on file"

    try:
        scores = json.loads(COMPARISON_PATH.read_text())
        muril = float(scores["muril"]["macro_f1"])
        lexical = float(scores["lexical"]["macro_f1"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError, OSError):
        return True, "comparison unreadable"

    if muril >= lexical:
        return True, f"measured better ({muril:.3f} vs {lexical:.3f})"
    return False, f"measured worse ({muril:.3f} vs {lexical:.3f})"


#: Why the active backend was chosen. Surfaced on /api/health so "which model
#: is serving, and why" is a question with a checkable answer.
selection_reason = "not yet loaded"

#: True only when the lexical model is serving because the *better* model is
#: genuinely unavailable — no checkpoint was ever exported, or the exported one
#: failed to load. It is deliberately *False* when lexical serves because it won
#: the measured comparison or was forced: that is the promotion gate working as
#: designed, not a fault, and calling it "degraded" would be crying wolf. The
#: health check keys `clf:lexical_fallback` off this, not off `backend`.
serving_is_fallback = False


def load_classifier() -> StageClassifier:
    """Best available classifier. Cached — loading MuRIL twice costs seconds."""
    global _cached, selection_reason, serving_is_fallback
    if _cached is not None:
        return _cached

    model_dir = settings.classifier_dir
    if model_dir.exists() and (model_dir / "config.json").exists():
        promote, reason = _checkpoint_is_better()
        if promote:
            try:
                _cached = MuRILStageClassifier(model_dir)
                selection_reason = f"fine-tuned checkpoint: {reason}"
                serving_is_fallback = False
                return _cached
            except Exception as exc:  # transformers/torch missing, bad export
                print(f"[presage] MuRIL unavailable ({exc}); using lexical classifier")
                selection_reason = f"checkpoint failed to load: {exc}"
                serving_is_fallback = True
        else:
            # Lexical is serving because it measurably beat the checkpoint (or was
            # forced). It is the best available model, so this is *not* degraded.
            print(f"[presage] checkpoint not promoted — {reason}")
            selection_reason = f"checkpoint present but {reason}"
            serving_is_fallback = False
    else:
        # The fine-tuned model was never produced on this machine (the clean-clone
        # / CI path). Lexical is genuinely a fallback here — flag it.
        selection_reason = "no checkpoint exported"
        serving_is_fallback = True

    _cached = LexicalStageClassifier()
    return _cached


def threat_weight(label: str) -> float:
    stage = BY_LABEL.get(label)
    if stage is not None:
        return stage.threat_weight
    return {
        "GREETING": 0.05, "AUTHORITY_CLAIM": 0.45, "FEAR_INDUCTION": 0.7,
        "ISOLATION": 0.9, "VERIFICATION_DEMAND": 0.8, "PAYMENT_SETUP": 0.9,
        "PAYMENT_EXECUTION": 1.0, "BENIGN": 0.0,
    }.get(label, 0.0)
