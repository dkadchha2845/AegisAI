"""
The trace recorder.

    .venv/bin/python -m pytest services/api/tests/test_orchestration_trace.py -q

The trace is three things at once (ARCHITECTURE.md §2): the debug tool, the UI's
agent panel, and the paper's per-agent success-rate table. That third use is why
the failed attempts have to be in it, and why `total_ms` is wall clock rather
than the sum of the spans.
"""

from __future__ import annotations

from schema.models import AgentStatus
from services.api.orchestration.trace import TraceRecorder


def rec() -> TraceRecorder:
    return TraceRecorder(origin=0.0)


def test_span_ids_encode_node_attempt_and_depth() -> None:
    r = rec()
    assert r.span_id("investigate/url_agent", 2, 1) == "investigate/url_agent#2@1"


def test_span_ids_do_not_depend_on_completion_order() -> None:
    """The subtle one.

    An id assigned from a counter as each node *finishes* depends on which agent
    returned first, so two runs of the same input produce different traces and
    the ablation study compares runs that are not comparable. Ids come from the
    plan, so recording in a different order changes nothing.
    """
    a, b = rec(), rec()
    a.append(node="n/one", status=AgentStatus.OK, t_start=0.0, t_end=0.1)
    a.append(node="n/two", status=AgentStatus.OK, t_start=0.0, t_end=0.2)

    b.append(node="n/two", status=AgentStatus.OK, t_start=0.0, t_end=0.2)
    b.append(node="n/one", status=AgentStatus.OK, t_start=0.0, t_end=0.1)

    assert [s.span_id for s in a.ordered()] == [s.span_id for s in b.ordered()]


def test_latency_is_derived_from_the_span_when_not_supplied() -> None:
    r = rec()
    span = r.append(node="n", status=AgentStatus.OK, t_start=0.25, t_end=0.75)
    assert span.latency_ms == 500


def test_a_supplied_latency_wins() -> None:
    """The agent's own measurement is closer to the work than the harness's.

    The harness clock includes scheduling; the agent's excludes it. When both
    exist, the agent's is the honest number for "how long did this take".
    """
    r = rec()
    span = r.append(node="n", status=AgentStatus.OK, t_start=0.0, t_end=1.0, latency_ms=42)
    assert span.latency_ms == 42


def test_every_attempt_gets_its_own_span() -> None:
    r = rec()
    r.append(node="n/flaky", status=AgentStatus.ERROR, t_start=0.0, t_end=0.1, attempt=1)
    r.append(node="n/flaky", status=AgentStatus.OK, t_start=0.2, t_end=0.3, attempt=2)

    spans = r.ordered()
    assert [s.attempt for s in spans] == [1, 2]
    assert [s.status for s in spans] == [AgentStatus.ERROR, AgentStatus.OK]
    assert len({s.span_id for s in spans}) == 2


def test_ordering_is_by_depth_then_node_then_attempt() -> None:
    r = rec()
    r.append(node="n/zulu", status=AgentStatus.OK, t_start=0.0, t_end=0.1)
    r.append(node="n/alpha", status=AgentStatus.OK, t_start=0.0, t_end=0.1, depth=1)
    r.append(node="n/alpha", status=AgentStatus.OK, t_start=0.0, t_end=0.1)

    assert [(s.depth, s.node) for s in r.ordered()] == [
        (0, "n/alpha"),
        (0, "n/zulu"),
        (1, "n/alpha"),
    ]


def test_negative_times_are_clamped_rather_than_stored() -> None:
    """`TraceSpan.t_start` is `ge=0` on the contract; a clock that briefly reads
    backwards should not fail an investigation over a rounding artefact."""
    r = rec()
    span = r.append(node="n", status=AgentStatus.OK, t_start=-0.0001, t_end=0.5)
    assert span.t_start == 0.0


def test_total_is_wall_clock_not_the_sum_of_the_spans() -> None:
    """With a parallel fan-out the sum exceeds the elapsed time.

    Quoting the sum would overstate how long a citizen actually waited — three
    agents each taking 300 ms concurrently is a 300 ms wait, not 900 ms.
    """
    r = rec()
    for name in ("a", "b", "c"):
        r.append(node=f"n/{name}", status=AgentStatus.OK, t_start=0.0, t_end=0.3)

    assert sum(s.latency_ms for s in r.spans) == 900
    assert r.total_ms() == 300


def test_an_empty_trace_totals_zero_rather_than_exploding() -> None:
    assert rec().total_ms() == 0
    assert rec().by_status() == {}


def test_status_counts_are_sorted_for_stable_output() -> None:
    r = rec()
    r.append(node="n/1", status=AgentStatus.OK, t_start=0.0, t_end=0.1)
    r.append(node="n/2", status=AgentStatus.ERROR, t_start=0.0, t_end=0.1)
    r.append(node="n/3", status=AgentStatus.OK, t_start=0.0, t_end=0.1)
    assert r.by_status() == {"error": 1, "ok": 2}
