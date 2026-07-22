"""
Artifact analyzer — the "is this a scam?" path.

Whatever the user uploads (a pasted SMS, a call transcript, a UPI ID, a QR
payload, a chat export, a .txt/.json/.csv file) is normalised into utterances
and run through the same engine that scores a live call: the same classifier,
the same threat fusion, the same knowledge base. Two paths that disagree about
what counts as a scam would be two products, and the one the judge did not see
would be the one that was wrong.

The output is deliberately shaped like a small audit rather than a verdict:
a score, the labelled utterances that produced it, named drivers, the
mechanical checks that fired, cited sources, and what to do next. A binary
SCAM/NOT-SCAM with no reasoning is a coin flip the user cannot check.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field

from ..rag.coach import get_coach
from ..rag.store import get_kb
from .classifier import load_classifier
from .coercion import CoercionTracker
from .passport import TrustPassport
from .scripts import get_script_matcher
from .spoofing import analyze_number
from .threat import ManipulationAccumulator, fuse, level_of
from .upi import Finding, analyze_payment_framing, analyze_upi

MAX_UTTERANCES = 400

#: Passport checks that settle the question by themselves, and how hard.
#: These are mechanical facts about what institutions do, not correlations —
#: which is why they are allowed to override a low fused score rather than
#: being averaged into it. Checks absent from this map (call-back tolerance,
#: claimed identity) are real signals but not conclusive alone, so they stay
#: in the weighted sum where they belong.
DISPOSITIVE_CHECKS: dict[str, float] = {
    "Credential request": 1.0,
    "Procedural plausibility": 0.95,
    "Secrecy demand": 0.9,
    "Payment to individual": 0.8,
}

#: Number-spoofing checks strong enough to settle the verdict on their own, and
#: how hard. Kept deliberately short: a reported number, or an authority claim
#: delivered from a personal/foreign number, is dispositive. VoIP, format, and
#: frequency are real signals but *not* conclusive alone — legitimate
#: businesses use VoIP — so they stay in the fusion weight where a false
#: positive cannot be manufactured from metadata that any real caller might have.
DISPOSITIVE_SPOOF_CHECKS: dict[str, float] = {
    "Reported number": 0.9,
    "Caller-ID vs claimed authority": 0.8,
    "International routing": 0.7,
}


@dataclass
class LabelledLine:
    index: int
    speaker: str
    text: str
    stage: str
    confidence: float
    distribution: dict[str, float]


@dataclass
class AnalysisResult:
    kind: str                      # text | transcript | sms | upi | file
    score: float
    level: str
    verdict: str                   # LIKELY_SCAM | SUSPICIOUS | LIKELY_LEGITIMATE | INSUFFICIENT
    summary: str
    lines: list[LabelledLine] = field(default_factory=list)
    drivers: list[dict] = field(default_factory=list)
    findings: list[dict] = field(default_factory=list)
    manipulation_map: dict[str, float] = field(default_factory=dict)
    stages_seen: list[str] = field(default_factory=list)
    trust_passport: dict | None = None
    coach: dict | None = None
    citations: list[str] = field(default_factory=list)
    recommended_actions: list[str] = field(default_factory=list)
    degraded: list[str] = field(default_factory=list)
    upi: dict | None = None
    number_intel: dict | None = None


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

#: "Caller: text", "[00:12] AGENT — text", "> text". Speaker labels vary
#: wildly across the formats people actually paste in, so the parser accepts
#: a family of them and falls back to alternating speakers rather than
#: refusing input it half-understands.
_SPEAKER_RE = re.compile(
    r"^\s*(?:\[?\d{1,2}:\d{2}(?::\d{2})?\]?\s*)?"
    r"(caller|scammer|agent|fraudster|them|unknown|victim|me|you|user|customer)"
    r"\s*[:\-–—]\s*(.+)$",
    re.I,
)

_CALLER_WORDS = {"caller", "scammer", "agent", "fraudster", "them", "unknown"}


def normalise(raw: str) -> list[tuple[str, str]]:
    """Turn free text into (speaker, text) pairs."""
    # A JSON transcript export — accept it directly rather than making the
    # user reformat something the system itself produced.
    stripped = raw.strip()
    if stripped.startswith("[") or stripped.startswith("{"):
        try:
            blob = json.loads(stripped)
            items = blob if isinstance(blob, list) else blob.get("utterances", [])
            pairs = []
            for item in items:
                if isinstance(item, dict) and item.get("text"):
                    speaker = str(item.get("speaker", "CALLER")).upper()
                    pairs.append(
                        ("VICTIM" if speaker in {"VICTIM", "ME", "USER"} else "CALLER",
                         str(item["text"]))
                    )
            if pairs:
                return pairs[:MAX_UTTERANCES]
        except (json.JSONDecodeError, AttributeError, TypeError):
            pass  # not JSON after all; fall through to line parsing

    pairs: list[tuple[str, str]] = []
    labelled_any = False
    for line in stripped.splitlines():
        line = line.strip()
        if not line:
            continue
        match = _SPEAKER_RE.match(line)
        if match:
            labelled_any = True
            who = match.group(1).lower()
            speaker = "CALLER" if who in _CALLER_WORDS else "VICTIM"
            pairs.append((speaker, match.group(2).strip()))
        else:
            pairs.append(("CALLER", line))

    # Unlabelled multi-line text: assume it alternates, starting with the
    # caller. A single-block SMS/notice is one-sided, so it does NOT alternate —
    # instead we split it into sentences, all attributed to the caller. Without
    # this, a forwarded paragraph is classified as a single stage, and a
    # multi-stage scam whose danger sits in its last sentence ("...buy gift cards
    # and read me the codes") is scored on its opening line alone. The sentence
    # splitter is language-aware — Devanagari danda as well as ./!/? — so a Hindi
    # or English paste both fan out into per-sentence stages.
    if not labelled_any and len(pairs) == 1:
        sentences = _split_sentences(pairs[0][1])
        if len(sentences) > 1:
            pairs = [("CALLER", s) for s in sentences]
    elif not labelled_any and len(pairs) > 1:
        pairs = [
            ("CALLER" if i % 2 == 0 else "VICTIM", text)
            for i, (_, text) in enumerate(pairs)
        ]
    return pairs[:MAX_UTTERANCES]


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?।])\s+|\s*[\n;]+\s*")


def _split_sentences(text: str) -> list[str]:
    """Sentence-ish chunks for a one-sided block. Conservative: only splits on
    real sentence terminators, so a phone number or UPI id is never torn apart."""
    parts = [p.strip() for p in _SENTENCE_SPLIT.split(text) if p and len(p.strip()) >= 3]
    return parts or [text]


def looks_like_upi(text: str) -> bool:
    stripped = text.strip()
    if stripped.lower().startswith("upi:"):
        return True
    return bool(re.fullmatch(r"[a-zA-Z0-9._\-]{2,256}@[a-zA-Z][a-zA-Z0-9]{1,63}", stripped))


def extract_upi_ids(text: str) -> list[str]:
    """VPAs mentioned anywhere in a body of text. Excludes email addresses,
    which share the shape — the discriminator is a TLD-looking suffix."""
    out = []
    for candidate in re.findall(r"\b[a-zA-Z0-9._\-]{2,64}@[a-zA-Z][a-zA-Z0-9]{1,63}\b", text):
        suffix = candidate.split("@")[1].lower()
        if "." in candidate.split("@")[1] or suffix in {"gmail", "yahoo", "outlook", "hotmail"}:
            continue
        out.append(candidate)
    return out


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


def _verdict_of(score: float, resolved_evidence: int) -> tuple[str, str]:
    """Verdict plus a one-line summary.

    `resolved_evidence` gates the confident answers. A two-word message that
    happens to score low is not evidence of legitimacy — it is not evidence of
    anything — and saying "looks legitimate" about it would be the single most
    harmful thing this system could do.
    """
    if resolved_evidence == 0:
        return (
            "INSUFFICIENT",
            "Not enough content to judge. Paste more of the conversation, or the "
            "full message including any payment details.",
        )
    if score >= 70:
        return (
            "LIKELY_SCAM",
            "This matches a known fraud script across several independent signals. "
            "Do not send money or share any code.",
        )
    if score >= 40:
        return (
            "SUSPICIOUS",
            "Some signals match a fraud script, but not enough to be conclusive. "
            "Verify independently before acting on anything in this message.",
        )
    return (
        "LIKELY_LEGITIMATE",
        "Nothing here matches the coercion patterns this system detects. That is "
        "not a guarantee — verify any payment request through your own app.",
    )


def analyze_text(
    raw: str,
    *,
    kind: str = "text",
    claimed_identity: str | None = None,
    caller_number: str | None = None,
) -> AnalysisResult:
    classifier = load_classifier()
    kb = get_kb()
    degraded: list[str] = list(kb.degraded)
    if classifier.backend != "muril":
        degraded.append("clf:lexical_fallback")

    # --- Bare UPI identifier: structural checks only, no narrative to score.
    if looks_like_upi(raw):
        upi = analyze_upi(raw, claimed_identity=claimed_identity)
        findings = upi.findings
        return _from_findings(
            kind="upi",
            findings=findings,
            degraded=degraded,
            upi_payload=asdict(upi),
        )

    pairs = normalise(raw)
    if not pairs:
        return AnalysisResult(
            kind=kind, score=0.0, level="CALM", verdict="INSUFFICIENT",
            summary="Nothing to analyse.", degraded=degraded,
        )

    manipulation = ManipulationAccumulator()
    coercion = CoercionTracker()
    passport = TrustPassport()
    lines: list[LabelledLine] = []
    history: list[str] = []
    stages_seen: list[str] = []
    coercion_index = 0.0
    matcher = get_script_matcher()
    script_similarity = 0.0
    script_label: str | None = None

    for i, (speaker, text) in enumerate(pairs):
        if speaker == "CALLER":
            pred = classifier.predict(text, history)
            manipulation.observe(pred.label, pred.confidence)
            passport.observe(text, speaker)
            m = matcher.match(text)
            if m.similarity > script_similarity:
                script_similarity, script_label = m.similarity, m.label
            if pred.label not in stages_seen:
                stages_seen.append(pred.label)
            lines.append(
                LabelledLine(
                    index=i, speaker=speaker, text=text, stage=pred.label,
                    confidence=round(pred.confidence, 3),
                    distribution={
                        k: round(v, 3)
                        for k, v in sorted(
                            pred.distribution.items(), key=lambda kv: -kv[1]
                        )[:3]
                    },
                )
            )
        else:
            out = coercion.observe(text)
            coercion_index = out.index
            manipulation.observe_victim(out.victim_state)
            lines.append(
                LabelledLine(
                    index=i, speaker=speaker, text=text, stage="—",
                    confidence=0.0, distribution={},
                )
            )
        history.append(text)

    passport_out = passport.snapshot()

    # A failed passport check is a mechanical finding, not just 15% of a
    # weighted sum. "Asked for an OTP" is dispositive on its own — it does not
    # become less dispositive because the rest of the message was short and
    # polite, and routing it only through the fusion weight let exactly that
    # happen: a one-line OTP demand scored 30 and read LIKELY_LEGITIMATE.
    findings: list[Finding] = [
        Finding(
            label=check.name,
            weight=DISPOSITIVE_CHECKS[check.name],
            detail=check.detail,
            source=check.source,
        )
        for check in passport_out.checks
        if check.verdict == "FAIL" and check.name in DISPOSITIVE_CHECKS
    ]

    # Payment framing + any VPAs mentioned in the body.
    findings += analyze_payment_framing(raw)
    upi_payload = None
    for vpa in extract_upi_ids(raw)[:3]:
        upi = analyze_upi(vpa, claimed_identity=passport.claimed_identity)
        findings.extend(upi.findings)
        if upi_payload is None:
            upi_payload = asdict(upi)

    # Peak stage over the whole artifact, not the last one. A message that
    # reaches ISOLATION and then chats about the weather is still an isolation
    # attempt, and scoring only the final line would miss it entirely.
    peak = max(
        (line for line in lines if line.speaker == "CALLER"),
        key=lambda line: _stage_rank(line.stage) * line.confidence,
        default=None,
    )
    # Caller-number intelligence, if a number was supplied. The claimed
    # identity comes from the caller's own words when the user did not name it.
    number_intel = None
    spoofing_risk = None
    if caller_number:
        intel = analyze_number(
            caller_number,
            claimed_identity=claimed_identity or passport.claimed_identity,
        )
        number_intel = asdict(intel)
        spoofing_risk = intel.risk
        # Fold the dispositive spoofing checks into findings so they floor the
        # score, the same way a credential request does — a foreign number
        # claiming to be the CBI is not merely 15% of a weighted sum.
        for check in intel.checks:
            if check.verdict == "FAIL" and check.name in DISPOSITIVE_SPOOF_CHECKS:
                findings.append(
                    Finding(
                        label=f"Number: {check.name}",
                        weight=DISPOSITIVE_SPOOF_CHECKS[check.name],
                        detail=check.detail,
                        source=check.source,
                    )
                )

    fusion = fuse(
        stage=peak.stage if peak else "BENIGN",
        stage_confidence=peak.confidence if peak else 0.0,
        manipulation=manipulation,
        coercion_index=coercion_index,
        trust_pct=passport_out.final_trust_pct,
        spoofing_risk=spoofing_risk,
        script_similarity=script_similarity,
        script_label=script_label,
        previous_score=0.0,
        dt_s=0.0,
    )

    # Mechanical findings escalate the score. They are checks, not
    # correlations — "asked for an OTP" does not become less dispositive
    # because the surrounding text was polite.
    score = fusion.score
    for finding in findings:
        if finding.verdict == "FAIL":
            score = max(score, 55.0 + 40.0 * finding.weight)
    score = round(min(100.0, score), 1)

    coach_out = get_coach().suggest(
        peak.stage if peak else "BENIGN",
        victim_state=coercion._victim_state(coercion_index, 0, 0, 0),
    )

    citations = _citations(findings, passport_out, coach_out, raw, kb)
    resolved = sum(1 for line in lines if line.speaker == "CALLER") + len(findings)
    verdict, summary = _verdict_of(score, resolved if len(raw.split()) >= 6 else 0)

    return AnalysisResult(
        kind=kind,
        score=score,
        level=level_of(score),
        verdict=verdict,
        summary=summary,
        lines=lines,
        drivers=[asdict(d) for d in fusion.drivers],
        findings=[asdict(f) for f in findings],
        manipulation_map=manipulation.as_dict(),
        stages_seen=stages_seen,
        trust_passport=asdict(passport_out),
        coach=asdict(coach_out) if coach_out else None,
        citations=citations,
        recommended_actions=_actions(verdict, findings),
        degraded=degraded,
        upi=upi_payload,
        number_intel=number_intel,
    )


def _stage_rank(stage: str) -> float:
    from .classifier import threat_weight

    return threat_weight(stage)


def _from_findings(
    *, kind: str, findings: list[Finding], degraded: list[str], upi_payload: dict
) -> AnalysisResult:
    """Verdict for an artifact with no narrative — a bare VPA or QR payload."""
    fails = [f for f in findings if f.verdict == "FAIL"]
    score = round(min(100.0, max((55.0 + 40.0 * f.weight for f in fails), default=10.0)), 1)
    if fails:
        verdict = "LIKELY_SCAM" if score >= 70 else "SUSPICIOUS"
        summary = fails[0].detail
    else:
        verdict = "INSUFFICIENT"
        summary = (
            "This UPI ID is structurally unremarkable. A valid-looking ID is not "
            "evidence of anything — check the registered payee name on the "
            "confirmation screen before you approve."
        )
    return AnalysisResult(
        kind=kind, score=score, level=level_of(score), verdict=verdict,
        summary=summary,
        findings=[asdict(f) for f in findings],
        citations=[f.source for f in findings if f.source],
        recommended_actions=_actions(verdict, findings),
        degraded=degraded,
        upi=upi_payload,
    )


def _citations(findings, passport_out, coach_out, raw: str, kb) -> list[str]:
    seen: list[str] = []

    def add(source: str | None) -> None:
        if source and source not in seen:
            seen.append(source)

    for finding in findings:
        add(finding.source)
    for check in passport_out.checks:
        add(check.source)
    if coach_out:
        for source in coach_out.sources:
            add(source)
    # Top up with a semantic lookup so an artifact that fired no hard rules
    # still comes back with something the user can read.
    for hit in kb.search(raw[:600], k=3):
        add(hit.chunk.source)
    return seen[:6]


def _actions(verdict: str, findings: list[Finding]) -> list[str]:
    if verdict == "LIKELY_SCAM":
        actions = [
            "Do not send money, share an OTP, or install anything they ask for.",
            "Hang up. There is no legal consequence for ending a call.",
            "Tell one other person now — isolation is what makes this work.",
            "Report on 1930 or at cybercrime.gov.in.",
        ]
        if any("Payee name" in f.label for f in findings):
            actions.insert(1, "Screenshot the payee name — it is evidence for the report.")
        return actions
    if verdict == "SUSPICIOUS":
        return [
            "Do not act on anything in this message yet.",
            "Look up the institution's number yourself and call them — never use a number the message supplies.",
            "If money has already moved, report on 1930 immediately.",
        ]
    if verdict == "INSUFFICIENT":
        return [
            "Paste the full message or more of the conversation for a real answer.",
            "If a payment is involved, include the UPI ID or the amount requested.",
        ]
    return [
        "Nothing detected — but verify any payment request in your own banking app.",
        "Remember that no institution ever needs your OTP, PIN, or CVV.",
    ]
