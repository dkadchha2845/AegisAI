"""
The trace: one `TraceSpan` per node execution.

**Why it exists.** ARCHITECTURE.md §2 calls the trace "simultaneously the debug
tool, the UI's agent view, and the paper's per-agent success-rate table". One
recording serves all three, so it has to be complete — including the attempts
that failed, which are exactly the ones a convenient implementation drops.

**What it consumes.** Node executions, as they happen.

**What it outputs.** A list of `TraceSpan` from the contract in `schema/`.

**How it connects.** `graph.py` owns a recorder for the length of one
investigation and writes the spans onto `state.trace`. Nothing else records.

**How it is evaluated.** `test_orchestration_trace.py`: every executed node
appears, retries appear as separate attempts, latency is real, and span ids do
not depend on the order tasks happened to finish.

**Limitations, stated.** `t_start` and `t_end` are seconds since the
investigation began, measured with a monotonic clock, so they are correct for
durations and useless as wall-clock timestamps — deliberately, because a span
that carried an absolute time would be one more thing to get wrong across a
resume from a checkpoint hours later.

Span ids are the subtle part
----------------------------
The obvious implementation assigns an id from an incrementing counter as each
node finishes. Under `asyncio.gather` that makes the id depend on which agent
happened to return first, so two runs of the same input produce different
traces, and the ablation study in 9.3 compares runs that are not comparable.

So ids are assigned when the fan-out is *planned* — from the sorted agent list,
before anything runs — and the recorder only fills in the timings.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Optional

from schema.models import AgentStatus, TraceSpan


@dataclass
class TraceRecorder:
    """Collects spans for one investigation.

    Not thread-safe and does not need to be: everything runs on one event loop,
    and `append()` is called from coroutines that never yield inside it.
    """

    #: Monotonic origin. Every `t_start` / `t_end` is relative to this.
    origin: float = field(default_factory=time.monotonic)
    spans: List[TraceSpan] = field(default_factory=list)

    def now(self) -> float:
        return time.monotonic() - self.origin

    def span_id(self, node: str, attempt: int = 1, depth: int = 0) -> str:
        """A deterministic id, derived from the plan rather than the outcome.

        `investigate/url_investigation#2@1` reads as "the second attempt at the
        url_investigation node, one level deep". Two runs of the same input
        produce the same ids, which is what makes two traces diffable.
        """
        return f"{node}#{attempt}@{depth}"

    def append(
        self,
        *,
        node: str,
        status: AgentStatus,
        t_start: float,
        t_end: float,
        agent: Optional[str] = None,
        version: Optional[str] = None,
        attempt: int = 1,
        depth: int = 0,
        parent_span_id: Optional[str] = None,
        error: Optional[str] = None,
        latency_ms: Optional[int] = None,
    ) -> TraceSpan:
        """Record one execution. Every attempt gets its own span.

        A node that succeeded on its second try is not the same as one that
        succeeded first time, and a latency percentile that silently averages
        the two is a measurement that lies (9.4). So the failed attempt is
        recorded, not overwritten.
        """
        span = TraceSpan(
            span_id=self.span_id(node, attempt, depth),
            node=node,
            agent=agent,
            version=version,
            t_start=max(0.0, t_start),
            t_end=max(0.0, t_end),
            latency_ms=latency_ms if latency_ms is not None else int((t_end - t_start) * 1000),
            status=status,
            attempt=attempt,
            depth=depth,
            parent_span_id=parent_span_id,
            error=error,
        )
        self.spans.append(span)
        return span

    def ordered(self) -> List[TraceSpan]:
        """Spans in a stable order: by depth, then node, then attempt.

        Sorted rather than chronological, again for diffability. Chronological
        order is recoverable from `t_start`, which is on every span; the reverse
        is not true of an order that depends on scheduling.
        """
        return sorted(self.spans, key=lambda s: (s.depth, s.node, s.attempt))

    # ---- summaries the UI and the paper both want -------------------------

    def total_ms(self) -> int:
        """Wall clock for the whole investigation, not the sum of the spans.

        The difference is the point: with a parallel fan-out the sum of node
        latencies exceeds the elapsed time, and quoting the sum would overstate
        how long a citizen waited.
        """
        if not self.spans:
            return 0
        return int(max(s.t_end for s in self.spans) * 1000)

    def by_status(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for s in self.spans:
            counts[s.status.value] = counts.get(s.status.value, 0) + 1
        return dict(sorted(counts.items()))
