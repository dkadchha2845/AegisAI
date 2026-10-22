"""
The feature-assembly contract, version 0 (T-19).

Every feature an agent emits is declared; a feature whose agent did not answer
is missing (None), never zero; the same state gives the same vector; and the
declarations cannot change without the committed hash changing with them.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import List

import pytest
from fastapi.testclient import TestClient

from schema.models import (
    AgentResult,
    AgentStatus,
    EvidenceItem,
    InputType,
    InvestigationState,
    utc_now_iso,
)
from services.api.agents import features as F
from services.api.agents import registry
from services.api.db import init_db
from services.api.main import app
from services.api.orchestration import graph as orch

CALL = (
    "CALLER: Hello, main Mumbai Cyber Crime se Inspector Rathore bol raha hoon.\n"
    "VICTIM: Ji, kya hua?\n"
    "CALLER: Aapke naam pe FIR darj hai. Disconnect mat kariye, kisi ko mat batana.\n"
    "VICTIM: Main darr gaya hoon, please.\n"
    "CALLER: Abhi RBI safe account mein 50000 transfer kariye warna arrest hoga."
)
SMS = (
    "Dear Customer, Rs 450.00 debited from A/c XX3421 to VPA grocerystore@ybl. "
    "Not you? Call 1800-11-2211. -SBI"
)
LINK = "Your parcel is held. Pay at https://india-post-track.top/x or call 9812345678."


def _state(*items: EvidenceItem) -> InvestigationState:
    return InvestigationState(
        case_id="AEG-FEAT",
        org_id="org-1",
        created_by="t@aegis.local",
        created_at=utc_now_iso(),
        inputs=list(items),
        input_types=sorted({i.kind for i in items}, key=list(InputType).index),
    )


def _text(text: str) -> EvidenceItem:
    return EvidenceItem(id="ev-01", kind=InputType.TEXT, text=text)


def _runs() -> List[InvestigationState]:
    return [
        asyncio.run(orch.investigate(_state(_text(CALL)))),
        asyncio.run(orch.investigate(_state(_text(SMS)))),
        asyncio.run(orch.investigate(_state(_text(LINK)))),
        asyncio.run(orch.investigate(_state(
            _text(CALL), EvidenceItem(id="ev-02", kind=InputType.PHONE, text="+18382247719")
        ))),
    ]


@pytest.fixture(scope="module")
def runs() -> List[InvestigationState]:
    return _runs()


def test_every_feature_an_agent_emits_is_declared(runs) -> None:
    undeclared = sorted({
        (r.agent, key)
        for state in runs for r in state.agent_results for key in r.features
        if key not in F.BY_NAME or F.BY_NAME[key].agent != r.agent
    })
    assert not undeclared, f"declare these in services/api/agents/features.py: {undeclared}"


def test_every_declared_producer_is_a_registered_agent() -> None:
    assert {f.agent for f in F.FEATURES} <= set(registry.names())


def test_the_vector_is_the_declared_inputs_in_order(runs) -> None:
    for state in runs:
        assert list(state.risk_features) == [f.name for f in F.INPUTS]
        # A judge never reads its own output.
        assert not {f.name for f in F.FEATURES if f.role == "output"} & set(state.risk_features)


def test_a_skipped_agent_is_missing_never_zero(runs) -> None:
    sms = runs[1]
    statuses = {r.agent: r.status for r in sms.agent_results}
    # A one-sided SMS has no victim side and no submitted number.
    assert "coercion_tracker" not in statuses or statuses["coercion_tracker"] is AgentStatus.SKIPPED
    for name in ("coercion_index", "victim_turns", "spoofing_risk", "number_fails"):
        assert sms.risk_features[name] is None, name
    # …while an agent that ran and saw nothing reports a true zero.
    assert sms.risk_features["stage:ISOLATION"] == 0.0


def test_an_agent_that_errored_is_missing() -> None:
    state = _state(_text(CALL))
    errored = AgentResult(agent="trust_passport", version="1.0.0", status=AgentStatus.ERROR,
                          error="boom", features={"trust_pct": 0.0})
    vector = F.assemble(state.model_copy(update={"agent_results": [errored]}))
    assert vector["trust_pct"] is None and vector["passport_fails"] is None


def test_a_degraded_agent_still_answers(runs) -> None:
    """DEGRADED is "answered from a fallback" in the contract. The coercion
    agent is DEGRADED on every text call for want of audio; its index is real."""
    call = runs[0]
    coercion = next(r for r in call.agent_results if r.agent == "coercion_tracker")
    assert coercion.status is AgentStatus.DEGRADED
    assert call.risk_features["coercion_index"] == coercion.features["coercion_index"]
    # …and audio-only features are missing, not zero.
    assert call.risk_features["speech_rate_wpm"] is None


def test_the_same_state_gives_the_same_vector(runs) -> None:
    for state in runs:
        assert F.assemble(state) == F.assemble(state.model_copy(deep=True)) == state.risk_features
    again = asyncio.run(orch.investigate(_state(_text(CALL))))
    assert again.risk_features == runs[0].risk_features


def test_values_fall_inside_their_declared_ranges(runs) -> None:
    for state in runs:
        for r in state.agent_results:
            for key, value in r.features.items():
                spec = F.BY_NAME[key]
                assert value >= spec.low, (key, value)
                assert spec.high is None or value <= spec.high, (key, value)
                if spec.dtype == "int":
                    assert float(value).is_integer(), (key, value)


def test_the_schema_cannot_change_without_its_hash() -> None:
    assert F.schema_digest() == F.SCHEMA_SHA256, (
        "the feature declarations changed: review the change, then set "
        f"SCHEMA_SHA256 = {F.schema_digest()!r} in services/api/agents/features.py"
    )
    tweaked = [replace(F.FEATURES[0], high=1.0), *F.FEATURES[1:]]
    assert F.schema_digest(tweaked) != F.SCHEMA_SHA256


def test_a_failed_assembly_costs_the_vector_not_the_case(monkeypatch) -> None:
    def boom(state):
        raise RuntimeError("assembly down")

    monkeypatch.setattr(F, "assemble", boom)
    done = asyncio.run(orch.investigate(_state(_text(CALL))))
    assert done.status.value == "COMPLETE" and done.risk_score is not None
    assert done.risk_features == {} and orch.FEATURES_UNAVAILABLE in done.degraded


def test_the_api_returns_the_vector_with_missing_as_null() -> None:
    init_db()
    with TestClient(app) as client:
        case_id = client.post("/api/investigations", json={"text": SMS}).json()["case_id"]
        with client.stream("GET", f"/api/investigations/{case_id}/stream") as stream:
            for _ in stream.iter_lines():
                pass
        features = client.get(f"/api/investigations/{case_id}").json()["risk_features"]
    assert list(features) == [f.name for f in F.INPUTS]
    assert features["spoofing_risk"] is None
    assert features["input_type:TEXT"] == 1.0
