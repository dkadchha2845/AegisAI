"""
Call-level dataset for the RSSIE sequence model.

The unit of training here is a **whole call**, not an utterance. That is the
substantive difference from `ml/train.py` and the reason this model exists: a
sequence classifier that never sees a sequence is just a slower per-utterance
classifier.

Splits are reused verbatim, not recomputed
------------------------------------------
`ml/build_dataset.py` already produced a leave-archetypes-out split by call
skeleton, and that split is what the existing published numbers are measured
against. Re-deriving it here with a different seed would silently make the two
models incomparable and would invite exactly the leak the original split was
built to prevent. So this reads `data/processed/{train,val,test}.jsonl` and
regroups the utterances back into calls by `call_id`.

One consequence worth stating: those files are de-duplicated at the utterance
level, so a reconstructed call is missing turns that were dropped as near-
duplicates elsewhere. That is acceptable for sequence learning — the stage
*order* survives de-duplication — and it is preferable to the alternative of
reading the raw corpus and re-splitting.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
ML_DIR = HERE.parent
REPO_ROOT = ML_DIR.parent
DATA = ML_DIR / "data" / "processed"

sys.path.insert(0, str(REPO_ROOT))

from ml.kavach.labels import (  # noqa: E402
    EMOTION2ID,
    SCAMTYPE2ID,
    STAGE2ID,
    emotion_of_victim_state,
    scam_type_of_archetype,
    transfer_risk_of_stage,
)
from services.api.engine.features.behaviour import BehaviourTracker  # noqa: E402
from services.api.engine.features.callflow import CallFlowTracker  # noqa: E402
from services.api.engine.features.emotion import EmotionTracker  # noqa: E402
from services.api.engine.features.linguistic import extract_linguistic  # noqa: E402


@dataclass
class CallExample:
    call_id: str
    archetype: str
    is_scam: bool
    turns: list[dict] = field(default_factory=list)
    scam_type_id: int = 0
    #: Per-turn stage ids, aligned with `turns`.
    turn_stage_ids: list[int] = field(default_factory=list)
    #: Call-level stage = the highest-risk stage the call reached. Not the last
    #: one: a call that reached PAYMENT_SETUP and then chatted is still a
    #: payment-stage call, and labelling it by its final turn would erase that.
    stage_id: int = 0
    transfer_risk: float = 0.0
    emotion_id: int = -1  # -1 = no labelled victim turn, masked in the loss
    features: list[float] = field(default_factory=list)

    @property
    def texts(self) -> list[str]:
        return [f"{t['speaker']}: {t['text']}" for t in self.turns]


def load_split(split: str) -> list[dict]:
    path = DATA / f"{split}.jsonl"
    if not path.exists():
        raise SystemExit(
            f"No {path}. Run `python ml/build_dataset.py` first — the RSSIE "
            "model reuses that split rather than making its own."
        )
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def build_features(turns: list[dict]) -> list[float]:
    """Handcrafted feature block, computed exactly as it is at serving time.

    Importing the live extractors rather than reimplementing them is the whole
    point: a training/serving skew in these 34 numbers would be invisible in
    every metric and fatal in production. This is the same class of invariant
    that `ml/train.py` documents for its `previous [SEP] current` join.
    """
    flow = CallFlowTracker()
    behaviour = BehaviourTracker()
    emotion = EmotionTracker()
    caller_text: list[str] = []
    emotion_features = None

    for turn in turns:
        speaker, text = turn["speaker"], turn["text"]
        if speaker == "CALLER":
            flow.observe(turn["label"])
            caller_text.append(text)
        else:
            emotion_features = emotion.observe(text)
        behaviour.observe(text, speaker=speaker)

    flow_vec = flow.snapshot().vector                      # 6
    ling_vec = extract_linguistic(" ".join(caller_text)).vector  # 11
    beh_vec = behaviour.snapshot().vector                  # 8
    emo_vec = emotion_features.vector if emotion_features else [0.0] * 9  # 9

    return flow_vec + ling_vec + beh_vec + emo_vec


def group_calls(rows: list[dict]) -> list[CallExample]:
    """Regroup utterance rows back into whole calls, in turn order."""
    by_call: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_call[row["call_id"]].append(row)

    examples: list[CallExample] = []
    for call_id, turns in by_call.items():
        turns.sort(key=lambda r: r["turn_index"])
        first = turns[0]
        is_scam = bool(first["is_scam"])
        archetype = first["archetype"]

        scam_type = scam_type_of_archetype(archetype, is_scam)
        turn_stage_ids = [STAGE2ID[t["label"]] for t in turns]

        # Call-level stage = highest transfer risk reached.
        peak_stage = max(
            (t["label"] for t in turns), key=transfer_risk_of_stage, default="BENIGN"
        )

        # Call-level emotion = the last labelled victim state. The end of the
        # call is where the manipulation either succeeded or did not, so it is
        # the label that actually carries outcome information.
        emotion_id = -1
        for turn in reversed(turns):
            if turn["speaker"] == "VICTIM":
                mapped = emotion_of_victim_state(turn.get("victim_state", "NA"))
                if mapped:
                    emotion_id = EMOTION2ID[mapped]
                    break

        examples.append(
            CallExample(
                call_id=call_id,
                archetype=archetype,
                is_scam=is_scam,
                turns=turns,
                scam_type_id=SCAMTYPE2ID[scam_type],
                turn_stage_ids=turn_stage_ids,
                stage_id=STAGE2ID[peak_stage],
                transfer_risk=transfer_risk_of_stage(peak_stage),
                emotion_id=emotion_id,
                features=build_features(turns),
            )
        )
    return examples


def load_calls(split: str) -> list[CallExample]:
    return group_calls(load_split(split))


def describe(examples: list[CallExample]) -> dict:
    from collections import Counter

    from ml.kavach.labels import SCAM_TYPES, STAGES

    return {
        "calls": len(examples),
        "scam": sum(1 for e in examples if e.is_scam),
        "benign": sum(1 for e in examples if not e.is_scam),
        "mean_turns": round(
            sum(len(e.turns) for e in examples) / max(1, len(examples)), 1
        ),
        "scam_types": dict(Counter(SCAM_TYPES[e.scam_type_id] for e in examples)),
        "peak_stages": dict(Counter(STAGES[e.stage_id] for e in examples)),
        "emotion_labelled": sum(1 for e in examples if e.emotion_id >= 0),
    }


if __name__ == "__main__":
    for split in ("train", "val", "test"):
        try:
            calls = load_calls(split)
        except SystemExit as exc:
            print(exc)
            break
        print(f"\n=== {split} ===")
        for key, value in describe(calls).items():
            print(f"  {key}: {value}")
        if calls:
            print(f"  feature_dim: {len(calls[0].features)}")
