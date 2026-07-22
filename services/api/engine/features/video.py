"""
D. Video-call intelligence.

The spec marks this "Future deployment", and this module is built to that
description honestly: the metadata half is implemented and useful today, the
frame-analysis half is a declared interface with `available=False` behind it.

Why the split is drawn there
----------------------------
Video call *metadata* — which platform, whether screen sharing is on, whether
a document was shared — is available from any calling integration and is
genuinely diagnostic. The digital-arrest tactic depends on a video call
specifically, because a uniform and a backdrop do work that a voice cannot.

Frame analysis — uniform detection, fake ID recognition, government logo
matching — needs a vision model, labelled Indian police-uniform data, and a
false-positive budget nobody has measured. Shipping a confident "fake ID
detected" from an unvalidated classifier would be worse than shipping nothing:
it would be a claim the user cannot check, attached to an accusation.

So the frame hooks exist, are wired, and report `available=False` until a real
model is attached. If OCR is installed, text extracted from a shared document
*is* analysed, because that path reuses the OCR adapter that already exists and
carries its own confidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#: Platforms a digital-arrest operation actually uses. Skype dominates because
#: it allows calls from an unverified account to an arbitrary number, and its
#: interface superficially resembles an official system to a non-technical user.
_SCAM_LEANING_PLATFORMS = {
    "skype": "Skype is the platform most digital-arrest operations run on — it "
             "allows unverified accounts to place calls and looks official enough "
             "to pass at a glance.",
    "whatsapp": "A video call over WhatsApp carries no verified identity. No "
                "Indian agency conducts proceedings this way.",
    "telegram": "Telegram provides no caller verification at all.",
    "botim": "BOTIM is a consumer VoIP app with no identity verification.",
}

_LEGITIMATE_PLATFORMS = {"zoom", "google meet", "meet", "teams", "webex"}

#: Text patterns that appear on the fake documents shown during these calls.
#: Matched against OCR output from a shared screen or document, never inferred
#: from the video itself.
_DOCUMENT_MARKERS = [
    (r"\b(arrest|search) warrant\b", "Warrant document displayed", 0.9),
    (r"\bnon[- ]?bailable\b", "Non-bailable offence notice displayed", 0.85),
    (r"\b(cbi|central bureau of investigation)\b", "CBI letterhead displayed", 0.8),
    (r"\benforcement directorate\b", "ED letterhead displayed", 0.8),
    (r"\bnarcotics control bureau\b", "NCB letterhead displayed", 0.8),
    (r"\b(fir|first information report)\s*(no|number|#)", "FIR document displayed", 0.75),
    (r"\bsupreme court|high court\b", "Court document displayed", 0.7),
    (r"\bsection \d+.{0,20}(ipc|crpc|ndps|pmla)\b", "Legal-section citation displayed", 0.7),
    (r"\b(government of india|bharat sarkar|भारत सरकार)\b", "Government emblem/heading displayed", 0.65),
    (r"\baadhaar\b.{0,30}\b\d{4}\s?\d{4}\s?\d{4}\b", "Aadhaar number displayed on document", 0.6),
]

_COMPILED = [(re.compile(p, re.I), label, weight) for p, label, weight in _DOCUMENT_MARKERS]


@dataclass
class VideoOut:
    available: bool = False
    fake_id_detected: bool | None = None
    uniform_detected: bool | None = None
    government_logo_detected: bool | None = None
    ocr_text: str | None = None
    meeting_platform: str | None = None
    confidence: float = 0.0
    notes: list[str] = field(default_factory=list)


def analyze_video(
    metadata: dict | None = None,
    *,
    shared_document_text: str | None = None,
) -> VideoOut:
    """Assess the video channel from metadata and any shared-document OCR."""
    meta = metadata or {}
    out = VideoOut()

    platform = str(meta.get("platform") or "").strip().lower() or None
    is_video = bool(meta.get("is_video")) or bool(meta.get("video_call"))

    if not is_video and not shared_document_text:
        out.notes.append("No video channel on this session.")
        return out

    out.available = True
    out.meeting_platform = platform
    weights: list[float] = []

    if platform and platform in _SCAM_LEANING_PLATFORMS:
        out.notes.append(_SCAM_LEANING_PLATFORMS[platform])
        weights.append(0.55)
    elif platform in _LEGITIMATE_PLATFORMS:
        out.notes.append(
            f"Video over {platform}, which is commonly used legitimately. The "
            "platform is not itself a signal here."
        )

    # A video call that the caller insists stays connected is the mechanical
    # signature of the "digital arrest" hold.
    duration = meta.get("call_duration_s", meta.get("duration_s"))
    if isinstance(duration, (int, float)) and duration > 1200:
        out.notes.append(
            f"Video call sustained for {duration / 60:.0f} minutes. Prolonged "
            "mandatory video contact is the defining mechanic of a digital arrest."
        )
        weights.append(0.6)

    if meta.get("screen_sharing"):
        out.notes.append(
            "Screen sharing is active. In this scam pattern that is used either "
            "to display a forged document or to watch the victim complete a "
            "transfer."
        )
        weights.append(0.5)

    if meta.get("remote_access") or meta.get("remote_control"):
        out.notes.append(
            "Remote access to the victim's device is active. No institution ever "
            "requires this, and it permits transfers the victim never authorises."
        )
        weights.append(0.95)

    # --- Shared-document analysis (real, when OCR produced text) ---------
    if shared_document_text:
        out.ocr_text = shared_document_text[:2000]
        hits = [
            (label, weight)
            for pattern, label, weight in _COMPILED
            if pattern.search(shared_document_text)
        ]
        if hits:
            out.government_logo_detected = any(
                "letterhead" in label or "emblem" in label for label, _ in hits
            )
            out.fake_id_detected = any(
                "warrant" in label.lower() or "FIR" in label for label, _ in hits
            )
            for label, weight in hits:
                out.notes.append(
                    f"{label}. Documents shown on a video call are images, not "
                    "verified records — anyone can produce one."
                )
                weights.append(weight)

    # Frame-level vision checks are not implemented. Reported as unknown rather
    # than False so the UI can distinguish "checked and clean" from "not run".
    if out.uniform_detected is None:
        out.notes.append(
            "Uniform and photo-ID frame analysis is not implemented in this "
            "build; only metadata and shared-document text were assessed."
        )

    if weights:
        product = 1.0
        for w in weights:
            product *= (1.0 - w)
        out.confidence = round(1.0 - product, 3)
    return out


def status() -> dict:
    return {
        "frame_analysis": False,
        "metadata_analysis": True,
        "document_ocr": True,
        "note": "Frame-level vision checks are declared but not implemented.",
    }
