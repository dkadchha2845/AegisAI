"""
The fingerprint that makes "deterministic" a checkable claim rather than a hope.

**Why it exists.** Task 1.3's hardest acceptance criterion is *same input +
fixed seeds ⇒ same output*, and ADR-0004 rests the whole ablation study on it:
removing one agent and re-measuring only means something if two runs of the
unchanged system are identical. But two runs are *never* byte-identical, because
an investigation records how long it took. So the claim has to be stated
precisely, and this module is where that precision lives.

**What it consumes.** A finished `InvestigationState`.

**What it outputs.** A SHA-256 over everything that must not vary, with the
things that legitimately vary removed first.

**How it connects.** `graph.py` exposes it; the determinism test asserts two
runs agree; Phase 9's harness will use it to prove an ablation differed *because
of the ablation*.

**How it is evaluated.** `test_orchestration_determinism.py`: two runs of the
same input over agents with deliberately varying latency produce one
fingerprint, and changing any substantive field changes it.

**What is excluded, and why each one is legitimate**

| Excluded | Why it varies | Why that is not a determinism failure |
|---|---|---|
| `latency_ms`, `t_start`, `t_end` | Wall clock | The *work* is reproducible; the machine is not |
| `created_at`, `completed_at`, `received_at`, `retrieved_at` | Wall clock | Same |
| `case_id` | Generated per submission | Identity, not content |
| `TIRecord.cached` | Depends on cache warmth | The record's *content* is compared; whether it came from RAM is an operational detail |

Everything else is in. In particular `status`, `degraded`, `findings`,
`features`, `risk_score`, `evidence`, `recommendations`, the ordering of
`agent_results`, and the *shape* of the trace (node, agent, version, attempt,
depth, parent, status) are all fingerprinted. A change to any of them is a
behaviour change and must show up.

**Limitations, stated.** This proves the orchestrator is deterministic given
deterministic agents. It cannot make a non-deterministic agent reproducible — an
LLM at temperature > 0 or an un-seeded model will change the fingerprint, and it
*should*. Detecting that is the point: if this hash moves between two identical
runs, something in the system is not reproducible and the Phase 9 numbers built
on it are not either.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from schema.models import InvestigationState

#: Field names dropped wherever they appear, at any nesting depth.
VOLATILE_FIELDS = frozenset(
    {
        "latency_ms",
        "t_start",
        "t_end",
        "created_at",
        "completed_at",
        "received_at",
        "retrieved_at",
        "case_id",
        "cached",
    }
)


def _strip(value: Any) -> Any:
    """Recursively drop volatile fields, preserving order everywhere else.

    List order is *kept*, not sorted. That is deliberate: the order of
    `agent_results` is itself a determinism property — the orchestrator sorts
    the fan-out before merging it, and sorting again here would hide a
    regression in exactly the code this is meant to police.
    """
    if isinstance(value, dict):
        return {k: _strip(v) for k, v in value.items() if k not in VOLATILE_FIELDS}
    if isinstance(value, list):
        return [_strip(v) for v in value]
    return value


def canonical(state: InvestigationState) -> str:
    """The comparable form of an investigation, as JSON.

    `sort_keys=True` because a dict written in a different order is the same
    dict, while a *list* in a different order is not — see `_strip`.
    """
    return json.dumps(
        _strip(state.model_dump(mode="json")),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def fingerprint(state: InvestigationState) -> str:
    """SHA-256 of the canonical form. Short enough to paste into a commit."""
    return hashlib.sha256(canonical(state).encode("utf-8")).hexdigest()


def diff_summary(a: InvestigationState, b: InvestigationState) -> list[str]:
    """Which top-level keys differ. For when the fingerprint says "no" and the
    next question is "where?" — a 64-character hash is a bad error message."""
    da, db = _strip(a.model_dump(mode="json")), _strip(b.model_dump(mode="json"))
    out = []
    for key in sorted(set(da) | set(db)):
        if da.get(key) != db.get(key):
            out.append(key)
    return out
