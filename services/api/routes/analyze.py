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
from ..engine.upi import analyze_upi
from ..rag.store import get_kb

router = APIRouter(prefix="/api/analyze", tags=["analyze"])

#: Extensions we will read as text. Anything else is rejected with a message
#: that says what to do instead, rather than a generic 400.
TEXT_SUFFIXES = {".txt", ".json", ".csv", ".md", ".log", ".vtt", ".srt"}


class TextRequest(BaseModel):
    text: str = Field(min_length=1, max_length=200_000)
    kind: str = "text"
    #: What the sender claims to be, if the user knows. Enables the strongest
    #: UPI check — claimed identity against the bank-registered payee name.
    claimed_identity: Optional[str] = None
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
        analyze_text(req.text, kind=req.kind, claimed_identity=req.claimed_identity)
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
