"""
The agent registry — what the orchestrator builds its graph from.

    .venv/bin/python -m pytest services/api/tests/test_agent_registry.py -q

Two of the checks here look pedantic and are not. `test_duplicate_names_are_refused`
guards the fact that an agent's name is simultaneously a registry key, a trace
node label, a `degraded` tag fragment and a feature-vector prefix — two agents
sharing one would overwrite each other's results in four places at once, silently.
And `test_enumeration_order_does_not_depend_on_import_order` guards the
determinism requirement in 1.3: ablations that compare runs are only meaningful
if the runs are comparable.

The registry is module-global, so every test here starts from empty via the
`clean_registry` fixture. Without it the suite would pass or fail on file order.
"""

from __future__ import annotations

import asyncio
from typing import Iterator

import pytest

from schema.models import AgentResult, AgentStatus, InputType, InvestigationState, utc_now_iso
from services.api.agents import registry
from services.api.agents.base import AgentContext, run_agent
from services.api.agents.registry import RegistrationError


@pytest.fixture(autouse=True)
def clean_registry() -> Iterator[None]:
    """Empty before, empty after — module-global state needs both."""
    registry.clear()
    yield
    registry.clear()


def make_state(**kw: object) -> InvestigationState:
    return InvestigationState(
        case_id="AGIS-TEST-1",
        org_id="aegis",
        created_by="test@aegis.local",
        created_at=utc_now_iso(),
        **kw,  # type: ignore[arg-type]
    )


def make_ctx() -> AgentContext:
    return AgentContext(org_id="aegis", case_id="AGIS-TEST-1")


class _Base:
    """Shared body for the toys below. Not part of the agent contract —
    the protocol is structural, and nothing is required to inherit anything."""

    name = "override_me"
    version = "0.1.0"

    def can_handle(self, state: InvestigationState) -> bool:
        return True

    async def run(self, state: InvestigationState, ctx: AgentContext) -> AgentResult:
        return AgentResult(agent=self.name, version=self.version, status=AgentStatus.OK)


# --------------------------------------------------------------------------
# The happy path
# --------------------------------------------------------------------------


def test_a_toy_agent_registers_runs_and_returns_a_valid_result() -> None:
    """The first acceptance criterion for 1.2, end to end through the registry."""

    @registry.register
    class Toy(_Base):
        name = "toy"
        version = "0.1.0"

    assert registry.names() == ["toy"]
    assert registry.versions() == {"toy": "0.1.0"}

    agent = registry.get("toy")
    result, tag = asyncio.run(run_agent(agent, make_state(), make_ctx()))

    assert isinstance(result, AgentResult)
    assert result.status is AgentStatus.OK
    assert result.agent == "toy" and result.version == "0.1.0"
    assert tag is None


def test_register_returns_the_class_so_it_stays_usable() -> None:
    """A decorator that swallowed the class would break every type annotation
    referring to it, and the failure would look like an import error."""

    @registry.register
    class Toy(_Base):
        name = "toy"
        version = "0.1.0"

    assert Toy.name == "toy"
    assert isinstance(Toy(), _Base)


def test_the_registry_holds_one_instance_not_a_class() -> None:
    """Agents are stateless by contract, so one instance serves every
    investigation and the fan-out pays no construction cost."""

    @registry.register
    class Toy(_Base):
        name = "toy"
        version = "0.1.0"

    assert registry.get("toy") is registry.get("toy")
    assert isinstance(registry.get("toy"), Toy)


# --------------------------------------------------------------------------
# What it refuses, and why
# --------------------------------------------------------------------------


def test_duplicate_names_are_refused() -> None:
    """One name is four identifiers. Two agents sharing it lose data in all four."""

    @registry.register
    class First(_Base):
        name = "collide"
        version = "0.1.0"

    with pytest.raises(RegistrationError, match="duplicate agent name"):

        @registry.register
        class Second(_Base):
            name = "collide"
            version = "9.9.9"

    # The first registration survives; a bad second must not clobber a good first.
    assert registry.get("collide").version == "0.1.0"


@pytest.mark.parametrize("version", [None, "", "latest", "v1", 1.0, "1"])
def test_unversioned_agents_are_refused(version: object) -> None:
    """A result without a pinned version cannot be reproduced, which makes every
    Phase 9 number that depends on it unverifiable."""
    # Built with `type()` rather than a decorated class body: the decorator runs
    # at definition time, so a `Bad.version = ...` line after the class would set
    # the attribute long after registration had already accepted the inherited one.
    with pytest.raises(RegistrationError, match="version"):
        registry.register(type("Bad", (_Base,), {"name": "unversioned", "version": version}))


@pytest.mark.parametrize("name", [None, "", "ab", "Bad Name", "url.agent", "URL_AGENT", "1st"])
def test_malformed_names_are_refused(name: object) -> None:
    with pytest.raises(RegistrationError, match="name must be snake_case"):
        registry.register(type("Bad", (_Base,), {"name": name, "version": "0.1.0"}))


def test_a_class_that_is_not_an_agent_is_refused() -> None:
    with pytest.raises(RegistrationError, match="does not satisfy Agent"):

        @registry.register
        class NotAnAgent:
            name = "not_an_agent"
            version = "0.1.0"


def test_registration_failure_leaves_the_registry_untouched() -> None:
    """A refused agent must not half-register. The orchestrator enumerates this
    list to build a graph; a partially-registered entry would build a node that
    cannot run."""

    @registry.register
    class Good(_Base):
        name = "good_one"
        version = "0.1.0"

    with pytest.raises(RegistrationError):

        @registry.register
        class Bad(_Base):
            name = "bad"
            version = "nope"

    assert registry.names() == ["good_one"]


# --------------------------------------------------------------------------
# Enumeration and routing
# --------------------------------------------------------------------------


def test_enumeration_order_does_not_depend_on_import_order() -> None:
    """Determinism starts here.

    1.3 requires that the same input plus fixed seeds gives the same output. A
    fan-out enumerated in import order would produce traces that cannot be
    diffed between runs, which makes the ablation study in 9.3 measure noise.
    """

    @registry.register
    class Zulu(_Base):
        name = "zulu"
        version = "0.1.0"

    @registry.register
    class Alpha(_Base):
        name = "alpha"
        version = "0.1.0"

    @registry.register
    class Mike(_Base):
        name = "mike"
        version = "0.1.0"

    assert [a.name for a in registry.all_agents()] == ["alpha", "mike", "zulu"]
    assert registry.names() == ["alpha", "mike", "zulu"]


def test_eligible_filters_on_can_handle() -> None:
    @registry.register
    class TextOnly(_Base):
        name = "text_only"
        version = "0.1.0"
        can_handle = registry.handles_input(InputType.TEXT)  # type: ignore[assignment]

    @registry.register
    class ApkOnly(_Base):
        name = "apk_only"
        version = "0.1.0"
        can_handle = registry.handles_input(InputType.APK)  # type: ignore[assignment]

    text_state = make_state(input_types=[InputType.TEXT])
    assert [a.name for a in registry.eligible(text_state)] == ["text_only"]

    apk_state = make_state(input_types=[InputType.APK, InputType.TEXT])
    assert [a.name for a in registry.eligible(apk_state)] == ["apk_only", "text_only"]


def test_eligible_honours_exclude_for_ablations() -> None:
    """"Run everything except the knowledge graph" has to be a parameter.

    If it is a code change, every ablation in 9.3 is a branch someone has to
    remember to revert, and one forgotten revert silently contaminates a
    published result.
    """

    @registry.register
    class A(_Base):
        name = "agent_a"
        version = "0.1.0"

    @registry.register
    class B(_Base):
        name = "agent_b"
        version = "0.1.0"

    state = make_state()
    assert [a.name for a in registry.eligible(state)] == ["agent_a", "agent_b"]
    assert [a.name for a in registry.eligible(state, exclude=["agent_a"])] == ["agent_b"]


def test_handles_input_matches_any_of_several_types() -> None:
    check = registry.handles_input(InputType.IMAGE, InputType.SCREENSHOT)
    assert check(make_state(input_types=[InputType.SCREENSHOT]))
    assert check(make_state(input_types=[InputType.IMAGE, InputType.TEXT]))
    assert not check(make_state(input_types=[InputType.AUDIO]))
    assert not check(make_state(input_types=[]))


def test_get_raises_on_an_unknown_name() -> None:
    with pytest.raises(KeyError):
        registry.get("no_such_agent")


def test_an_empty_registry_is_a_valid_state() -> None:
    """A clean clone with no agents imported still enumerates, rather than
    exploding — the same reason the API boots with no compose stack."""
    assert registry.all_agents() == []
    assert registry.versions() == {}
    assert registry.eligible(make_state()) == []


# --------------------------------------------------------------------------
# Warm-up — an optional hook, motivated by a measurement
# --------------------------------------------------------------------------


def test_warm_all_calls_warmup_where_it_exists_and_skips_where_it_does_not() -> None:
    """The hook is optional so 1.7's adapters can stay four lines long."""
    loaded: list[str] = []

    @registry.register
    class Heavy(_Base):
        name = "heavy_model"
        version = "0.1.0"

        async def warmup(self) -> None:
            loaded.append("heavy_model")

    @registry.register
    class Light(_Base):
        name = "just_regexes"
        version = "0.1.0"

    report = asyncio.run(registry.warm_all())

    assert loaded == ["heavy_model"]
    assert report["just_regexes"] == "no warmup"
    assert report["heavy_model"].startswith("warmed in ")


def test_a_failing_warmup_does_not_block_startup() -> None:
    """The degradation invariant, at boot.

    An agent that could not preload may still work — slowly, or from a
    fallback. Refusing to start over it turns a degradation into an outage, and
    the API's whole design is that it boots and answers with nothing available.
    """

    @registry.register
    class Broken(_Base):
        name = "broken_warmup"
        version = "0.1.0"

        async def warmup(self) -> None:
            raise OSError("checkpoint not found")

    @registry.register
    class Fine(_Base):
        name = "fine_agent"
        version = "0.1.0"

        async def warmup(self) -> None:
            return None

    report = asyncio.run(registry.warm_all())

    assert report["broken_warmup"].startswith("failed: OSError")
    assert report["fine_agent"].startswith("warmed in ")
    # Still registered, still runnable — a warm-up failure is not a deregistration.
    assert "broken_warmup" in registry.names()
    result, _ = asyncio.run(run_agent(registry.get("broken_warmup"), make_state(), make_ctx()))
    assert result.status is AgentStatus.OK


def test_a_hanging_warmup_is_bounded() -> None:
    """A model that never finishes loading must not hold the process at boot."""

    @registry.register
    class Hanger(_Base):
        name = "slow_loader"
        version = "0.1.0"

        async def warmup(self) -> None:
            await asyncio.sleep(30)

    report = asyncio.run(registry.warm_all(timeout_s=0.1))
    assert report["slow_loader"].startswith("timeout after")
