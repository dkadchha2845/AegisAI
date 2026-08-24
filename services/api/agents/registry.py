"""
The agent registry — the list the orchestrator builds its graph from.

**Why it exists.** ARCHITECTURE.md §2 builds the investigation graph *from the
registry* rather than from a hand-written node list. That is what lets Phase 2
add the QR agent without editing the orchestrator, and what lets the Phase 9
ablations remove one agent and re-run everything by changing a filter instead of
a graph definition.

**What it consumes.** Agent classes, at import time, through `@register`.

**What it outputs.** A frozen, name-keyed view of every agent, plus the version
string of each — which is what makes a recorded investigation reproducible.

**How it connects.** `orchestration/graph.py` (1.3) enumerates it; nothing else
should. Agents never look each other up here — an agent that reaches for another
agent has broken the isolation rule in §2 and should be reading state instead.

**How it is evaluated.** `test_agent_registry.py`: duplicate names are refused,
an agent without a version is refused, an agent that does not satisfy the
protocol is refused, and registration order does not affect enumeration order.

**Limitations, stated.** Registration is import-time and global, which is the
right shape for a fixed set of agents in one process and the wrong shape for
per-tenant agent sets — if an org ever needs its own agent list, this becomes a
constructed object rather than a module global. Version pinning is recorded, not
enforced: nothing here stops an agent changing its behaviour without changing
its version. The promotion gate in 4.9 is where that becomes checkable.
"""

from __future__ import annotations

import asyncio
import re
import time
from typing import Dict, Iterable, List, Optional, Type, TypeVar

from schema.models import InputType, InvestigationState

from .base import Agent

#: snake_case, because the name is a registry key, a `degraded` tag fragment
#: (`agent:url_investigation:timeout`), a trace node label and a JSON field name
#: all at once. Allowing spaces or dots would make one of those four ambiguous.
_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{2,47}$")

#: Any dotted version; the point is that it exists and changes when behaviour
#: does. Enforcing full semver here would reject "0.1" for no defect-finding gain.
_VERSION_RE = re.compile(r"^\d+(\.\d+)+([-.][0-9A-Za-z.-]+)?$")

_REGISTRY: Dict[str, Agent] = {}

A = TypeVar("A", bound=Type[Agent])


class RegistrationError(ValueError):
    """Raised at import time, on purpose.

    A misregistered agent should stop the process at startup, not surface as a
    missing node halfway through an investigation. This is the one place in the
    agent layer that is allowed to be fatal, because it fires before any citizen
    is waiting on an answer.
    """


def register(cls: A) -> A:
    """Class decorator. Instantiates once and records the instance.

    Agents are stateless by contract — everything they need arrives in `state`
    and `ctx` — so one instance serves every investigation and there is no
    per-call construction cost on the fan-out path.

    An agent that needs a heavy model must load it in `warmup()`, not in
    `__init__` and **not** lazily on first `run()`. Both of the wrong answers
    were measured rather than guessed: loading in `__init__` pulls checkpoints
    into any process that merely imports the registry, and loading on first
    `run()` puts a 7.7 s checkpoint load inside an agent whose budget is 8 s —
    the first investigation after a restart either times out or spends its
    entire allowance on disk I/O. See `warm_all()`.
    """
    instance = cls()

    name = getattr(instance, "name", None)
    if not isinstance(name, str) or not _NAME_RE.match(name):
        raise RegistrationError(
            f"{cls.__name__}: name must be snake_case, 3-48 chars, got {name!r}"
        )

    version = getattr(instance, "version", None)
    if not isinstance(version, str) or not _VERSION_RE.match(version):
        raise RegistrationError(
            f"{cls.__name__}: version must be a dotted string like '0.1.0', got {version!r} — "
            "a result without a pinned version cannot be reproduced"
        )

    if not isinstance(instance, Agent):
        missing = [m for m in ("can_handle", "run") if not callable(getattr(instance, m, None))]
        raise RegistrationError(f"{cls.__name__}: does not satisfy Agent; missing {missing}")

    if name in _REGISTRY:
        existing = _REGISTRY[name]
        raise RegistrationError(
            f"duplicate agent name {name!r}: already registered by "
            f"{type(existing).__name__} v{existing.version}. Names key the trace, the "
            "degraded tags and the feature vector — two agents sharing one would "
            "silently overwrite each other's results"
        )

    _REGISTRY[name] = instance
    return cls


def get(name: str) -> Agent:
    """One agent by name. Raises `KeyError` — an unknown agent is a code bug."""
    return _REGISTRY[name]


def all_agents() -> List[Agent]:
    """Every registered agent, sorted by name.

    Sorted, not insertion-ordered, so enumeration does not depend on which
    module Python imported first. The determinism requirement in 1.3 — same
    input plus fixed seeds gives the same output — starts here: a fan-out whose
    order drifts with import order produces traces that cannot be diffed.
    """
    return [_REGISTRY[k] for k in sorted(_REGISTRY)]


def names() -> List[str]:
    return sorted(_REGISTRY)


def versions() -> Dict[str, str]:
    """`{agent: version}` — recorded on every investigation for reproducibility."""
    return {name: _REGISTRY[name].version for name in sorted(_REGISTRY)}


def eligible(
    state: InvestigationState, *, exclude: Optional[Iterable[str]] = None
) -> List[Agent]:
    """The agents that say they can handle this state.

    `exclude` exists for the Phase 9 ablation study, so "run everything except
    the knowledge graph" is a parameter rather than a code change. Without it,
    every ablation is a branch someone has to remember to revert.
    """
    skip = set(exclude or ())
    return [a for a in all_agents() if a.name not in skip and a.can_handle(state)]


def handles_input(*types: InputType) -> staticmethod:
    """A `can_handle` for the common case: this agent runs on these input types.

        class UrlAgent:
            can_handle = registry.handles_input(InputType.URL)

    Most agents are exactly this, and hand-writing the check invites the mistake
    of comparing against a user-supplied MIME type instead of the classifier's
    verdict — which task 1.4 exists to prevent.

    Wrapped in `staticmethod` for one specific reason: assigned into a class
    body, a bare closure becomes an instance method and is handed `self` as its
    first argument, so `agent.can_handle(state)` raises a TypeError about
    argument counts at fan-out time. `staticmethod` suppresses the binding, and
    since Python 3.10 the object is still directly callable, so the same value
    also works standalone in a test or a filter.
    """
    wanted = set(types)

    def check(state: InvestigationState) -> bool:
        return bool(wanted.intersection(state.input_types))

    return staticmethod(check)


async def warm_all(*, timeout_s: float = 120.0) -> Dict[str, str]:
    """Load what the agents need before any investigation asks for it.

    Optional hook, not part of the `Agent` protocol: an agent that needs it
    defines `async def warmup(self) -> None`, and one that does not is left
    alone. Keeping it off the protocol matters because most agents are a regex
    and a lookup, and 1.7's adapters should stay four lines long.

    Why it exists at all is a measurement. The inherited classifier costs
    **7.66 s on its first call and 22-34 ms after** — a 300x difference, all of
    it checkpoint loading. ARCHITECTURE.md §2 gives an agent 8 s. So an agent
    that loads lazily is, on the first investigation after every restart, an
    agent that times out or nearly does; and the citizen who happens to arrive
    first gets the degraded answer. `services/api/main.py` already warms the
    classifier in its lifespan handler for exactly this reason. This is the
    same discipline, generalised to the agent layer.

    A failing warm-up never blocks startup. It is reported per agent and the
    agent stays registered, because an agent that could not preload may still
    work — slowly, or from a fallback — and refusing to boot over it would turn
    a degradation into an outage. The returned map is intended for
    `/api/health`, so the shortfall is visible rather than merely logged.
    """
    report: Dict[str, str] = {}
    for agent in all_agents():
        warmup = getattr(agent, "warmup", None)
        if not callable(warmup):
            report[agent.name] = "no warmup"
            continue
        started = time.monotonic()
        try:
            await asyncio.wait_for(warmup(), timeout=timeout_s)
        except asyncio.TimeoutError:
            report[agent.name] = f"timeout after {timeout_s:.0f}s"
        except Exception as e:
            report[agent.name] = f"failed: {type(e).__name__}: {e}"
        else:
            report[agent.name] = f"warmed in {int((time.monotonic() - started) * 1000)} ms"
    return report


def clear() -> None:
    """Empty the registry. Tests only.

    Module-global state and test isolation do not mix; every test that registers
    an agent must be able to start from empty, or the suite passes or fails
    depending on file order.
    """
    _REGISTRY.clear()
