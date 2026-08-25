"""
The investigation lifecycle API — task 1.6's four acceptance criteria, and the
invariants that have to survive the next change.

    .venv/bin/python -m pytest services/api/tests/test_investigations_api.py -q

| Criterion | Test |
|---|---|
| submit → live per-node progress → final report | `test_submit_stream_report_end_to_end` |
| SSE reconnect resumes without duplicate events | `test_reconnect_*` (three of them) |
| 4 MB upload cap enforced | `test_an_upload_over_the_cap_*` |
| OpenAPI documents every route | `test_openapi_documents_every_lifecycle_route` |

Three things about the harness are load-bearing rather than incidental.

**Every client is a context manager.** `TestClient(app)` used bare opens a new
event-loop portal per request and tears it down when the request returns —
which kills the background task the graph is running on, so the investigation
would never finish and the stream would hang. Entering the client keeps one
loop for its lifetime, which is also what a real server has.

**Every client gets its own IP.** The rate limiter allows 30 writes a minute per
address, and this file makes more than that. Distinct addresses give each test
its own bucket, so the suite exercises the real middleware stack instead of
disabling it — the SSE response passes through `BaseHTTPMiddleware` in
production and that is precisely the part worth testing.

**`TestClient` buffers a streaming response.** Measured, not assumed: with a
two-second agent in the graph, the first chunk still arrives only when the last
one does. So nothing here can assert that events arrive *as they happen* —
that claim belongs to the running server and was checked there (uvicorn,
`curl -N`: events 1-3 at 0 ms, a two-second gap, then 4-9). What the tests below
assert is everything that does not depend on delivery timing, plus one direct
test of `Run.follow` for the live-resume path the HTTP client cannot reach.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import zipfile
from io import BytesIO
from typing import Any, Dict, Iterator, List, Optional

import pytest
from fastapi.testclient import TestClient

from schema.models import (
    AgentResult,
    AgentStatus,
    EvidenceItem,
    InvestigationState,
    InvestigationStatus,
    utc_now_iso,
)
from services.api.agents import registry
from services.api.config import settings
from services.api.db import SessionLocal, init_db
from services.api.investigations import intake as intake_mod
from services.api.investigations.report import NOT_SCORED, build_report
from services.api.investigations.runner import InvestigationRunner
from services.api.main import app
from services.api.orchestration.graph import node_plan
from services.api.stores import blobs as blob_store
from services.api.stores.evidence import EvidenceStore

SCAM_TEXT = (
    "URGENT: your SBI KYC is suspended. Pay Rs 4999 to refund@okaxis within 2 hours "
    "or your account will be blocked. Verify at http://sbi-kyc-verify.top"
)
BENIGN_TEXT = (
    "Dear Customer, Rs 450.00 debited from A/c XX3421 on 24-08-26 to VPA "
    "grocerystore@ybl. Not you? Call 1800-11-2211. -SBI"
)

_ADDRESS = itertools.count(2)


def _queued_state(case_id: str, org_id: str = "org-1") -> InvestigationState:
    return InvestigationState(
        case_id=case_id,
        org_id=org_id,
        created_by="t@aegis.local",
        created_at=utc_now_iso(),
        inputs=[EvidenceItem(id="ev-01", text="pay verify@ybl")],
    )


@pytest.fixture(autouse=True)
def _db() -> None:
    init_db()


@pytest.fixture
def client() -> Iterator[TestClient]:
    address = f"10.0.{next(_ADDRESS) // 250}.{next(_ADDRESS) % 250 + 1}"
    with TestClient(app, client=(address, 51000)) as test_client:
        yield test_client


# --------------------------------------------------------------------------
# SSE helpers
# --------------------------------------------------------------------------

TERMINAL = {"complete", "failed", "cancelled"}


def _parse_block(block: str) -> Optional[Dict[str, Any]]:
    """One SSE block as `{id, event, data}`, or None if it carries no event.

    `retry:` and comment lines (`: keepalive`) are deliberately dropped here
    rather than counted, because that is exactly how a browser treats them —
    and the reconnect claim rests on them not being events.
    """
    event_id: Optional[str] = None
    name: Optional[str] = None
    data: List[str] = []
    for line in block.splitlines():
        if line.startswith(":") or not line.strip():
            continue
        field, _, value = line.partition(":")
        value = value.lstrip()
        if field == "id":
            event_id = value
        elif field == "event":
            name = value
        elif field == "data":
            data.append(value)
    if name is None or not data:
        return None
    return {"id": int(event_id) if event_id else None, "event": name, "data": json.loads("\n".join(data))}


def read_stream(
    client: TestClient,
    case_id: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Read the stream until a terminal event, or until `limit` events.

    Returning early closes the response, which is the client-disconnect the
    reconnect tests need — there is no separate mechanism for simulating it.
    """
    seen: List[Dict[str, Any]] = []
    with client.stream(
        "GET", f"/api/investigations/{case_id}/stream", headers=headers or {}, params=params or {}
    ) as response:
        assert response.status_code == 200, response.read()
        assert response.headers["content-type"].startswith("text/event-stream")
        buffer = ""
        for chunk in response.iter_text():
            buffer += chunk
            while "\n\n" in buffer:
                block, buffer = buffer.split("\n\n", 1)
                parsed = _parse_block(block)
                if parsed is None:
                    continue
                seen.append(parsed)
                if limit is not None and len(seen) >= limit:
                    return seen
                if parsed["event"] in TERMINAL:
                    return seen
    return seen


def submit(client: TestClient, text: str = SCAM_TEXT, **kw: Any) -> str:
    response = client.post("/api/investigations", json={"text": text}, **kw)
    assert response.status_code == 202, response.text
    return str(response.json()["case_id"])


def finish(client: TestClient, case_id: str) -> Dict[str, Any]:
    """Wait for the run by draining its stream, then return the final state."""
    read_stream(client, case_id)
    return dict(client.get(f"/api/investigations/{case_id}").json())


# --------------------------------------------------------------------------
# Criterion 1 — submit, watch, read the report
# --------------------------------------------------------------------------


def test_submit_stream_report_end_to_end(client: TestClient) -> None:
    accepted = client.post("/api/investigations", json={"text": SCAM_TEXT})
    assert accepted.status_code == 202
    body = accepted.json()
    case_id = body["case_id"]
    assert body["status"] == "QUEUED"
    assert body["stream"] == f"/api/investigations/{case_id}/stream"
    # Readable the instant the POST returns — the record is written before the
    # graph starts, so a client is never told about a case it cannot then fetch.
    assert client.get(f"/api/investigations/{case_id}").status_code == 200

    events = read_stream(client, case_id)
    assert events[0]["event"] == "accepted"
    assert events[-1]["event"] == "complete"

    state = client.get(f"/api/investigations/{case_id}").json()
    assert state["status"] == "COMPLETE"
    assert state["completed_at"]
    assert "input_classifier" in [r["agent"] for r in state["agent_results"]]

    report = client.get(f"/api/investigations/{case_id}/report").json()
    assert report["report_id"] == case_id
    assert report["case"]["status"] == "COMPLETE"
    assert report["findings"]


def test_the_finished_case_is_durable_and_rebuilt_from_rows(client: TestClient) -> None:
    """The state a client reads after the run is the one 1.5 reassembled.

    Read through `EvidenceStore` directly rather than through the route, because
    the route would happily serve the runner's in-memory copy and the thing
    being asserted is that the *database* has it.
    """
    case_id = submit(client)
    finish(client, case_id)

    db = SessionLocal()
    try:
        stored = EvidenceStore(db, _scope_of(client)).load(case_id)
    finally:
        db.close()
    live = client.get(f"/api/investigations/{case_id}").json()
    assert stored is not None
    assert stored.status is InvestigationStatus.COMPLETE
    # Every agent that ran survived the round trip, in the same order — the
    # store rebuilds from rows, so this is the six tables agreeing with the
    # object they were written from.
    assert [r.agent for r in stored.agent_results] == [r["agent"] for r in live["agent_results"]]
    assert "input_classifier" in [r.agent for r in stored.agent_results]
    assert "threat_fusion" in [r.agent for r in stored.agent_results]
    assert stored.inputs[0].text == SCAM_TEXT


# --------------------------------------------------------------------------
# Criterion 1 (cont.) — progress is observed, not estimated
# --------------------------------------------------------------------------


def test_the_stream_reports_every_graph_node_exactly_once(client: TestClient) -> None:
    case_id = submit(client)
    events = read_stream(client, case_id)

    nodes = [e["data"]["node"] for e in events if e["event"] == "node_complete"]
    assert nodes == node_plan(), "one event per node, in graph order"
    assert len(nodes) == len(set(nodes))


def test_the_plan_arrives_first_so_progress_has_a_real_denominator(client: TestClient) -> None:
    """`accepted` carries the whole node list.

    This is what keeps 1.9's progress bar honest: the client is *told* how many
    nodes there are and then *told* as each one finishes, so nothing about the
    display is inferred from elapsed time.
    """
    case_id = submit(client)
    events = read_stream(client, case_id)

    first = events[0]["data"]
    assert first["kind"] == "accepted"
    assert first["plan"] == node_plan()
    assert first["nodes_done"] == 0

    done = [e["data"]["nodes_done"] for e in events if e["event"] == "node_complete"]
    assert done == list(range(1, len(node_plan()) + 1))


def test_an_events_agent_results_are_the_delta_not_the_running_total(client: TestClient) -> None:
    """Appending every event's results must reconstruct the state's list exactly.

    The graph's nodes return whole lists, so an event that forwarded the update
    verbatim would re-send every earlier tier and a reconnecting client would
    double-count. This is the test that fails if that ever regresses.
    """
    case_id = submit(client)
    events = read_stream(client, case_id)
    state = client.get(f"/api/investigations/{case_id}").json()

    streamed = [r for e in events for r in e["data"]["agent_results"]]
    assert [r["agent"] for r in streamed] == [r["agent"] for r in state["agent_results"]]


def test_a_degraded_agent_is_visible_in_the_frame_it_degraded_in(client: TestClient) -> None:
    """Degradation is streamed as it happens, not summarised at the end."""
    from services.api.agents.base import AgentContext, Stage

    class _Degrader:
        name = "test_degrader"
        version = "1.0.0"
        stage = Stage.INVESTIGATE

        def can_handle(self, state: InvestigationState) -> bool:
            return True

        async def run(self, state: InvestigationState, ctx: AgentContext) -> AgentResult:
            return AgentResult(
                agent=self.name,
                version=self.version,
                status=AgentStatus.DEGRADED,
                confidence=0.2,
                error="feed unreachable; served from cache",
            )

    registry.register(_Degrader)
    try:
        case_id = submit(client)
        events = read_stream(client, case_id)
    finally:
        registry._REGISTRY.pop("test_degrader", None)

    carrying = [e for e in events if e["data"]["degraded"]]
    assert carrying, "the degradation was never streamed"
    assert carrying[0]["data"]["node"] == "investigate_stage"
    assert "agent:test_degrader:degraded" in carrying[0]["data"]["degraded"]


# --------------------------------------------------------------------------
# Criterion 2 — reconnect without duplicates
# --------------------------------------------------------------------------


def test_reconnect_with_last_event_id_resumes_without_duplicates(client: TestClient) -> None:
    """Disconnect after three events, come back with `Last-Event-ID`, get the rest.

    What this proves is the resume arithmetic and the no-duplicate property.
    What it cannot prove is the *timing*, because `TestClient` buffers a
    streaming response in full before handing it to the caller — the first
    chunk arrives only when the last one does. Incremental delivery is a
    property of the running server, and it was verified there: against uvicorn
    with a deliberately slow agent, events 1-3 arrive at 0 ms, then a two-second
    gap while the agent runs, then 4-9. `test_a_follower_that_drops_mid_run_*`
    below covers the live-resume path without HTTP in the way.
    """
    case_id = submit(client)

    first = read_stream(client, case_id, limit=3)
    assert [e["id"] for e in first] == [1, 2, 3]

    resumed = read_stream(client, case_id, headers={"Last-Event-ID": "3"})
    ids = [e["id"] for e in first] + [e["id"] for e in resumed]

    assert len(ids) == len(set(ids)), "an event was delivered twice"
    assert ids == list(range(1, len(ids) + 1)), "the sequence has a hole"
    assert resumed[-1]["event"] == "complete"
    assert [e["data"]["node"] for e in resumed if e["event"] == "node_complete"] == node_plan()[2:]


def test_a_follower_that_drops_mid_run_resumes_live_without_duplicates() -> None:
    """The case the HTTP test cannot reach: a client that drops *while the
    investigation is still running*, and comes back to find both the events it
    missed and the ones that have not happened yet.

    Driven against `Run` directly, so the interleaving is arranged rather than
    hoped for — the graph finishes in single-digit milliseconds and a test that
    raced it would pass for the wrong reason.
    """
    from schema.models import InvestigationEventKind as Kind
    from services.api.investigations.runner import Run

    async def scenario() -> tuple[List[int], List[int]]:
        run = Run(_queued_state("AEG-MIDRUN"), "org-1")
        run.append(Kind.ACCEPTED, plan=run.plan)
        run.append(Kind.NODE_COMPLETE, node="begin")

        early: List[int] = []
        follower = run.follow(0)
        async for event in follower:
            assert event is not None
            early.append(event.seq)
            if len(early) == 2:
                break
        await follower.aclose()  # the disconnect

        # Progress nobody is listening to.
        run.append(Kind.NODE_COMPLETE, node="classify")

        late: List[int] = []

        async def resume() -> None:
            async for event in run.follow(early[-1]):
                assert event is not None
                late.append(event.seq)

        task = asyncio.create_task(resume())
        await asyncio.sleep(0.01)  # let it drain what it missed
        assert late == [3], "the missed event was not replayed"

        run.append(Kind.NODE_COMPLETE, node="extract_stage")
        run.append(Kind.COMPLETE)
        run.finish()
        await asyncio.wait_for(task, timeout=2)
        return early, late

    early, late = asyncio.run(scenario())
    assert early == [1, 2]
    assert late == [3, 4, 5], "live events after a resume were missed or duplicated"
    assert set(early) & set(late) == set()


def test_reconnect_query_parameter_is_a_fallback_for_the_header(client: TestClient) -> None:
    case_id = submit(client)
    read_stream(client, case_id)  # let it finish

    resumed = read_stream(client, case_id, params={"after": 4})
    assert resumed[0]["id"] == 5


def test_a_follower_arriving_after_the_run_is_replayed_the_whole_journal(
    client: TestClient,
) -> None:
    """The journal outlives the run, so a client that connects late is not
    told a case it can still fetch has no progress to show."""
    case_id = submit(client)
    read_stream(client, case_id)

    replayed = read_stream(client, case_id)
    assert [e["id"] for e in replayed] == list(range(1, len(replayed) + 1))
    assert replayed[0]["event"] == "accepted"
    assert replayed[-1]["event"] == "complete"


def test_a_stream_for_a_case_with_no_journal_says_where_to_read_it(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A finished-and-evicted case is a 409 naming the state endpoint, not a
    404 — the case exists, it simply is not streaming any more."""
    from services.api.investigations import runner as runner_mod

    case_id = submit(client)
    read_stream(client, case_id)
    runner_mod.runner.forget(_scope_of(client), case_id)

    response = client.get(f"/api/investigations/{case_id}/stream")
    assert response.status_code == 409
    assert f"/api/investigations/{case_id}" in response.json()["detail"]

    missing = client.get("/api/investigations/AEG-000000000000/stream")
    assert missing.status_code == 404


def test_an_idle_stream_signals_with_something_that_carries_no_id() -> None:
    """The keepalive is an SSE comment, and this pins that it stays one.

    If the idle signal ever became a real event it would be given a sequence
    number, a reconnecting client would resume past it, and "resumes without
    duplicate events" would quietly start meaning "unless the connection was
    idle". `follow()` yields `None` for the idle case — a value the route
    renders as `: keepalive`, which by definition has no id.
    """
    from schema.models import InvestigationEventKind
    from services.api.investigations.runner import Run

    async def scenario() -> List[Any]:
        run = Run(_queued_state("AEG-IDLE"), "org-1")
        run.append(InvestigationEventKind.ACCEPTED, plan=run.plan)
        seen: List[Any] = []
        async for item in run.follow(0, keepalive_s=0.02):
            seen.append(item)
            if len(seen) >= 3:
                break
        return seen

    seen = asyncio.run(scenario())
    assert seen[0] is not None and seen[0].seq == 1
    assert seen[1] is None and seen[2] is None, "an idle stream produced numbered events"


# --------------------------------------------------------------------------
# Criterion 3 — the upload cap
# --------------------------------------------------------------------------


def test_an_upload_over_the_cap_is_refused(client: TestClient) -> None:
    oversize = b"\x00" * (settings.max_upload_bytes + 1)
    response = client.post(
        "/api/investigations",
        files={"files": ("huge.bin", oversize, "application/octet-stream")},
    )
    assert response.status_code == 413
    assert "4 MB" in response.json()["detail"]


def test_an_upload_at_the_cap_is_accepted(client: TestClient) -> None:
    """The boundary is a limit, not an off-by-one."""
    at_limit = b"\x00" * settings.max_upload_bytes
    response = client.post(
        "/api/investigations",
        files={"files": ("big.bin", at_limit, "application/octet-stream")},
    )
    assert response.status_code == 202


def test_read_capped_refuses_before_buffering_the_whole_body() -> None:
    """The cap is enforced *while reading*, which is the point of it.

    `await file.read()` followed by a length check has already buffered the
    whole body by the time it decides to say no, so a 500 MB upload costs
    500 MB of memory to refuse. This asserts the refusal happens after a bounded
    number of chunks rather than after the body.
    """

    class _Endless:
        def __init__(self) -> None:
            self.reads = 0

        async def read(self, size: int = -1) -> bytes:
            self.reads += 1
            return b"x" * (size if size > 0 else intake_mod.CHUNK)

    source = _Endless()
    with pytest.raises(intake_mod.EvidenceTooLarge):
        asyncio.run(intake_mod.read_capped(source, limit=4 * intake_mod.CHUNK))
    assert source.reads <= 6, "read far past the cap before refusing"


def test_more_artefacts_than_the_limit_are_refused(client: TestClient) -> None:
    files = [
        ("files", (f"note-{i}.txt", b"pay verify@ybl now", "text/plain"))
        for i in range(intake_mod.MAX_ITEMS + 1)
    ]
    response = client.post("/api/investigations", files=files)
    assert response.status_code == 413
    assert str(intake_mod.MAX_ITEMS) in response.json()["detail"]


def test_an_empty_submission_is_refused(client: TestClient) -> None:
    assert client.post("/api/investigations", json={}).status_code == 422
    assert client.post("/api/investigations", json={"items": []}).status_code == 422


# --------------------------------------------------------------------------
# Criterion 4 — OpenAPI
# --------------------------------------------------------------------------


def test_openapi_documents_every_lifecycle_route(client: TestClient) -> None:
    spec = client.get("/openapi.json").json()
    expected = {
        ("/api/investigations", "post"),
        ("/api/investigations/{case_id}", "get"),
        ("/api/investigations/{case_id}", "delete"),
        ("/api/investigations/{case_id}/stream", "get"),
        ("/api/investigations/{case_id}/report", "get"),
        ("/api/investigations/{case_id}/report.pdf", "get"),
        ("/api/investigations/{case_id}/trace", "get"),
    }
    for path, method in sorted(expected):
        operation = spec["paths"].get(path, {}).get(method)
        assert operation, f"{method.upper()} {path} is not in the OpenAPI document"
        # A route in the schema with no prose is documented only in the sense
        # that its existence is discoverable, which is not what the criterion
        # asks for.
        assert operation.get("summary"), f"{method.upper()} {path} has no summary"
        assert operation.get("description"), f"{method.upper()} {path} has no description"


def test_openapi_names_the_streaming_and_pdf_content_types(client: TestClient) -> None:
    spec = client.get("/openapi.json").json()
    stream = spec["paths"]["/api/investigations/{case_id}/stream"]["get"]
    assert "text/event-stream" in stream["responses"]["200"]["content"]
    pdf = spec["paths"]["/api/investigations/{case_id}/report.pdf"]["get"]
    assert "application/pdf" in pdf["responses"]["200"]["content"]


# --------------------------------------------------------------------------
# Uploads: the bytes decide the type, and the lie is recorded
# --------------------------------------------------------------------------

_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x02\x80\x00\x00\x05\x00"
    b"\x08\x06\x00\x00\x00" + b"\x00" * 32
)


def _apk_bytes() -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("AndroidManifest.xml", "\x03\x00\x08\x00")
        archive.writestr("classes.dex", "dex\n035\x00")
        archive.writestr("resources.arsc", "\x02\x00\x0c\x00")
    return buffer.getvalue()


def test_an_uploaded_image_is_classified_from_its_bytes_and_stored(client: TestClient) -> None:
    response = client.post(
        "/api/investigations", files={"files": ("notice.png", _PNG, "image/png")}
    )
    assert response.status_code == 202
    case_id = response.json()["case_id"]
    state = finish(client, case_id)

    item = state["inputs"][0]
    assert item["kind"] == "IMAGE"
    assert item["media_type"] == "image/png"
    assert item["sha256"]
    assert item["uri"], "the bytes were not stored, so no later agent could read them"
    assert item["text"] is None, "binary evidence must not be inlined into the state"


def test_an_apk_renamed_as_an_image_is_recorded_as_a_conflict_not_a_rejection(
    client: TestClient,
) -> None:
    """Magic bytes decide, and the lie becomes evidence.

    Rejecting at the door would turn the most interesting fact about a hostile
    upload into a 415 with nothing written down. Intake records what was
    claimed; the classifier reads the bytes; the disagreement is a finding.
    """
    response = client.post(
        "/api/investigations", files={"files": ("holiday.jpg", _apk_bytes(), "image/jpeg")}
    )
    assert response.status_code == 202
    case_id = response.json()["case_id"]
    state = finish(client, case_id)

    assert state["inputs"][0]["kind"] == "APK"
    assert state["inputs"][0]["declared_type"] == "image/jpeg"
    conflicts = [
        f
        for r in state["agent_results"]
        for f in r["findings"]
        if f["label"] == "type_conflict"
    ]
    assert conflicts, "the declared/detected disagreement was not recorded"


def test_a_traversing_filename_is_defanged(client: TestClient) -> None:
    response = client.post(
        "/api/investigations",
        files={"files": ("../../../etc/passwd", b"root:x:0:0:", "text/plain")},
    )
    case_id = response.json()["case_id"]
    state = finish(client, case_id)
    stored = state["inputs"][0]["filename"]
    assert stored == "passwd"
    assert ".." not in stored and "/" not in stored


def test_a_small_text_upload_is_inlined_and_a_binary_one_is_not() -> None:
    text = intake_mod.build_items(
        "AEG-INLINE", [intake_mod.Submission(data=b"pay verify@ybl", filename="sms.txt")]
    )
    assert text.items[0].text == "pay verify@ybl"

    binary = intake_mod.build_items(
        "AEG-INLINE", [intake_mod.Submission(data=b"\x00\x01\x02", filename="x.bin")]
    )
    assert binary.items[0].text is None


# --------------------------------------------------------------------------
# The report tells the truth about what it does not know
# --------------------------------------------------------------------------


def test_an_unscored_investigation_says_so_rather_than_reading_as_safe(
    client: TestClient,
) -> None:
    """The judgement tier is empty until 4.6, and the report must not paper
    over it. `0.0 / CALM` on an unscored case is a false negative wearing a
    number — which is exactly why `risk_score` is Optional in the contract."""
    case_id = submit(client)
    finish(client, case_id)
    assessment = client.get(f"/api/investigations/{case_id}/report").json()["assessment"]

    assert assessment["scored"] is False
    assert assessment["risk_score"] is None
    assert assessment["risk_level"] is None
    assert assessment["classification"] is None
    assert assessment["note"] == NOT_SCORED
    assert "not a finding of safety" in assessment["note"]


def test_a_scored_investigation_reports_its_score_verbatim() -> None:
    """Every number in the report is copied from a contract field.

    Built directly rather than through the API because no agent scores yet;
    what is being pinned is that when 4.6 lands, the report renders the score
    it was given and does not re-band it.
    """
    from schema.models import FraudCategory, ThreatLevel

    state = InvestigationState(
        case_id="AEG-SCORED",
        org_id="org-1",
        created_by="t@aegis.local",
        created_at=utc_now_iso(),
        status=InvestigationStatus.COMPLETE,
        risk_score=69.6,
        risk_level=ThreatLevel.HIGH,
        confidence=0.81,
        classification=FraudCategory.UPI_PAYMENT_FRAUD,
    )
    assessment = build_report(state)["assessment"]
    assert assessment == {
        "scored": True,
        "risk_score": 69.6,
        "risk_level": "HIGH",
        "confidence": 0.81,
        "classification": "upi_payment_fraud",
        "note": None,
    }


def test_the_report_names_every_artefact_with_its_hash(client: TestClient) -> None:
    response = client.post(
        "/api/investigations",
        data={"text": SCAM_TEXT},
        files={"files": ("notice.png", _PNG, "image/png")},
    )
    case_id = response.json()["case_id"]
    finish(client, case_id)
    report = client.get(f"/api/investigations/{case_id}/report").json()

    assert len(report["inputs"]) == 2
    for row in report["inputs"]:
        assert len(row["sha256"]) == 64
    assert {row["kind"] for row in report["inputs"]} == {"TEXT", "IMAGE"}


def test_the_report_renders_as_a_pdf(client: TestClient) -> None:
    from services.api.engine.report_pdf import pdf_available

    case_id = submit(client)
    finish(client, case_id)
    response = client.get(f"/api/investigations/{case_id}/report.pdf")

    if not pdf_available():  # pragma: no cover - depends on the environment
        assert response.status_code == 503
        assert "reportlab" in response.json()["detail"]
        return
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    assert f'filename="{case_id}.pdf"' in response.headers["content-disposition"]


def test_the_trace_separates_wall_clock_from_summed_agent_time(client: TestClient) -> None:
    case_id = submit(client)
    finish(client, case_id)
    trace = client.get(f"/api/investigations/{case_id}/trace").json()

    state = client.get(f"/api/investigations/{case_id}").json()
    assert trace["plan"] == node_plan()
    # One span per agent execution, and the set matches what actually ran —
    # a trace that lost an agent would be a latency table with a hole in it.
    assert {s["agent"] for s in trace["spans"]} == {r["agent"] for r in state["agent_results"]}
    assert trace["elapsed_ms"] >= 0
    assert "agent_ms" in trace


# --------------------------------------------------------------------------
# False-positive discipline
# --------------------------------------------------------------------------


def test_a_legitimate_bank_alert_produces_no_manufactured_signal(client: TestClient) -> None:
    """A benign input must come out benign.

    There is nothing to score yet, so the claim this can make is precise: the
    lifecycle produces no type conflict, no degradation and no classification
    for an ordinary debit alert. When 4.6 adds a score, this test is where the
    benign case is already waiting.

    The alert names `grocerystore@ybl`, so `UPI_ID` is detected — and that is
    the point rather than a wrinkle. Extraction is not judgement: a legitimate
    SMS about a legitimate payment contains a legitimate VPA, and a system that
    treated "a UPI ID is present" as a signal would flag every bank alert in
    India. The identifier is recorded; nothing is concluded from its existence.
    """
    case_id = submit(client, BENIGN_TEXT)
    state = finish(client, case_id)

    assert state["classification"] is None
    assert state["risk_score"] is None
    labels = [f["label"] for r in state["agent_results"] for f in r["findings"]]
    assert "type_conflict" not in labels
    assert state["input_types"] == ["TEXT", "UPI_ID"]
    assert client.get(f"/api/investigations/{case_id}/report").json()["evidence"] == []

    # Nothing in `degraded` is a claim about this message. Every tag is an
    # `agent:<name>:degraded` capability shortfall — on a machine with no
    # promoted checkpoint the stage classifier serves the lexical model and says
    # so. A tag that named the evidence would be a finding wearing a shortfall's
    # clothes.
    assert all(d.startswith("agent:") and d.endswith(":degraded") for d in state["degraded"]), (
        state["degraded"]
    )

    # And the inherited engine, now wired into the graph, does not manufacture a
    # threat out of an ordinary bank alert.
    fusion = next(r for r in state["agent_results"] if r["agent"] == "threat_fusion")
    assert fusion["features"]["threat_score"] < 25.0
    level = next(f["value"] for f in fusion["findings"] if f["label"] == "threat_level")
    assert level == "CALM"


# --------------------------------------------------------------------------
# Tenancy
# --------------------------------------------------------------------------


def _scope_of(client: TestClient) -> str:
    """The evidence scope the open-mode caller acts under."""
    from services.api.auth import _open_mode_user
    from services.api.orgs import evidence_scope

    db = SessionLocal()
    try:
        scope = evidence_scope(_open_mode_user(db))
    finally:
        db.close()
    assert scope is not None
    return scope


def _user_in_new_org(email: str, role: str = "analyst") -> str:
    """A user in a brand-new organisation, and a bearer token for them.

    Open mode honours a presented token, so this is enough to act as another
    tenant without turning enforcement on for the whole module.
    """
    from services.api.auth import create_token, create_user, get_user_by_email
    from services.api.orgs import create_org

    db = SessionLocal()
    try:
        user = get_user_by_email(db, email)
        if user is None:
            org = create_org(db, f"Test Org {email}")
            user = create_user(db, email, "password12345", role=role, org_id=org.id)
        return create_token(user)
    finally:
        db.close()


def _user_without_org(email: str) -> str:
    from services.api.auth import create_token, create_user, get_user_by_email

    db = SessionLocal()
    try:
        user = get_user_by_email(db, email)
        if user is None:
            user = create_user(db, email, "password12345", role="admin", org_id=None)
        return create_token(user)
    finally:
        db.close()


def test_another_organisation_cannot_read_or_erase_a_case(client: TestClient) -> None:
    """404, not 403: a case id must not be probeable for existence from outside
    the organisation that owns it."""
    case_id = submit(client)
    finish(client, case_id)

    other = {"Authorization": f"Bearer {_user_in_new_org('tenant.b@aegis.local', 'admin')}"}
    assert client.get(f"/api/investigations/{case_id}", headers=other).status_code == 404
    assert client.get(f"/api/investigations/{case_id}/report", headers=other).status_code == 404
    assert client.get(f"/api/investigations/{case_id}/trace", headers=other).status_code == 404
    assert client.get(f"/api/investigations/{case_id}/stream", headers=other).status_code == 404
    assert client.delete(f"/api/investigations/{case_id}", headers=other).status_code == 404

    # And the owner's own view is untouched by the attempt.
    assert client.get(f"/api/investigations/{case_id}").status_code == 200


def test_a_user_with_no_organisation_is_refused_rather_than_shown_nothing(
    client: TestClient,
) -> None:
    headers = {"Authorization": f"Bearer {_user_without_org('orphan@aegis.local')}"}
    response = client.post("/api/investigations", json={"text": SCAM_TEXT}, headers=headers)
    assert response.status_code == 403
    assert "organisation" in response.json()["detail"]


def test_the_blob_store_refuses_another_organisations_uri(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(blob_store, "ROOT", tmp_path)
    uri = blob_store.EvidenceBlobs("org-1").write("AEG-X", "a" * 64, b"secret")
    assert uri is not None
    assert blob_store.EvidenceBlobs("org-1").read(uri) == b"secret"
    with pytest.raises(blob_store.BlobRejected):
        blob_store.EvidenceBlobs("org-2").read(uri)


@pytest.mark.parametrize(
    "uri",
    [
        "aegis-blob:org-1/../../etc/passwd",
        "aegis-blob:../org-1/AEG-X/" + "a" * 64,
        "aegis-blob:org-1/AEG-X/not-a-digest",
        "file:///etc/passwd",
    ],
)
def test_a_traversing_blob_uri_is_rejected(uri: str, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(blob_store, "ROOT", tmp_path)
    with pytest.raises(blob_store.BlobRejected):
        blob_store.EvidenceBlobs("org-1").read(uri)


# --------------------------------------------------------------------------
# RBAC
# --------------------------------------------------------------------------


def test_creating_an_investigation_requires_an_analyst(client: TestClient) -> None:
    headers = {"Authorization": f"Bearer {_user_in_new_org('read.only@aegis.local', 'viewer')}"}
    response = client.post("/api/investigations", json={"text": SCAM_TEXT}, headers=headers)
    assert response.status_code == 403


def test_erasing_an_investigation_requires_an_admin(client: TestClient) -> None:
    """Erasure destroys evidence, so it sits a rung above creating a case."""
    token = _user_in_new_org("analyst.only@aegis.local", "analyst")
    headers = {"Authorization": f"Bearer {token}"}
    case_id = submit(client, headers=headers)
    read_stream(client, case_id, headers=headers)

    assert client.delete(f"/api/investigations/{case_id}", headers=headers).status_code == 403


# --------------------------------------------------------------------------
# Erasure
# --------------------------------------------------------------------------


def test_erasure_removes_the_case_its_rows_and_its_bytes(client: TestClient) -> None:
    response = client.post(
        "/api/investigations", files={"files": ("notice.png", _PNG, "image/png")}
    )
    case_id = response.json()["case_id"]
    state = finish(client, case_id)
    uri = state["inputs"][0]["uri"]
    scope = _scope_of(client)
    assert blob_store.EvidenceBlobs(scope).read(uri) is not None

    erased = client.delete(f"/api/investigations/{case_id}")
    assert erased.status_code == 200
    assert erased.json() == {
        "case_id": case_id,
        "erased": True,
        "blobs_removed": 1,
        "was_running": False,
    }

    assert client.get(f"/api/investigations/{case_id}").status_code == 404
    assert blob_store.EvidenceBlobs(scope).read(uri) is None
    db = SessionLocal()
    try:
        assert EvidenceStore(db, scope).load(case_id) is None
    finally:
        db.close()


def test_erasure_is_audited_even_though_the_case_is_gone(client: TestClient) -> None:
    """The audit row survives the erasure it records.

    Deliberate: a deletion nobody can account for is its own problem, and §8
    puts "every investigation" in the audit log. The row names the case id and
    the actor, not the evidence.
    """
    case_id = submit(client)
    finish(client, case_id)
    client.delete(f"/api/investigations/{case_id}")

    events = client.get("/api/audit", params={"action": "investigation.delete"}).json()["events"]
    assert any(e["target"] == case_id for e in events)

    created = client.get("/api/audit", params={"action": "investigation.create"}).json()["events"]
    assert any(e["target"] == case_id for e in created)


def test_erasing_an_unknown_case_is_a_404(client: TestClient) -> None:
    assert client.delete("/api/investigations/AEG-000000000000").status_code == 404


def test_erasure_cancels_a_run_that_is_still_going() -> None:
    """An erasure must stop the graph before it deletes the rows.

    Otherwise the run finishes a moment later and saves them straight back — an
    erasure that quietly undoes itself. Driven through the runner rather than
    the API so the race is deterministic rather than hoped for.
    """
    from services.api.agents.base import AgentContext, Stage

    started = asyncio.Event()

    class _Slow:
        name = "test_slow_agent"
        version = "1.0.0"
        stage = Stage.INVESTIGATE

        def can_handle(self, state: InvestigationState) -> bool:
            return True

        async def run(self, state: InvestigationState, ctx: AgentContext) -> AgentResult:
            started.set()
            await asyncio.sleep(30)
            raise AssertionError("the slow agent was never cancelled")

    registry.register(_Slow)

    saves: List[str] = []

    class _RecordingStore:
        def __init__(self, db: Any, org_id: str) -> None:
            self.org_id = org_id

        def save(self, state: InvestigationState) -> int:
            saves.append(state.case_id)
            return 1

    async def scenario() -> None:
        import services.api.investigations.runner as runner_mod

        local = InvestigationRunner(session_factory=lambda: None)  # type: ignore[arg-type,return-value]
        original = runner_mod.EvidenceStore
        runner_mod.EvidenceStore = _RecordingStore  # type: ignore[misc]
        try:
            run = local.start(_queued_state("AEG-CANCELME"), "org-1")
            await asyncio.wait_for(started.wait(), timeout=10)
            assert await local.cancel("org-1", "AEG-CANCELME") is True
            assert run.finished
            assert run.events[-1].kind.value == "cancelled"
            assert run.state.status is InvestigationStatus.CANCELLED
        finally:
            runner_mod.EvidenceStore = original  # type: ignore[misc]

    try:
        asyncio.run(scenario())
    finally:
        registry._REGISTRY.pop("test_slow_agent", None)

    assert saves == [], "a cancelled run wrote the rows an erasure is about to delete"


# --------------------------------------------------------------------------
# Degradation
# --------------------------------------------------------------------------


def test_an_unwritable_evidence_directory_degrades_the_submission(
    client: TestClient, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unwritable disk must not cost a frightened person their answer.

    The item keeps its hash, its metadata and its inline text, the tag says what
    was lost, and the investigation still completes.
    """
    blocked = tmp_path / "not-a-directory"
    blocked.write_bytes(b"")
    monkeypatch.setattr(blob_store, "ROOT", blocked)

    response = client.post(
        "/api/investigations", files={"files": ("notice.png", _PNG, "image/png")}
    )
    assert response.status_code == 202
    degraded = response.json()["degraded"]
    # Two tags, and they are different kinds of thing. The blob tag is what this
    # test is about. `queue:in_process` arrived with 1.8 and says where the graph
    # will run — the suite pins the queue off, so it is deterministic here; the
    # set comparison is what keeps a third, unexplained tag from creeping in.
    assert "store:blobs:unwritable" in degraded
    assert set(degraded) == {"store:blobs:unwritable", "queue:in_process"}

    case_id = response.json()["case_id"]
    state = finish(client, case_id)
    assert state["status"] == "COMPLETE"
    assert state["inputs"][0]["uri"] is None
    assert state["inputs"][0]["sha256"]
    assert "store:blobs:unwritable" in state["degraded"]


def test_a_failed_final_write_degrades_rather_than_losing_the_answer(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The stream still delivers the investigation; `degraded` says it is not
    filed. A 500 here would throw away work that had already been done.

    The store is refused *before* the submission, and that ordering is the whole
    test. Patching afterwards races the graph: `runner.start()` puts the run on a
    background task that keeps going between requests, so on a machine where the
    graph finishes first the save succeeds, `degraded` is empty and the assertion
    below fails on something that is not a defect. That is not hypothetical — it
    is what turned CI red while the same test passed locally, and it reproduces
    on demand with a three-second sleep in the gap.

    Only the runner's reference is patched. `routes/investigations.py` imports
    `EvidenceStore` separately, so the QUEUED row is still written at submission
    and this stays a test about the *final* write.
    """
    import services.api.investigations.runner as runner_mod
    from services.api.investigations.runner import WRITE_FAILED

    class _Refusing:
        def __init__(self, db: Any, org_id: str) -> None:
            pass

        def save(self, state: InvestigationState) -> int:
            raise RuntimeError("disk is on fire")

    monkeypatch.setattr(runner_mod, "EvidenceStore", _Refusing)

    case_id = submit(client)
    events = read_stream(client, case_id)

    terminal = events[-1]
    assert terminal["event"] == "complete"
    assert WRITE_FAILED in terminal["data"]["degraded"]
    assert WRITE_FAILED in client.get(f"/api/investigations/{case_id}").json()["degraded"]


def test_an_orchestrator_failure_is_reported_as_failed_not_as_a_clean_complete(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FAILED is reserved for the orchestrator itself being unable to run.

    Every agent erroring is still a COMPLETE investigation with an honest
    `degraded` list — the graph's own `finish` node makes that call. This is the
    other case, and it must not arrive dressed as a completed investigation with
    nothing in it, which would read as "we looked and found nothing".
    """
    import services.api.investigations.runner as runner_mod

    async def _explode(state: InvestigationState, **kw: Any) -> Any:
        raise RuntimeError("langgraph is unwell")
        yield  # pragma: no cover - makes this an async generator

    monkeypatch.setattr(runner_mod, "investigate_stream", _explode)
    case_id = submit(client)
    events = read_stream(client, case_id)

    assert events[-1]["event"] == "failed"
    assert "langgraph is unwell" in events[-1]["data"]["error"]
    assert "orchestrator:failed" in events[-1]["data"]["degraded"]

    state = client.get(f"/api/investigations/{case_id}").json()
    assert state["status"] == "FAILED"
    assert state["completed_at"]

    # And it is durable: a failure that is not written down is a case that
    # silently reads as QUEUED forever.
    db = SessionLocal()
    try:
        stored = EvidenceStore(db, _scope_of(client)).load(case_id)
    finally:
        db.close()
    assert stored is not None and stored.status is InvestigationStatus.FAILED


def test_blob_health_flags_the_mismatch_and_not_an_all_ephemeral_install(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`blobs:ephemeral` names the surprising state, not the documented one.

    Everything ephemeral is already described by `db:ephemeral`; a second tag
    saying the same thing trains people to ignore both. A durable database with
    an ephemeral evidence directory is different — the case outlives its own
    screenshots — and that is the one worth raising.
    """
    monkeypatch.setattr(blob_store, "EPHEMERAL", True)
    monkeypatch.setattr(blob_store, "DB_EPHEMERAL", True)
    assert "blobs:ephemeral" not in blob_store.degraded()

    monkeypatch.setattr(blob_store, "DB_EPHEMERAL", False)
    assert "blobs:ephemeral" in blob_store.degraded()

    monkeypatch.setattr(blob_store, "EPHEMERAL", False)
    assert "blobs:ephemeral" not in blob_store.degraded()


def test_health_reports_both_contract_versions(client: TestClient) -> None:
    """Serving two contracts and reporting one is how a client checks the wrong
    version. Task 1.1 recorded the gap and parked it until an investigation was
    actually served; both numbers are read from `schema/` so neither can drift
    from the contract it describes.
    """
    from schema.models import CONTRACT_VERSION, INVESTIGATION_CONTRACT_VERSION

    body = client.get("/api/health").json()
    assert body["contract_version"] == CONTRACT_VERSION
    assert body["investigation_contract_version"] == INVESTIGATION_CONTRACT_VERSION


def test_health_reports_where_evidence_bytes_live(client: TestClient) -> None:
    storage = client.get("/api/health").json()["evidence_storage"]
    assert storage["backend"] == "filesystem"
    assert storage["root"]
    assert isinstance(storage["persistent"], bool)
    assert storage["writable"] is True
