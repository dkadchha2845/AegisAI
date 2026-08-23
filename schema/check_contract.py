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
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from models import (
    Event,
    EventKind,
    GuardianState,
    PaymentState,
    Stage,
    StateFrame,
    ThreatLevel,
    Verdict,
    VictimState,
)

# Python enum -> the `as const` array name in types.ts
PAIRS = [
    (Stage, "STAGES"),
    (ThreatLevel, "THREAT_LEVELS"),
    (VictimState, "VICTIM_STATES"),
    (PaymentState, "PAYMENT_STATES"),
    (GuardianState, "GUARDIAN_STATES"),
    (Verdict, "VERDICTS"),
    (EventKind, "EVENT_KINDS"),
]


def ts_array(source: str, name: str) -> list[str]:
    m = re.search(rf"export const {name} = \[(.*?)\] as const;", source, re.S)
    if not m:
        raise SystemExit(f"types.ts: could not find `export const {name}`")
    return re.findall(r'"([^"]+)"', m.group(1))


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

    # Contract version must agree too.
    from models import CONTRACT_VERSION

    m = re.search(r"export const CONTRACT_VERSION = (\d+);", ts)
    if not m or int(m.group(1)) != CONTRACT_VERSION:
        failures.append(
            f"CONTRACT_VERSION: models.py={CONTRACT_VERSION}, "
            f"types.ts={m.group(1) if m else 'missing'}"
        )
    else:
        print(f"  ok  CONTRACT_VERSION == {CONTRACT_VERSION}")

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

    if failures:
        print("\nCONTRACT DRIFT:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    print("\ncontract consistent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
