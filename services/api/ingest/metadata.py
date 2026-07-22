"""
Call-envelope metadata extraction.

Everything here is derived from how the call arrived rather than what was said.
That independence is the point: metadata corroborates the content classifier
without sharing its failure modes. A scammer can rewrite their script freely,
but the routing, the number shape, and the hour of the call are constrained by
infrastructure they do not fully control.

Kept separate from `engine/spoofing.py`, which scores the *number*. This module
handles the rest of the envelope — platform, device, timing, contact history —
and hands a normalised structure to the spoofing analyser rather than
duplicating its logic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Optional

#: Outside these hours an unsolicited call claiming to be an institution is
#: anomalous. Indian government offices and bank call centres do not initiate
#: contact at 2am; scam operations run around the clock and frequently target
#: the small hours precisely because the victim is disoriented and alone.
BUSINESS_START = time(8, 0)
BUSINESS_END = time(21, 0)

#: Platforms that carry no verified caller identity at all. Not suspicious on
#: their own — hundreds of millions of legitimate calls run over them — but a
#: *government agency* contacting a citizen over WhatsApp is procedurally wrong
#: in a way that a phone call is not.
UNVERIFIED_PLATFORMS = {"whatsapp", "telegram", "signal", "skype", "imo", "botim", "duo"}

VIDEO_PLATFORMS = {"skype", "zoom", "google meet", "meet", "teams", "whatsapp", "duo", "botim"}


@dataclass
class EnvelopeIntel:
    platform: Optional[str] = None
    device: Optional[str] = None
    call_duration_s: Optional[float] = None
    started_at: Optional[str] = None
    off_hours: bool = False
    prior_contacts: int = 0
    historical_complaints: int = 0
    is_video: bool = False
    unverified_platform: bool = False
    routing_notes: list[str] = field(default_factory=list)
    #: 0-1 contribution to the fused threat score.
    risk_contribution: float = 0.0


def _parse_timestamp(value: object) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value))
        except (OSError, OverflowError, ValueError):
            return None
    if isinstance(value, str):
        text = value.strip().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M", "%Y-%m-%dT%H:%M:%S"):
                try:
                    return datetime.strptime(text, fmt)
                except ValueError:
                    continue
    return None


def _is_off_hours(when: datetime) -> bool:
    return not (BUSINESS_START <= when.time() <= BUSINESS_END)


def extract(metadata: dict | None) -> EnvelopeIntel:
    """Normalise a free-form metadata dict into structured envelope intel.

    Accepts whatever the caller supplies — the shape varies by integration —
    and never raises on a missing or malformed field. An absent timestamp is
    "we do not know when", not "this call happened at epoch zero".
    """
    meta = metadata or {}
    intel = EnvelopeIntel()

    platform = str(meta.get("platform") or "").strip().lower() or None
    intel.platform = platform
    intel.device = str(meta.get("device") or "").strip() or None

    duration = meta.get("call_duration_s", meta.get("duration_s"))
    if isinstance(duration, (int, float)) and duration >= 0:
        intel.call_duration_s = float(duration)

    when = _parse_timestamp(meta.get("timestamp") or meta.get("started_at"))
    if when is not None:
        intel.started_at = when.isoformat()
        intel.off_hours = _is_off_hours(when)
        if intel.off_hours:
            intel.routing_notes.append(
                f"Contact at {when.strftime('%H:%M')} — outside the hours any "
                "institution initiates contact."
            )

    for key in ("prior_contacts", "call_frequency", "contact_count"):
        value = meta.get(key)
        if isinstance(value, (int, float)):
            intel.prior_contacts = max(intel.prior_contacts, int(value))

    complaints = meta.get("historical_complaints", meta.get("reported_count"))
    if isinstance(complaints, (int, float)):
        intel.historical_complaints = int(complaints)
        if intel.historical_complaints > 0:
            intel.routing_notes.append(
                f"This number has {intel.historical_complaints} prior complaint(s) "
                "on record."
            )

    if platform:
        intel.unverified_platform = platform in UNVERIFIED_PLATFORMS
        intel.is_video = bool(meta.get("is_video")) or platform in VIDEO_PLATFORMS
        if intel.unverified_platform:
            intel.routing_notes.append(
                f"Contact over {platform}, which carries no verified caller identity."
            )

    for note_key in ("routing", "network_routing", "carrier_notes"):
        note = meta.get(note_key)
        if isinstance(note, str) and note.strip():
            intel.routing_notes.append(note.strip())
        elif isinstance(note, list):
            intel.routing_notes.extend(str(n) for n in note if str(n).strip())

    intel.risk_contribution = _score(intel)
    return intel


def _score(intel: EnvelopeIntel) -> float:
    """Fold the envelope into a single 0-1 risk contribution.

    Weights are small on purpose. Metadata is corroborating evidence, never
    dispositive — plenty of legitimate calls arrive over WhatsApp at 10pm, and
    a system that treats that as proof of fraud will cry wolf constantly. The
    weight it carries in fusion is capped correspondingly low.
    """
    score = 0.0
    if intel.off_hours:
        score += 0.25
    if intel.unverified_platform:
        score += 0.20
    if intel.historical_complaints > 0:
        # Saturating rather than linear: the difference between 1 and 3 prior
        # complaints matters much more than between 20 and 40.
        score += min(0.35, 0.15 * intel.historical_complaints)
    if intel.prior_contacts >= 5:
        score += 0.15
        intel.routing_notes.append(
            f"{intel.prior_contacts} contacts from this number — repeated approach."
        )
    # A very long call is itself a digital-arrest signature: the whole tactic
    # depends on keeping the victim on the line for an extended period.
    if intel.call_duration_s and intel.call_duration_s > 1800:
        score += 0.15
        intel.routing_notes.append(
            f"Call has run {intel.call_duration_s / 60:.0f} minutes — prolonged "
            "contact is characteristic of a digital-arrest hold."
        )
    return round(min(1.0, score), 3)
