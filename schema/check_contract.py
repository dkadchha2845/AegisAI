#!/usr/bin/env python3
"""
AegisAI — contract drift guard.

    python schema/check_contract.py

models.py and types.ts describe the same wire format in two languages. Nothing
enforces that at runtime: if someone adds a stage to the Python enum and forgets
the TypeScript one, the backend starts emitting a value the frontend silently
treats as unknown, and the bug surfaces as a blank panel during the demo.

This compares every enum in both files and exits non-zero on any mismatch. It
also validates the generated mock stream against the Pydantic models, so a
malformed fixture is caught here rather than in the browser.

What it deliberately does NOT check
-----------------------------------
Field-level agreement. Comparing enums catches a missing enum member; it cannot
catch a field added to `models.py` and forgotten in `types.ts`. That hole is
closed by `schema/mock_investigation.py`, which emits one `InvestigationState`
as an annotated TypeScript literal so `npm run typecheck` — gate three — fails
on any field-level drift in either direction. This script's job for that fixture
is narrower and complementary: prove the committed artifacts are not *stale*,
so the typecheck is checking the current contract rather than an old snapshot.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from models import (
    AgentStatus,
    Event,
    EventKind,
    FraudCategory,
    GuardianState,
    InputType,
    InvestigationState,
    InvestigationStatus,
    PaymentState,
    RecommendedAction,
    Severity,
    Stage,
    StateFrame,
    ThreatLevel,
    Verdict,
    VictimState,
)

# Python enum -> the `as const` array name in types.ts
PAIRS = [
    # --- live-call contract ---
    (Stage, "STAGES"),
    (ThreatLevel, "THREAT_LEVELS"),
    (VictimState, "VICTIM_STATES"),
    (PaymentState, "PAYMENT_STATES"),
    (GuardianState, "GUARDIAN_STATES"),
    (Verdict, "VERDICTS"),
    (EventKind, "EVENT_KINDS"),
    # --- investigation contract ---
    (InputType, "INPUT_TYPES"),
    (AgentStatus, "AGENT_STATUSES"),
    (InvestigationStatus, "INVESTIGATION_STATUSES"),
    (FraudCategory, "FRAUD_CATEGORIES"),
    (Severity, "SEVERITIES"),
    (RecommendedAction, "RECOMMENDED_ACTIONS"),
]


def ts_array(source: str, name: str) -> list[str]:
    m = re.search(rf"export const {name} = \[(.*?)\] as const;", source, re.S)
    if not m:
        raise SystemExit(f"types.ts: could not find `export const {name}`")
    return re.findall(r'"([^"]+)"', m.group(1))


def check_investigation_fixture() -> list[str]:
    """Validate the investigation fixture, and prove it is not stale.

    Two separate things, both cheap:

    1. `mock-investigation.json` still validates against `InvestigationState` —
       the JSON -> Pydantic direction, which the TypeScript check cannot cover.
    2. Regenerating from the current models produces exactly what is committed.

    (2) is the one that matters. `investigation.fixture.ts` is what makes
    `npm run typecheck` a field-level contract check, and a stale fixture would
    keep passing that gate while describing a contract nobody uses any more —
    the same failure mode as the stale `metrics.json` in task 0.5, which claimed
    macro-F1 0.269 for a model measuring 0.767. The generator is deterministic
    precisely so this comparison is possible.
    """
    import mock_investigation as mi

    failures: list[str] = []
    if not mi.JSON_OUT.exists():
        return [f"{mi.JSON_OUT.name} absent — run schema/mock_investigation.py"]

    raw = json.loads(mi.JSON_OUT.read_text())
    try:
        InvestigationState.model_validate(raw)
        print(f"  ok  {mi.JSON_OUT.name} validates against InvestigationState")
    except Exception as e:
        failures.append(f"{mi.JSON_OUT.name}: {str(e)[:200]}")
        return failures

    state = mi.build()
    for path, rendered in ((mi.JSON_OUT, mi.to_json(state)), (mi.TS_OUT, mi.to_typescript(state))):
        if not path.exists():
            failures.append(f"{path.name} absent — run ./scripts/sync-contract.sh")
        elif path.read_text() != rendered:
            failures.append(f"{path.name} is stale — run ./scripts/sync-contract.sh")
        else:
            print(f"  ok  {path.name} matches the current models")
    return failures


def main() -> int:
    ts = (HERE / "types.ts").read_text()
    failures: list[str] = []

    for enum_cls, ts_name in PAIRS:
        py_values = [m.value for m in enum_cls]
        ts_values = ts_array(ts, ts_name)
        if py_values != ts_values:
            only_py = [v for v in py_values if v not in ts_values]
            only_ts = [v for v in ts_values if v not in py_values]
            detail = []
            if only_py:
                detail.append(f"missing from types.ts: {only_py}")
            if only_ts:
                detail.append(f"missing from models.py: {only_ts}")
            if not detail:
                detail.append("same members, different order")
            failures.append(f"{enum_cls.__name__} / {ts_name}: {'; '.join(detail)}")
        else:
            print(f"  ok  {enum_cls.__name__:<14} == {ts_name} ({len(py_values)} members)")

    # Both contract versions must agree. They are separate numbers because the
    # live-call frame contract and the investigation contract evolve
    # independently — adding an investigation field must not invalidate a client
    # that only speaks frames.
    from models import CONTRACT_VERSION, INVESTIGATION_CONTRACT_VERSION

    for name, py_value in (
        ("CONTRACT_VERSION", CONTRACT_VERSION),
        ("INVESTIGATION_CONTRACT_VERSION", INVESTIGATION_CONTRACT_VERSION),
    ):
        m = re.search(rf"export const {name} = (\d+);", ts)
        if not m or int(m.group(1)) != py_value:
            failures.append(
                f"{name}: models.py={py_value}, "
                f"types.ts={m.group(1) if m else 'missing'}"
            )
        else:
            print(f"  ok  {name} == {py_value}")

    # Validate the fixture the frontend actually builds against.
    fixture = HERE / "mock-stream.json"
    if fixture.exists():
        messages = json.loads(fixture.read_text())
        states = events = 0
        for i, msg in enumerate(messages):
            try:
                if msg["type"] == "state":
                    StateFrame.model_validate(msg)
                    states += 1
                elif msg["type"] == "event":
                    Event.model_validate(msg)
                    events += 1
            except Exception as e:
                failures.append(f"mock-stream.json[{i}]: {str(e)[:140]}")
        print(f"  ok  mock-stream.json validates ({states} state, {events} event)")

        seqs = [m["seq"] for m in messages]
        if seqs != sorted(seqs) or len(set(seqs)) != len(seqs):
            failures.append("mock-stream.json: seq is not strictly increasing")
    else:
        print("  --  mock-stream.json absent (run mock_stream.py)")

    failures.extend(check_investigation_fixture())

    if failures:
        print("\nCONTRACT DRIFT:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    print("\ncontract consistent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
