"""
Per-node execution policy: how long an agent gets, and when a failure is worth
retrying.

**Why it exists.** ARCHITECTURE.md §2 gives every node a timeout and "2
attempts, exponential backoff, only for transient/network errors". Task 1.2
deliberately left retry out of `run_agent()` — retrying is a graph decision,
because it needs to know whether an error was transient, and that judgement
does not belong inside the thing that failed.

**What it consumes.** An agent (for its name) and an `AgentResult` (for its
error text).

**What it outputs.** A `NodePolicy` — timeout, attempt count, backoff schedule
— and a yes/no on whether a given failure should be retried.

**How it connects.** `graph.py` is the only caller. Agents never see it; an
agent that knew its own retry budget would be tempted to implement its own.

**How it is evaluated.** `test_orchestration_policy.py`: a transient failure is
retried and a permanent one is not, budgets are honoured, and the backoff
schedule is exact.

**Limitations, stated.** Transience is inferred from the exception *type name*
that `agents/base.py` formats into `AgentResult.error`. That coupling is real
and is pinned by a test. A richer alternative — carrying the exception class on
the result — would put a Python type into a contract that also has to serialise
to TypeScript, which is a worse trade. And the classification is necessarily
approximate: a `ValueError` from a malformed WHOIS response is permanent, while
the same class raised by a half-read socket is not. Retrying costs a second
attempt; misclassifying the other way costs an answer. The table below leans
toward not retrying, because a retry that cannot succeed spends a frightened
person's time twice.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from schema.models import AgentResult, AgentStatus
from services.api.agents.base import DEFAULT_TIMEOUT_S, Agent


@dataclass(frozen=True)
class NodePolicy:
    """What one node is allowed to spend.

    `attempts` is the *total* number of tries, not retries after the first, so
    the ARCHITECTURE.md figure of "2 attempts" reads literally here.

    There is no jitter. Jitter exists to desynchronise a thundering herd, which
    is not a problem a single investigation has, and it would make two runs of
    the same input differ — the exact property the Phase 9 ablations depend on
    not happening. Determinism wins.
    """

    timeout_s: float = DEFAULT_TIMEOUT_S
    attempts: int = 2
    backoff_s: float = 0.25
    backoff_factor: float = 2.0

    def backoff_before(self, attempt: int) -> float:
        """Seconds to wait before `attempt` (1-based). Zero before the first."""
        if attempt <= 1:
            return 0.0
        return self.backoff_s * (self.backoff_factor ** (attempt - 2))


#: Per-agent overrides. ARCHITECTURE.md §2: "default 8 s; TI 3 s; APK 120 s async".
#: Names that do not exist yet are listed on purpose — the budget is a design
#: decision recorded with the design, not a number invented when the agent is
#: written and the deadline is inconvenient.
POLICIES: dict[str, NodePolicy] = {
    # A feed that is slow is a feed that is down. Three seconds, then the
    # cached snapshot, because no citizen should wait on abuse.ch.
    "threat_intel": NodePolicy(timeout_s=3.0, attempts=2),
    # Static analysis of an APK is minutes of work. It never runs in-request
    # (1.8 moves it to the sandbox queue), and retrying two minutes of
    # decompilation to get the same answer is pure waste.
    "apk_static": NodePolicy(timeout_s=120.0, attempts=1),
    # Network-bound and worth a second try.
    "url_investigation": NodePolicy(timeout_s=10.0, attempts=2),
    # Local model inference. It either works or it is broken; a retry changes
    # nothing and doubles the latency of the slowest node in the graph.
    "scam_classifier": NodePolicy(timeout_s=8.0, attempts=1),
}

DEFAULT_POLICY = NodePolicy()

#: Exception types worth a second attempt: the network, the filesystem, and the
#: clock. Everything else is assumed to be a bug or bad input, where a retry
#: produces the same failure a little later.
_TRANSIENT_NAMES = frozenset(
    {
        "TimeoutError",
        "asyncio.TimeoutError",
        "ConnectionError",
        "ConnectionResetError",
        "ConnectionAbortedError",
        "ConnectionRefusedError",
        "BrokenPipeError",
        "OSError",
        "IOError",
        "socket.timeout",
        "ssl.SSLError",
        "SSLError",
        "HTTPError",
        "ReadTimeout",
        "ConnectTimeout",
        "ReadTimeoutError",
        "TemporaryFailure",
        "ServiceUnavailable",
        "TransientError",
    }
)

#: `agents/base.py` formats a caught exception as "TypeName: message". This
#: reads that prefix back. The coupling is deliberate and pinned by a test in
#: test_orchestration_policy.py, so the format cannot drift silently.
_ERROR_TYPE_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_.]*)\s*:")


def policy_for(agent: Agent) -> NodePolicy:
    return POLICIES.get(agent.name, DEFAULT_POLICY)


def error_type_of(result: AgentResult) -> Optional[str]:
    """The exception class name recorded on a failed result, if there is one."""
    if not result.error:
        return None
    m = _ERROR_TYPE_RE.match(result.error)
    return m.group(1) if m else None


def should_retry(result: AgentResult, tag: Optional[str], attempt: int, policy: NodePolicy) -> bool:
    """Whether to spend another attempt on this failure.

    A timeout is always transient by definition — the agent did not fail, it
    ran out of clock — but it is also the most expensive failure to repeat, so
    it is still bounded by `attempts` like everything else.

    Only ERROR is retried. A DEGRADED result is a *successful* answer from a
    fallback; retrying it would discard a usable answer in the hope of a better
    one, on a path where the fallback exists precisely because the primary is
    unavailable.
    """
    if attempt >= policy.attempts:
        return False
    if result.status is not AgentStatus.ERROR:
        return False
    if tag is not None and tag.endswith(":cancelled"):
        return False  # someone asked us to stop; trying again ignores them
    if tag is not None and tag.endswith(":timeout"):
        return True
    name = error_type_of(result)
    return name is not None and name in _TRANSIENT_NAMES
