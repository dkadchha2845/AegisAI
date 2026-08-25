"""
The investigation lifecycle API — task 1.6.

Six routes, and between them the whole arc of a case: submit evidence, watch it
being investigated, read the report, read the trace, erase it.

    POST   /api/investigations              JSON body or multipart upload
    GET    /api/investigations/{id}          the InvestigationState
    GET    /api/investigations/{id}/stream   SSE, one event per completed node
    GET    /api/investigations/{id}/report   the human-readable package
    GET    /api/investigations/{id}/report.pdf
    GET    /api/investigations/{id}/trace    spans, and where the time went
    DELETE /api/investigations/{id}          erasure: rows, blobs and journal

Tenancy
-------
Every route builds an `EvidenceStore` and an `EvidenceBlobs` scoped to the
caller's organisation, and neither can express a query outside it. That is a
deliberate, visible difference from `routes/reports.py`, which uses
`orgs.scope_query` and therefore lets a platform `owner` read across tenants:
**there is no cross-organisation view of investigations, not even for an
owner.** Task 1.5 chose that ("no `load_any()`, and no escape hatch for a
platform superadmin — an exception to a tenancy rule is where the isolation bug
eventually lives"), and adding one here to match the older route would undo it.
An owner sees their own organisation's cases. The cross-org view can be built
the day it is needed, out of a query that says so.

A user with no organisation gets a 403 rather than an empty list, because
"you have no tenant" and "your tenant has no cases" are different answers and
only one of them is actionable.

Why the stream authenticates with a header and not a query parameter
--------------------------------------------------------------------
The browser `EventSource` API cannot set request headers, which is why so many
SSE endpoints end up accepting `?token=…`. This one does not. A bearer token in
a URL is written to every access log, proxy log and browser history entry it
passes through, and a token that leaks through a log is a token that leaks. The
stream takes the same `Authorization: Bearer` header as every other route here,
and a browser client reaches it with `fetch()` plus a `ReadableStream` reader
rather than `EventSource` — slightly more code in the client, and no credential
in a URL. Task 1.9 builds that client.
"""

from __future__ import annotations

import uuid
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from schema.models import InvestigationState, InvestigationStatus, utc_now_iso

from .. import audit
from ..auth import require_role
from ..config import settings
from ..db import get_db
from ..engine.report_pdf import pdf_available
from ..investigations import intake as intake_mod
from ..investigations.report import build_report, render_pdf
from ..investigations.runner import runner
from ..models_db import User
from ..orchestration.graph import node_plan
from ..orgs import evidence_scope
from ..stores.blobs import EvidenceBlobs
from ..stores.evidence import EvidenceStore

router = APIRouter(prefix="/api/investigations", tags=["investigations"])


def _new_case_id() -> str:
    """`AEG-` plus twelve hex characters.

    Minted server-side and never taken from the caller. A client-supplied id is
    an id a client can choose to collide with, and `case_id` is what all six of
    these routes look up by.
    """
    return f"AEG-{uuid.uuid4().hex[:12].upper()}"


# --------------------------------------------------------------------------
# Request / response models — these are what OpenAPI documents
# --------------------------------------------------------------------------


class InlineEvidence(BaseModel):
    """One pasted artefact: a message, a URL, a phone number, a UPI ID."""

    text: str = Field(min_length=1, max_length=intake_mod.MAX_INLINE_CHARS)
    filename: Optional[str] = Field(
        None, max_length=255, description="only if the text came from a named file"
    )
    declared_type: Optional[str] = Field(
        None,
        max_length=128,
        description="what the caller claims this is — recorded, never trusted for routing",
    )


class InvestigationRequest(BaseModel):
    """The JSON form of a submission.

    `text` is the one-artefact convenience case, which is the overwhelming
    majority of submissions; `items` is the general form. Both may be given and
    the results concatenate, so a client never has to restructure a request just
    because a second artefact appeared.
    """

    text: Optional[str] = Field(
        None, min_length=1, max_length=intake_mod.MAX_INLINE_CHARS,
        description="a single pasted message, URL, phone number or UPI ID",
    )
    items: List[InlineEvidence] = Field(default_factory=list, max_length=intake_mod.MAX_ITEMS)


class AcceptedInvestigation(BaseModel):
    """What `POST /api/investigations` returns, before the graph has run."""

    case_id: str
    status: InvestigationStatus
    investigation: InvestigationState
    stream: str = Field(description="the SSE endpoint for live progress")
    degraded: List[str] = Field(
        default_factory=list, description="capabilities already known to be reduced"
    )


class ErasureResult(BaseModel):
    """What `DELETE /api/investigations/{id}` removed."""

    case_id: str
    erased: bool
    blobs_removed: int
    was_running: bool


# --------------------------------------------------------------------------
# Dependencies
# --------------------------------------------------------------------------


def _scope(user: User) -> str:
    scope = evidence_scope(user)
    if scope is None:
        raise HTTPException(
            status_code=403,
            detail="Your account is not attached to an organisation, so it has no case file. "
                   "Ask an administrator to add you to one.",
        )
    return scope


def _load(user: User, db: Session, case_id: str) -> InvestigationState:
    """The freshest view of one case, or 404.

    A run still in flight is read from the runner rather than the database. The
    durable row is written when the graph finishes, so serving it mid-run would
    report QUEUED to a client that is simultaneously being streamed the third
    node's results — two endpoints on the same server disagreeing about the same
    case. 404 rather than 403 for another tenant's id, which is the same
    non-answer `routes/reports.py` gives, so a case id cannot be probed for
    existence from outside the organisation that owns it.
    """
    scope = _scope(user)
    run = runner.get(scope, case_id)
    if run is not None:
        return run.state
    state = EvidenceStore(db, scope).load(case_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"No investigation {case_id}")
    return state


# --------------------------------------------------------------------------
# Submit
# --------------------------------------------------------------------------


async def _submissions(
    request: Request,
    files: List[UploadFile],
    text: Optional[str],
) -> List[intake_mod.Submission]:
    """Normalise either request shape into a list of submissions.

    One route rather than two because "start an investigation" is one action;
    the transport is a detail of what the client happens to be holding, and a
    caller that pastes a message today and attaches a screenshot tomorrow should
    not have to change endpoints.
    """
    content_type = (request.headers.get("content-type") or "").split(";")[0].strip().lower()

    if content_type == "application/json":
        try:
            payload = InvestigationRequest.model_validate(await request.json())
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Malformed JSON body: {exc}"[:300]) from exc
        subs = [intake_mod.Submission(text=payload.text)] if payload.text else []
        subs += [
            intake_mod.Submission(
                text=item.text, filename=item.filename, declared_type=item.declared_type
            )
            for item in payload.items
        ]
        return subs

    subs = []
    if text and text.strip():
        subs.append(intake_mod.Submission(text=text))
    for upload in files:
        # Capped while reading, not after: see `intake.read_capped`. A 500 MB
        # body is refused one chunk past 4 MB instead of being buffered whole
        # and then rejected.
        data = await intake_mod.read_capped(upload)
        if not data:
            raise HTTPException(
                status_code=422,
                detail=f"'{upload.filename or 'file'}' is empty — there is nothing to investigate.",
            )
        subs.append(
            intake_mod.Submission(
                data=data,
                filename=upload.filename,
                declared_type=upload.content_type,
            )
        )
    return subs


@router.post(
    "",
    status_code=202,
    response_model=AcceptedInvestigation,
    summary="Submit evidence and start an investigation",
    description=(
        "Accepts either `application/json` (a pasted message, URL, phone number "
        "or UPI ID) or `multipart/form-data` (up to "
        f"{intake_mod.MAX_ITEMS} files, each at most "
        f"{settings.max_upload_bytes // 1024 // 1024} MB, plus an optional `text` "
        "field). Returns 202 with the queued investigation and the URL of its "
        "progress stream: the agent graph runs after the response, and the case "
        "is readable from the moment this returns."
    ),
)
async def create_investigation(
    request: Request,
    files: List[UploadFile] = File(default=[], description="evidence files (multipart only)"),
    text: Optional[str] = Form(default=None, description="pasted evidence (multipart only)"),
    user: User = Depends(require_role("analyst")),
    db: Session = Depends(get_db),
) -> AcceptedInvestigation:
    scope = _scope(user)
    case_id = _new_case_id()

    try:
        submissions = await _submissions(request, files, text)
        result = intake_mod.build_items(case_id, submissions, EvidenceBlobs(scope))
    except intake_mod.EvidenceTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except intake_mod.TooManyItems as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except intake_mod.NoEvidence as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    state = InvestigationState(
        case_id=case_id,
        org_id=scope,
        created_by=user.email,
        created_at=utc_now_iso(),
        status=InvestigationStatus.QUEUED,
        inputs=result.items,
        degraded=result.degraded,
    )

    # Written before the graph starts, so `GET /{id}` and the case list answer
    # from the moment this responds — and so a process that dies mid-run leaves
    # a record of what was submitted rather than nothing at all.
    EvidenceStore(db, scope).save(state)
    audit.record(
        db,
        "investigation.create",
        actor=user.email,
        target=case_id,
        detail=f"{len(result.items)} item(s)"
               + (f"; degraded {result.degraded}" if result.degraded else ""),
        org_id=user.org_id,
    )

    runner.start(state, scope)
    return AcceptedInvestigation(
        case_id=case_id,
        status=state.status,
        investigation=state,
        stream=f"/api/investigations/{case_id}/stream",
        degraded=list(result.degraded),
    )


# --------------------------------------------------------------------------
# Read
# --------------------------------------------------------------------------


@router.get(
    "/{case_id}",
    response_model=InvestigationState,
    summary="Read one investigation",
    description=(
        "The full `InvestigationState`. While the graph is running this is the "
        "live state; afterwards it is rebuilt from the evidence store's rows."
    ),
)
def get_investigation(
    case_id: str,
    user: User = Depends(require_role("viewer")),
    db: Session = Depends(get_db),
) -> InvestigationState:
    return _load(user, db, case_id)


@router.get(
    "/{case_id}/report",
    summary="The human-readable report",
    description=(
        "What was submitted, what was found, what the system will and will not "
        "claim, and what to do next. An investigation the judgement tier has not "
        "scored says so explicitly — it is never rendered as a risk of zero."
    ),
)
def get_report(
    case_id: str,
    user: User = Depends(require_role("viewer")),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    return build_report(_load(user, db, case_id))


@router.get(
    "/{case_id}/report.pdf",
    summary="The report as a PDF",
    description=(
        "The same package rendered for printing or attaching to a complaint. "
        "Returns 503 naming the JSON endpoint if reportlab is not installed."
    ),
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}, "description": "the report"}},
)
def get_report_pdf(
    case_id: str,
    user: User = Depends(require_role("viewer")),
    db: Session = Depends(get_db),
) -> Response:
    state = _load(user, db, case_id)
    if not pdf_available():
        raise HTTPException(
            status_code=503,
            detail=(
                "PDF rendering is unavailable — reportlab is not installed. "
                "Install it (`pip install reportlab`) or use GET "
                f"/api/investigations/{case_id}/report for the JSON package."
            ),
        )
    pdf = render_pdf(build_report(state))
    audit.record(
        db, "investigation.export", actor=user.email, target=case_id,
        detail="report.pdf", org_id=user.org_id,
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{case_id}.pdf"'},
    )


@router.get(
    "/{case_id}/trace",
    summary="Where the time went",
    description=(
        "Every node execution as a `TraceSpan`, plus the graph's node plan and "
        "the wall-clock elapsed time. `elapsed_ms` is the wall clock, not the "
        "sum of the spans: with a concurrent fan-out the sum is larger, and "
        "quoting it would overstate how long the citizen waited."
    ),
)
def get_trace(
    case_id: str,
    user: User = Depends(require_role("viewer")),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    state = _load(user, db, case_id)
    return {
        "case_id": state.case_id,
        "status": state.status.value,
        # From the graph, not from the run: the plan is a property of the graph's
        # shape, so it is still the right answer for a case whose journal has
        # been evicted or whose process has restarted.
        "plan": node_plan(),
        "spans": [s.model_dump(mode="json") for s in state.trace],
        "elapsed_ms": int(max((s.t_end for s in state.trace), default=0.0) * 1000),
        "agent_ms": sum(s.latency_ms for s in state.trace),
        "degraded": list(state.degraded),
    }


# --------------------------------------------------------------------------
# Stream
# --------------------------------------------------------------------------


def _sse(payload: str, *, event: Optional[str] = None, seq: Optional[int] = None) -> bytes:
    lines = []
    if seq is not None:
        lines.append(f"id: {seq}")
    if event is not None:
        lines.append(f"event: {event}")
    lines.append(f"data: {payload}")
    return ("\n".join(lines) + "\n\n").encode("utf-8")


@router.get(
    "/{case_id}/stream",
    summary="Live per-node progress (server-sent events)",
    description=(
        "One event per completed graph node, plus `accepted` at the start and "
        "`complete`/`failed`/`cancelled` at the end. Every event carries a "
        "monotonic `id`; reconnect with `Last-Event-ID` (or `?after=`) and the "
        "stream resumes from the next one, so nothing is delivered twice. "
        "Keepalives are SSE comment lines and carry no id. Authenticate with the "
        "same `Authorization: Bearer` header as every other route — the browser "
        "`EventSource` API cannot set headers, so use `fetch()` with a "
        "`ReadableStream` reader rather than putting a token in the URL."
    ),
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}, "description": "the event stream"}},
)
async def stream_investigation(
    case_id: str,
    last_event_id: Optional[str] = Header(default=None, alias="Last-Event-ID"),
    after: Optional[int] = Query(
        default=None, ge=0, description="fallback for Last-Event-ID; the header wins"
    ),
    user: User = Depends(require_role("viewer")),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    scope = _scope(user)
    run = runner.get(scope, case_id)
    if run is None:
        # No journal. Either the case never existed here, or it finished long
        # enough ago to be evicted, or this process was restarted. The
        # distinction matters to the client, so it is made rather than collapsed
        # into one 404: a case that exists is told to read the finished state.
        if EvidenceStore(db, scope).exists(case_id):
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Investigation {case_id} is not streaming in this process — it has "
                    "finished, or the server restarted. Read the final state at "
                    f"GET /api/investigations/{case_id}."
                ),
            )
        raise HTTPException(status_code=404, detail=f"No investigation {case_id}")

    resume_from = 0
    if last_event_id and last_event_id.strip().isdigit():
        resume_from = int(last_event_id.strip())
    elif after is not None:
        resume_from = after

    async def events() -> AsyncIterator[bytes]:
        # `retry` is the client's reconnect delay. Sent once, before anything
        # else, so a connection that drops on the very first event still comes
        # back on our schedule rather than the browser's default.
        yield b"retry: 3000\n\n"
        async for event in run.follow(resume_from):
            if event is None:
                yield b": keepalive\n\n"
                continue
            yield _sse(
                event.model_dump_json(),
                event=event.kind.value,
                seq=event.seq,
            )

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            # Nginx buffers proxied responses by default, which turns a live
            # stream into one delivery at the end. This is the documented opt
            # out and is inert everywhere else.
            "X-Accel-Buffering": "no",
        },
    )


# --------------------------------------------------------------------------
# Erase
# --------------------------------------------------------------------------


@router.delete(
    "/{case_id}",
    response_model=ErasureResult,
    summary="Erase an investigation and its evidence",
    description=(
        "GDPR-style erasure. Cancels the run if it is still going, deletes the "
        "case row and every child row, removes the stored bytes of every "
        "uploaded artefact, and drops the in-memory progress journal. Admin "
        "only, and audited — the audit row survives, naming the case id and who "
        "erased it, because a deletion nobody can account for is its own problem."
    ),
)
async def delete_investigation(
    case_id: str,
    user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> ErasureResult:
    scope = _scope(user)
    store = EvidenceStore(db, scope)
    if not store.exists(case_id):
        raise HTTPException(status_code=404, detail=f"No investigation {case_id}")

    # Order matters. Cancel first: a run that finishes after the rows are gone
    # writes them straight back, and an erasure that undoes itself four seconds
    # later is worse than one that fails loudly.
    was_running = await runner.cancel(scope, case_id)
    erased = store.delete_case(case_id)
    blobs_removed = EvidenceBlobs(scope).delete_case(case_id)
    runner.forget(scope, case_id)

    audit.record(
        db,
        "investigation.delete",
        actor=user.email,
        target=case_id,
        detail=f"erased={erased}; artefacts removed={blobs_removed}"
               + ("; cancelled a running investigation" if was_running else ""),
        org_id=user.org_id,
    )
    return ErasureResult(
        case_id=case_id,
        erased=erased,
        blobs_removed=blobs_removed,
        was_running=was_running,
    )


__all__ = ["router"]
