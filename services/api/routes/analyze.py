"""
Analyzer routes — the "check this for me" surface.

Everything the user can submit ends up in `engine.analyzer.analyze_text`, so
a pasted SMS, an uploaded transcript, and a scanned UPI ID are scored by
exactly one implementation. The routes differ only in how they get the text
out of the request.

Annotations here use `Optional[...]` rather than `X | None` on purpose:
FastAPI and Pydantic evaluate these at runtime, and PEP 604 unions are a
syntax error on the Python 3.9 this project currently runs on.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from .. import llm
from ..config import settings
from ..engine.analyzer import analyze_text
from ..engine.ocr import extract_text
from ..engine.upi import analyze_upi
from ..rag.store import get_kb

router = APIRouter(prefix="/api/analyze", tags=["analyze"])

#: Extensions we will read as text. Anything else is rejected with a message
#: that says what to do instead, rather than a generic 400.
TEXT_SUFFIXES = {".txt", ".json", ".csv", ".md", ".log", ".vtt", ".srt"}

#: Image types the OCR path accepts.
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".gif"}

#: Audio types the speech-to-text path accepts.
AUDIO_SUFFIXES = {".wav", ".mp3", ".m4a", ".ogg", ".flac", ".webm", ".aac"}


class TextRequest(BaseModel):
    text: str = Field(min_length=1, max_length=200_000)
    kind: str = "text"
    #: What the sender claims to be, if the user knows. Enables the strongest
    #: UPI check — claimed identity against the bank-registered payee name.
    claimed_identity: Optional[str] = None
    #: Caller number, if the artifact came from a call. Enables the number
    #: spoofing checks (Caller-ID mismatch, VoIP, international routing).
    caller_number: Optional[str] = None
    #: Ask the LLM to phrase the explanation. Off by default: the templated
    #: explanation is instant and offline, and this adds a network round trip.
    explain: bool = False


class UPIRequest(BaseModel):
    upi_id: str = Field(min_length=3, max_length=512)
    claimed_identity: Optional[str] = None


def _with_explanation(result: Dict[str, Any], wanted: bool) -> Dict[str, Any]:
    if wanted and llm.available():
        prose = llm.explain(result)
        if prose:
            result["explanation"] = prose
            result["explanation_source"] = f"llm:{settings.llm_backend}"
            return result
        # Asked for, unavailable, said so. Silently degrading to the template
        # without a word would leave the user thinking they got the good one.
        result.setdefault("degraded", []).append("llm:unavailable")
    result.setdefault("explanation", result.get("summary"))
    result.setdefault("explanation_source", "template")
    return result


@router.post("/text")
def analyze_text_route(req: TextRequest) -> Dict[str, Any]:
    """Free text: an SMS, a WhatsApp forward, a pasted transcript, a VPA."""
    result = asdict(
        analyze_text(
            req.text,
            kind=req.kind,
            claimed_identity=req.claimed_identity,
            caller_number=req.caller_number,
        )
    )
    return _with_explanation(result, req.explain)


@router.post("/upi")
def analyze_upi_route(req: UPIRequest) -> Dict[str, Any]:
    """A UPI ID, `upi://pay?...` deep link, or decoded QR payload.

    Structural checks only. There is no reputation lookup and no network call:
    a blocklist this project could ship would be stale before the demo, and a
    check the user cannot reason about is one they are right to ignore.
    """
    analysis = analyze_upi(req.upi_id, claimed_identity=req.claimed_identity)
    result = asdict(analyze_text(req.upi_id, kind="upi", claimed_identity=req.claimed_identity))
    result["upi"] = asdict(analysis)
    return result


@router.post("/file")
async def analyze_file_route(
    file: UploadFile = File(...),
    claimed_identity: Optional[str] = None,
) -> Dict[str, Any]:
    """Uploaded transcript, chat export, or message log."""
    suffix = "." + (file.filename or "").rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else ""
    if suffix not in TEXT_SUFFIXES:
        raise HTTPException(
            status_code=415,
            detail=(
                f"Cannot read '{suffix or 'this file type'}'. Upload a .txt, .json, "
                ".csv, .md, .vtt or .srt transcript — or paste the message text "
                "directly, which works for anything."
            ),
        )

    raw = await file.read()
    if len(raw) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File is larger than {settings.max_upload_bytes // 1024 // 1024}MB.",
        )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        # Windows-generated exports are frequently cp1252. Try once, then give
        # up with a message that names the actual problem.
        try:
            text = raw.decode("cp1252")
        except UnicodeDecodeError:
            raise HTTPException(
                status_code=415,
                detail="File is not readable as text. Paste the message contents instead.",
            )

    result = asdict(
        analyze_text(text, kind="file", claimed_identity=claimed_identity)
    )
    result["filename"] = file.filename
    return result


@router.post("/image")
async def analyze_image_route(
    file: UploadFile = File(...),
    claimed_identity: Optional[str] = None,
    caller_number: Optional[str] = None,
) -> Dict[str, Any]:
    """A screenshot — a fake police notice, a payment screenshot, a QR code.

    OCR extracts the text, any QR payload is decoded, and both are run through
    the same analyzer as a pasted message. If no OCR engine is installed the
    response is an explicit `ocr:unavailable` degradation asking the user to
    type the text, rather than a confident verdict on an empty read.
    """
    suffix = "." + (file.filename or "").rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else ""
    if suffix not in IMAGE_SUFFIXES:
        raise HTTPException(
            status_code=415,
            detail=(
                f"Cannot read '{suffix or 'this file type'}' as an image. Upload a "
                ".png, .jpg, .webp or .tiff — or paste the text directly."
            ),
        )

    raw = await file.read()
    if len(raw) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Image is larger than {settings.max_upload_bytes // 1024 // 1024}MB.",
        )

    ocr = extract_text(raw)

    # Fold any decoded QR payload into the text so a UPI deep link in a QR is
    # scored by the same path as one that was pasted.
    combined = ocr.text
    if ocr.qr_payloads:
        combined = (combined + "\n" + "\n".join(ocr.qr_payloads)).strip()

    if not combined:
        # Nothing readable. Say so — do not score an empty string.
        return {
            "kind": "image",
            "score": 0.0,
            "level": "CALM",
            "verdict": "INSUFFICIENT",
            "summary": (
                "No text could be read from this image. "
                + (
                    "OCR is not installed on this server — install it, or type out "
                    "what the screenshot says."
                    if "ocr:unavailable" in ocr.degraded
                    else "Try a clearer screenshot, or type out what it says."
                )
            ),
            "filename": file.filename,
            "ocr": {"engine": ocr.engine, "text": ocr.text, "qr_payloads": ocr.qr_payloads},
            "degraded": ocr.degraded,
            "recommended_actions": [
                "Type out the message text and analyse that instead.",
                "If a payment is involved, include the UPI ID or the amount requested.",
            ],
        }

    result = asdict(
        analyze_text(
            combined,
            kind="image",
            claimed_identity=claimed_identity,
            caller_number=caller_number,
        )
    )
    result["filename"] = file.filename
    result["ocr"] = {"engine": ocr.engine, "text": ocr.text, "qr_payloads": ocr.qr_payloads}
    # Surface OCR degradations alongside any the analyzer recorded.
    result["degraded"] = list(dict.fromkeys(result.get("degraded", []) + ocr.degraded))
    return result


@router.post("/audio")
async def analyze_audio_route(
    file: UploadFile = File(...),
    claimed_identity: Optional[str] = None,
    caller_number: Optional[str] = None,
) -> Dict[str, Any]:
    """A voice note or call recording. Whisper transcribes it, then the same
    analyzer scores the transcript.

    Degrades honestly, exactly like the OCR path: if no speech-to-text backend
    (or ffmpeg) is installed, the response carries an `asr:unavailable` reason
    asking the user to type the transcript, never a confident verdict on an
    empty read.
    """
    from ..ingest.asr import transcribe

    suffix = "." + (file.filename or "").rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else ""
    if suffix not in AUDIO_SUFFIXES:
        raise HTTPException(
            status_code=415,
            detail=(
                f"Cannot read '{suffix or 'this file type'}' as audio. Upload a "
                ".wav, .mp3, .m4a or .ogg recording — or paste the transcript directly."
            ),
        )

    raw = await file.read()
    if len(raw) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Audio is larger than {settings.max_upload_bytes // 1024 // 1024}MB.",
        )

    asr = transcribe(raw, filename=file.filename)
    if not asr.ok or not asr.text.strip():
        return {
            "kind": "audio",
            "score": 0.0,
            "level": "CALM",
            "verdict": "INSUFFICIENT",
            "summary": asr.reason or "No speech could be transcribed from this audio.",
            "filename": file.filename,
            "asr": {"backend": asr.backend, "ok": asr.ok, "text": asr.text, "reason": asr.reason},
            "degraded": asr.degraded or ["asr:empty"],
            "recommended_actions": [
                "Type out what was said and analyse that instead — the text path scores identically.",
            ],
        }

    result = asdict(
        analyze_text(
            asr.text,
            kind="audio",
            claimed_identity=claimed_identity,
            caller_number=caller_number,
        )
    )
    result["filename"] = file.filename
    result["asr"] = {"backend": asr.backend, "ok": True, "text": asr.text, "reason": None}
    result["degraded"] = list(dict.fromkeys(result.get("degraded", []) + asr.degraded))
    return result


@router.get("/knowledge/search")
def search_knowledge(q: str, k: int = 5) -> Dict[str, Any]:
    """Direct access to the corpus the verdicts cite.

    Exposed because a citation the user cannot follow is not really a
    citation. Every source string in an analysis resolves to a chunk here.
    """
    kb = get_kb()
    hits = kb.search(q, k=min(k, 20))
    return {
        "backend": kb.backend,
        "degraded": kb.degraded,
        "results": [
            {"source": h.chunk.source, "text": h.chunk.text, "score": h.score,
             "tags": h.chunk.tags, "doc": h.chunk.doc}
            for h in hits
        ],
    }


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2_000)
    k: int = 5


@router.post("/knowledge/ask")
def ask_knowledge(req: AskRequest) -> Dict[str, Any]:
    """Grounded question-answering over the curated corpus.

    Retrieval first, generation second — and only ever over what was retrieved.
    The passages returned to the caller are exactly the ones handed to the model,
    so the answer is auditable: every claim can be checked against a cited chunk,
    and if no LLM backend is configured the endpoint still returns the passages
    (extractive fallback) rather than nothing. The model phrases; it never scores
    and never sources a fact from outside the returned context.
    """
    kb = get_kb()
    hits = kb.search(req.question, k=min(max(req.k, 1), 8))
    contexts = [{"source": h.chunk.source, "text": h.chunk.text} for h in hits]
    citations = [
        {"source": h.chunk.source, "text": h.chunk.text, "doc": h.chunk.doc,
         "score": h.score}
        for h in hits
    ]

    degraded = list(kb.degraded)
    answer: Optional[str] = None
    grounded = bool(contexts)

    if not contexts:
        answer = (
            "I could not find anything about that in the knowledge base. For a "
            "live fraud, call 1930 or file at cybercrime.gov.in."
        )
        grounded = False
    elif llm.available():
        answer = llm.answer_question(req.question, contexts)
        if answer is None:
            # Asked, but the backend was unreachable. Say so, then fall through
            # to the extractive passages the UI shows either way.
            degraded.append("llm:unavailable")

    return {
        "question": req.question,
        "answer": answer,                     # None => UI shows passages only
        "answer_source": ("llm:" + settings.llm_backend) if answer and llm.available() else "extractive",
        "grounded": grounded,
        "retrieval_backend": kb.backend,
        "llm_configured": llm.available(),
        "citations": citations,
        "degraded": degraded,
    }


@router.get("/knowledge/docs")
def list_documents() -> Dict[str, List[Dict[str, Any]]]:
    """Everything in the knowledge base, grouped by document."""
    kb = get_kb()
    docs: Dict[str, List[Dict[str, Any]]] = {}
    for chunk in kb.chunks:
        docs.setdefault(chunk.doc, []).append(
            {"source": chunk.source, "text": chunk.text, "tags": chunk.tags}
        )
    return {"documents": [{"name": k, "sections": v} for k, v in sorted(docs.items())]}
