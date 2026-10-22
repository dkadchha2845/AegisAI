"""
AegisAI scam feature extraction — the spec's Section 5.

    A. callflow.py         call-flow sequence features
    E. linguistic.py       linguistic features
    F. behaviour.py        behavioural features
    G. emotion.py          emotional features

Sections B (script templates), C (number spoofing) and D (video) were removed
in T-71 (audit D-02). Nothing imported them: B and C duplicated the serving
modules `engine/scripts.py` and `engine/spoofing.py`, which are what every
path uses, and D analysed video, which is out of scope. Git history keeps them.
The four that remain are off the serving path too, but the RSSIE training
pipeline (`ml/training/rssie/dataset.py`) builds its behavioural vectors from
them, so they stay.

The spec calls this layer "the heart of your novelty", and the distinction it
draws is the one this package is organised around: these are *Digital Arrest-
specific* features, not generic NLP. A sentiment score or a TF-IDF vector would
describe the text. These describe the scam.

Each extractor is independent and side-effect free, and none of them imports
another. That is what makes the fusion downstream meaningful — signals that
share an input share a failure mode, and averaging two views of the same
evidence produces confidence rather than corroboration.
"""

from .behaviour import BehaviourFeatures, BehaviourTracker
from .callflow import CallFlowFeatures, CallFlowTracker
from .emotion import EmotionFeatures, EmotionTracker
from .linguistic import LinguisticFeatures, extract_linguistic

__all__ = [
    "BehaviourFeatures",
    "BehaviourTracker",
    "CallFlowFeatures",
    "CallFlowTracker",
    "EmotionFeatures",
    "EmotionTracker",
    "LinguisticFeatures",
    "extract_linguistic",
]
