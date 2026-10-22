"""
The investigation extracts its entities (T-18, audit B-03).

Before T-18 the input classifier detected `URL`, `UPI_ID` and `TEXT` in a
message holding a link, a VPA and a number, and `state.entities` still came
back `{}`: no agent in the graph wrote it.
"""

from __future__ import annotations

import asyncio
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from schema.models import (
    AgentResult,
    AgentStatus,
    EvidenceItem,
    InputType,
    InvestigationState,
    InvestigationStatus,
    utc_now_iso,
)
from services.api.agents import registry
from services.api.agents.base import Stage
from services.api.agents.entities import agent as entity_mod
from services.api.agents.registry import RegistrationError
from services.api.db import init_db
from services.api.main import app
from services.api.orchestration import graph as orch

MIXED = (
    "Your parcel is held. Pay the fee to customs.clear@okaxis or call 9812345678. "
    "Track it at https://india-post-track.top/parcel?id=88."
)
MASKED_ALERT = "Rs 450.00 debited from A/c XX3421 on 24-08-26. Not you? Call 1800-11-2211. -SBI"


def _state(*texts: str) -> InvestigationState:
    return InvestigationState(
        case_id="AEG-ENT",
        org_id="org-1",
        created_by="t@aegis.local",
        created_at=utc_now_iso(),
        inputs=[
            EvidenceItem(id=f"ev-{i:02d}", kind=InputType.TEXT, text=t)
            for i, t in enumerate(texts, 1)
        ],
        input_types=[InputType.TEXT],
    )


def _run(state: InvestigationState) -> InvestigationState:
    return asyncio.run(orch.investigate(state))


def _entity_result(state: InvestigationState) -> AgentResult:
    return next(r for r in state.agent_results if r.agent == entity_mod.NAME)


def test_a_link_a_vpa_and_a_number_are_all_extracted_with_their_source() -> None:
    done = _run(_state("Hello, this is about your order.", MIXED))
    assert done.entities.upi_ids == ["customs.clear@okaxis"]
    assert done.entities.phones == ["9812345678"]
    assert done.entities.urls == ["https://india-post-track.top/parcel?id=88"]
    assert "india-post-track.top" in done.entities.domains
    sources = {f.value: f.detail for f in _entity_result(done).findings}
    # Each identifier names the evidence item it was found in.
    assert sources["upi_ids:customs.clear@okaxis"] == "ev-02"
    assert sources["phones:9812345678"] == "ev-02"


def test_a_masked_account_and_a_toll_free_number_are_not_entities() -> None:
    """Benign: a bank debit SMS names an account and a number. Neither is an
    identifier anybody could be linked by — the account is masked, and the
    number is the bank's own toll-free line."""
    done = _run(_state(MASKED_ALERT))
    assert done.entities.phones == []
    assert done.entities.upi_ids == []
    assert done.entities.bank_accounts == []


def test_a_vpa_ending_a_sentence_is_kept() -> None:
    """Found by this task: "…to VPA grocerystore@ybl. Not you?" dropped the
    VPA, because a following "." was read as the middle of a longer domain."""
    done = _run(_state("Rs 450 debited to VPA grocerystore@ybl. Not you? -SBI"))
    assert done.entities.upi_ids == ["grocerystore@ybl"]


def test_a_failing_extractor_costs_the_entities_not_the_investigation(monkeypatch) -> None:
    def boom(text: str):
        raise RuntimeError("extractor down")

    monkeypatch.setattr(entity_mod, "extract_from_text", boom)
    done = _run(_state(MIXED))
    assert done.status is InvestigationStatus.COMPLETE
    assert _entity_result(done).status is AgentStatus.ERROR
    assert any(tag.startswith(f"agent:{entity_mod.NAME}") for tag in done.degraded)
    assert done.entities.upi_ids == []
    # The rest of the graph still ran and scored the text.
    assert done.risk_score is not None


def test_the_entities_reach_the_api() -> None:
    init_db()
    with TestClient(app) as client:
        response = client.post("/api/investigations", json={"text": MIXED})
        assert response.status_code == 202, response.text
        case_id = response.json()["case_id"]
        with client.stream("GET", f"/api/investigations/{case_id}/stream") as stream:
            for _ in stream.iter_lines():
                pass
        state = client.get(f"/api/investigations/{case_id}").json()
        report = client.get(f"/api/investigations/{case_id}/report").json()
    assert state["entities"]["upi_ids"] == ["customs.clear@okaxis"]
    assert report["entities"]["urls"] == ["https://india-post-track.top/parcel?id=88"]


# --- the declared-write mechanism the agent relies on ----------------------


@pytest.fixture
def scratch() -> Iterator[None]:
    added: list[str] = []
    yield added  # type: ignore[misc]
    for name in added:
        registry._REGISTRY.pop(name, None)


def test_an_agent_may_write_only_the_fields_it_declares(scratch) -> None:
    class Writes:
        name = "test_bad_writer"
        version = "0.1.0"
        stage = Stage.REASON
        writes = ("status",)

        def can_handle(self, state):
            return True

        async def run(self, state, ctx):  # pragma: no cover - never registered
            raise AssertionError

        def state_update(self, state, result):  # pragma: no cover
            return {}

    with pytest.raises(RegistrationError, match="may not write"):
        registry.register(Writes)


def test_two_agents_in_one_tier_may_not_write_the_same_field(scratch) -> None:
    class Second:
        name = "test_second_extractor"
        version = "0.1.0"
        stage = Stage.EXTRACT
        writes = ("entities",)

        def can_handle(self, state):  # pragma: no cover
            return True

        async def run(self, state, ctx):  # pragma: no cover
            raise AssertionError

        def state_update(self, state, result):  # pragma: no cover
            return {}

    with pytest.raises(RegistrationError, match="both write"):
        registry.register(Second)


def test_a_state_update_that_raises_is_tagged(monkeypatch) -> None:
    def broken(self, state, result):
        raise ValueError("bad update")

    monkeypatch.setattr(entity_mod.EntityExtractorAgent, "state_update", broken)
    done = _run(_state(MIXED))
    assert done.status is InvestigationStatus.COMPLETE
    assert f"state_update:{entity_mod.NAME}" in done.degraded
    assert done.entities.upi_ids == []
