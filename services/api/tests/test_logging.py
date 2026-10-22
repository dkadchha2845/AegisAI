"""
One ID follows a request, and another a case, through parseable logs (T-12,
audit D-08).

Before T-12 the service had sixteen bare `print()` lines and nothing that tied
a line to the request or investigation behind it.
"""

from __future__ import annotations

import ast
import asyncio
import json
import logging
from pathlib import Path
from typing import Iterator, List

import pytest
from fastapi.testclient import TestClient

from services.api import logs
from services.api.db import init_db
from services.api.main import app

ROOT = Path(__file__).resolve().parents[3]


class _Collect(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: List[logging.LogRecord] = []
        self.formatter_ = logs.JsonFormatter()

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    def lines(self) -> List[dict]:
        return [json.loads(self.formatter_.format(r)) for r in self.records]


@pytest.fixture
def captured() -> Iterator[_Collect]:
    logs.configure()
    handler = _Collect()
    root = logging.getLogger(logs.ROOT)
    root.addHandler(handler)
    try:
        yield handler
    finally:
        root.removeHandler(handler)


# --- the context -------------------------------------------------------------


def test_the_ids_survive_an_await_a_task_and_a_thread_hop() -> None:
    async def scenario() -> tuple:
        with logs.bind(request="req-1", case="AEG-1"):
            await asyncio.sleep(0)
            after_await = (logs.request_id.get(), logs.case_id.get())
            in_task = await asyncio.create_task(_read())
            in_thread = await asyncio.to_thread(lambda: (logs.request_id.get(), logs.case_id.get()))
        outside = (logs.request_id.get(), logs.case_id.get())
        return after_await, in_task, in_thread, outside

    async def _read() -> tuple:
        return logs.request_id.get(), logs.case_id.get()

    after_await, in_task, in_thread, outside = asyncio.run(scenario())
    assert after_await == in_task == in_thread == ("req-1", "AEG-1")
    assert outside == (None, None)


def test_a_line_is_one_json_object_with_both_ids(captured: _Collect) -> None:
    with logs.bind(request="req-9", case="AEG-9"):
        logs.get_logger("test").info("hello", extra={"agent": "trust_passport"})
    line = captured.lines()[-1]
    assert line["msg"] == "hello"
    assert line["request_id"] == "req-9" and line["case_id"] == "AEG-9"
    assert line["agent"] == "trust_passport"
    assert line["ts"].endswith("Z") and line["level"] == "INFO"


# --- requests ----------------------------------------------------------------


def test_every_response_carries_a_request_id() -> None:
    with TestClient(app) as client:
        r = client.get("/api/health")
        assert len(r.headers["x-request-id"]) == 32
        r = client.post("/api/analyze/text", json={})  # a validation error
        assert r.headers.get("x-request-id")


def test_a_well_formed_supplied_id_is_kept_and_a_hostile_one_replaced() -> None:
    with TestClient(app) as client:
        kept = client.get("/api/health", headers={"X-Request-ID": "trace-abc_123"})
        assert kept.headers["x-request-id"] == "trace-abc_123"
        for hostile in ('a"}, {"level": "x', "x" * 65):
            r = client.get("/api/health", headers={"X-Request-ID": hostile})
            assert r.headers["x-request-id"] != hostile


def test_the_request_line_has_the_path_but_never_the_query(captured: _Collect) -> None:
    with TestClient(app) as client:
        r = client.get("/api/health?token=s3cret-session-token")
    rid = r.headers["x-request-id"]
    line = next(x for x in captured.lines() if x["msg"] == "request" and x["request_id"] == rid)
    assert line["path"] == "/api/health" and line["status"] == 200
    assert "s3cret" not in json.dumps(captured.lines())


# --- an investigation ----------------------------------------------------------

MARKER = "Zqxv-UNIQUE-EVIDENCE-7731"


def test_an_investigation_logs_under_one_request_and_one_case_and_no_evidence(
    captured: _Collect,
) -> None:
    init_db()
    text = f"Main CBI officer bol raha hoon {MARKER}. Abhi transfer karo warna arrest hoga."
    with TestClient(app) as client:
        r = client.post("/api/investigations", json={"text": text})
        assert r.status_code == 202, r.text
        rid, case = r.headers["x-request-id"], r.json()["case_id"]
        with client.stream("GET", f"/api/investigations/{case}/stream") as stream:
            for _ in stream.iter_lines():
                pass

    mine = [x for x in captured.lines() if x.get("case_id") == case]
    messages = [x["msg"] for x in mine]
    assert messages[0] == "investigation started" and "investigation finished" in messages
    spans = [x for x in mine if x["msg"] == "span"]
    assert {x["agent"] for x in spans} >= {"entity_extractor", "trust_passport", "threat_fusion"}
    # The investigation runs in a task the request created, so it carries the
    # request's id as well as its own.
    assert {x["request_id"] for x in mine} == {rid}
    assert MARKER not in json.dumps(captured.lines())


def test_a_reset_request_logs_no_email(captured: _Collect) -> None:
    init_db()
    from services.api import auth as auth_mod
    from services.api.db import SessionLocal

    db = SessionLocal()
    try:
        auth_mod.seed_admin(db)
    finally:
        db.close()
    with TestClient(app) as client:
        client.post("/api/auth/password/forgot", json={"email": "admin@aegis.local"})
    issued = [x for x in captured.lines() if x["msg"] == "password reset token issued"]
    assert issued and "admin@aegis.local" not in json.dumps(issued)


# --- no print() left -----------------------------------------------------------

#: Command-line tools, whose stdout *is* their output.
CLI_MODULES = {
    "services/api/seed.py",
    "services/api/dbshell.py",
    "services/api/orchestration/__main__.py",
}


def _prints(tree: ast.AST) -> List[int]:
    """Line numbers of print() calls outside a function named `main`."""
    found: List[int] = []

    def visit(node: ast.AST, in_main: bool) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            in_main = in_main or node.name == "main"
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "print"
            and not in_main
        ):
            found.append(node.lineno)
        for child in ast.iter_child_nodes(node):
            visit(child, in_main)

    visit(tree, False)
    return found


def test_no_served_module_prints() -> None:
    offenders = []
    for base in ("services/api", "services/worker"):
        for path in sorted((ROOT / base).rglob("*.py")):
            rel = path.relative_to(ROOT).as_posix()
            if "/tests/" in rel or rel in CLI_MODULES:
                continue
            lines = _prints(ast.parse(path.read_text(encoding="utf-8")))
            offenders += [f"{rel}:{n}" for n in lines]
    assert not offenders, "print() in a served module — use services.api.logs: " + ", ".join(offenders)
