"""
AegisAI scam feature extraction — the spec's Section 5.

    A. callflow.py         call-flow sequence features
    B. script_templates.py scam script template matching
    C. spoofing.py         number-spoofing intelligence
    D. video.py            video-call intelligence
    E. linguistic.py       linguistic features
    F. behaviour.py        behavioural features
    G. emotion.py          emotional features

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
from .script_templates import ScriptMatchOut, match_templates
from .spoofing import SpoofingOut, analyze_number
from .video import VideoOut, analyze_video

__all__ = [
    "BehaviourFeatures",
    "BehaviourTracker",
    "CallFlowFeatures",
    "CallFlowTracker",
    "EmotionFeatures",
    "EmotionTracker",
    "LinguisticFeatures",
    "ScriptMatchOut",
    "SpoofingOut",
    "VideoOut",
    "analyze_number",
    "analyze_video",
    "extract_linguistic",
    "match_templates",
]
