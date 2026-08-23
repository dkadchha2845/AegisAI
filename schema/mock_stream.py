#!/usr/bin/env python3
"""
AegisAI — mock event stream.

    python schema/mock_stream.py                 # write mock-stream.json
    python schema/mock_stream.py --print         # human-readable timeline

Replays a hand-written gold call as a fully-formed sequence of contract
messages, with realistic timings, a rising threat curve, a forecast that fires
before the stage it predicts, a guardian alert, and a held payment.

Why this exists
---------------
It removes the backend from the frontend's critical path entirely. The Live
Call screen, the threat meter, the forecast chip, the guardian view and the
circuit-breaker can all be built, animated and polished against this file
before a single model is served. When the real backend arrives it emits the
same shapes and the UI does not change.

It is also the demo's safety net. If live audio dies on stage, replaying this
stream drives the identical UI — the fallback path is not a different codebase.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from models import (  # noqa: E402
    CallInfo,
    CoachSuggestion,
    CoercionState,
    Event,
    EventKind,
    Forecast,
    GuardianInfo,
    GuardianState,
    ManipulationMap,
    NumberIntel,
    PassportCheck,
    PaymentInfo,
    PaymentState,
    Stage,
    StageState,
    StateFrame,
    ThreatDriver,
    ThreatState,
    Transcript,
    TrustPassport,
    Utterance,
    Verdict,
    VictimState,
    threat_level,
)

ROOT = Path(__file__).parent.parent
GOLD = ROOT / "ml" / "data" / "seed" / "exemplars.jsonl"
OUT = Path(__file__).parent / "mock-stream.json"

SECONDS_PER_TURN = 4.5

# Per-stage threat contribution, mirroring aegis/taxonomy.py.
STAGE_THREAT = {
    Stage.GREETING: 5,
    Stage.AUTHORITY_CLAIM: 45,
    Stage.FEAR_INDUCTION: 70,
    Stage.ISOLATION: 90,
    Stage.VERIFICATION_DEMAND: 80,
    Stage.PAYMENT_SETUP: 90,
    Stage.PAYMENT_EXECUTION: 100,
    Stage.BENIGN: 0,
}

# Which manipulation bar each stage pushes.
STAGE_TACTIC = {
    Stage.AUTHORITY_CLAIM: "authority",
    Stage.FEAR_INDUCTION: "fear",
    Stage.ISOLATION: "isolation",
    Stage.VERIFICATION_DEMAND: "urgency",
    Stage.PAYMENT_SETUP: "urgency",
    Stage.PAYMENT_EXECUTION: "compliance",
}

# Curated coach lines, keyed by the stage they answer. In the real system
# these are retrieved from the library, never generated.
COACH = {
    Stage.AUTHORITY_CLAIM: (
        "Ask for their name, badge number and station, then say you will call "
        "the station's public number back.",
        "Real officers accept a callback. Impersonators never do.",
        "warn",
    ),
    Stage.FEAR_INDUCTION: (
        "Say: \"I am going to hang up and call 1930 to verify this.\"",
        "No genuine agency loses anything if you verify first.",
        "warn",
    ),
    Stage.ISOLATION: (
        "Say: \"I don't discuss anything without my family present.\" Then put "
        "the phone down and go to another person in the house.",
        "Isolation is the step before every transfer. Breaking it ends most "
        "scams on its own.",
        "urgent",
    ),
    Stage.VERIFICATION_DEMAND: (
        "Do not read out any OTP, Aadhaar or account number. Say you will "
        "verify at the branch.",
        "No bank or agency asks for these on a call. Not once, not ever.",
        "urgent",
    ),
    Stage.PAYMENT_SETUP: (
        "Say: \"I need to speak to my bank first.\" Do not open any payment "
        "app while this call is connected.",
        "No investigation requires you to move your own money.",
        "urgent",
    ),
    Stage.PAYMENT_EXECUTION: (
        "Stop. Put the phone down now. Nothing you are being told is real.",
        "This is the moment money leaves. There is no legitimate version of "
        "this instruction.",
        "urgent",
    ),
}

PASSPORT_CHECKS = [
    (2, "Number format", Verdict.FAIL,
     "International VoIP prefix, not an Indian landline",
     "TRAI numbering plan"),
    (3, "Official registry", Verdict.FAIL,
     "No match in the published agency contact directory",
     "agency-directory.json"),
    (4, "Caller ID consistency", Verdict.FAIL,
     "Claimed agency does not operate from this circle",
     "agency-directory.json"),
    (5, "Procedure check", Verdict.FAIL,
     "No Indian agency conducts arrests over video call",
     "MHA advisory 2024/cyber/11"),
]

# Number Spoofing Intelligence. The gold call's caller ID is a US number
# (+1-838-…) wearing a CBI badge — the signature mismatch of a digital-arrest
# scam. Hand-built here to mirror what engine/spoofing.py produces for this
# number, so the recorded demo shows the panel populated rather than empty.
# The intl-routing FAIL is visible from turn 0 (the number alone gives it away);
# the authority mismatch lands once the caller claims to be CBI at turn 2.
NUMBER_INTEL_RISK = {"International routing": 40.0, "Caller-ID vs claimed authority": 45.0}
NUMBER_INTEL_CONTEXT = [
    PassportCheck(name="Number format", verdict=Verdict.PASS,
                  detail="parses to a well-formed number", source=None),
    PassportCheck(name="Reported number", verdict=Verdict.UNKNOWN,
                  detail="not in the local complaint sample (illustrative, not exhaustive)",
                  source=None),
    PassportCheck(name="VoIP / suspicious prefix", verdict=Verdict.UNKNOWN,
                  detail="no known VoIP/bulk prefix — this check is not exhaustive",
                  source=None),
    PassportCheck(name="Call frequency", verdict=Verdict.UNKNOWN,
                  detail="not enough call history to judge frequency", source=None),
]


def build_number_intel(turn_index: int) -> NumberIntel:
    fails = [
        PassportCheck(
            name="International routing", verdict=Verdict.FAIL,
            detail="originates outside India (+1) while claiming an Indian agency — "
                   "government bodies do not call from foreign numbers",
            source="scam-playbooks.md",
        )
    ]
    if turn_index >= 2:
        fails.append(PassportCheck(
            name="Caller-ID vs claimed authority", verdict=Verdict.FAIL,
            detail="claims an Indian agency but the number is foreign-routed",
            source="rbi-advisories.md",
        ))
    risk = min(100.0, sum(NUMBER_INTEL_RISK[c.name] for c in fails))
    return NumberIntel(
        number="+1-838-224-7719", risk=round(risk, 1),
        verdict=Verdict.FAIL, checks=fails + NUMBER_INTEL_CONTEXT,
    )


def load_gold_call(call_id: str) -> dict:
    for line in GOLD.read_text().splitlines():
        if line.strip():
            call = json.loads(line)
            if call["seed"]["call_id"] == call_id:
                return call
    raise SystemExit(f"gold call {call_id} not found in {GOLD}")


def build(call: dict, session_id: str = "demo-session") -> list[dict]:
    turns = call["turns"]
    stages = [Stage(t["stage"]) for t in turns]

    # Index of the first turn in each stage run — used to fire the forecast
    # before the stage it predicts actually arrives.
    first_of_stage: dict[Stage, int] = {}
    for i, s in enumerate(stages):
        first_of_stage.setdefault(s, i)

    messages: list[dict] = []
    finals: list[Utterance] = []
    coercion_hist: list[float] = []
    tactics = {"authority": 0.0, "fear": 0.0, "isolation": 0.0,
               "urgency": 0.0, "compliance": 0.0}
    trust = 97.0
    checks: list[PassportCheck] = []
    seq = 0
    guardian = GuardianInfo()
    payment = PaymentInfo()
    prev_stage: Stage | None = None
    prev_level = None
    forecast_fired: set[Stage] = set()
    stage_started_at = 0.0

    def emit(msg) -> None:
        nonlocal seq
        seq += 1
        msg.seq = seq
        messages.append(json.loads(msg.model_dump_json()))

    for i, turn in enumerate(turns):
        t = round(i * SECONDS_PER_TURN, 2)
        stage = stages[i]
        if stage != prev_stage:
            stage_started_at = t

        finals.append(
            Utterance(
                id=f"u{i}",
                speaker=turn["speaker"],
                text=turn["text"],
                t0=t,
                t1=round(t + SECONDS_PER_TURN - 0.4, 2),
                stage=stage,
                confidence=round(0.72 + 0.02 * min(i, 12), 3),
                victim_state=VictimState(turn["victim_state"])
                if turn["victim_state"] != "NA"
                else VictimState.UNKNOWN,
            )
        )

        # Coercion: climbs with victim distress, eases when they resist.
        vs = turn["victim_state"]
        target = {
            "CALM": 12, "CONFUSED": 32, "ANXIOUS": 58,
            "PANICKED": 82, "COMPLIANT": 74, "RESISTING": 40,
        }.get(vs, coercion_hist[-1] if coercion_hist else 10)
        current = coercion_hist[-1] if coercion_hist else 8.0
        coercion_val = round(current + (target - current) * 0.55, 1)
        coercion_hist.append(coercion_val)
        trend = (
            "rising" if len(coercion_hist) > 1 and coercion_val > coercion_hist[-2] + 1
            else "falling" if len(coercion_hist) > 1 and coercion_val < coercion_hist[-2] - 1
            else "flat"
        )

        if (tac := STAGE_TACTIC.get(stage)):
            tactics[tac] = round(min(1.0, tactics[tac] + 0.28), 3)

        # Threat: stage weight dominates, coercion modulates.
        base = STAGE_THREAT[stage]
        score = round(min(100.0, base * 0.8 + coercion_val * 0.25), 1)
        level = threat_level(score)

        drivers = [
            ThreatDriver(
                label=f"Stage: {stage.value.replace('_', ' ').title()}",
                contribution=round(base / 100 * 0.8, 2),
                detail=f"Classifier confidence {finals[-1].confidence:.0%}",
            ),
            ThreatDriver(
                label="Victim stress",
                contribution=round(coercion_val / 100 * 0.25, 2),
                detail=f"Coercion index {coercion_val:.0f}, {trend}",
            ),
        ]
        # Script-template similarity — the module's own "Script similarity 94%"
        # signal. Climbs as the caller works through the scripted arc.
        if stage not in (Stage.GREETING, Stage.BENIGN):
            sim = min(0.96, 0.62 + 0.03 * i)
            drivers.append(
                ThreatDriver(
                    label="Script match",
                    contribution=round(sim * 0.15, 2),
                    detail=f"{sim:.0%} similar to a known "
                           f"{stage.value.replace('_', ' ').lower()} script",
                )
            )

        # Trust Passport: evidence lands progressively, trust falls with it.
        for idx, name, verdict, detail, source in PASSPORT_CHECKS:
            if i == idx:
                checks.append(
                    PassportCheck(name=name, verdict=verdict, detail=detail, source=source)
                )
                trust = round(max(3.0, trust - 24.0), 1)

        # Forecast: fire one turn BEFORE the predicted stage begins. This is
        # the whole point — a forecast that arrives with the event is a label.
        forecast = None
        for nxt in (Stage.ISOLATION, Stage.VERIFICATION_DEMAND,
                    Stage.PAYMENT_SETUP, Stage.PAYMENT_EXECUTION):
            start = first_of_stage.get(nxt)
            if start is not None and i < start:
                turns_away = start - i
                pay_start = first_of_stage.get(Stage.PAYMENT_EXECUTION)
                forecast = Forecast(
                    next_stage=nxt,
                    probability=round(min(0.96, 0.62 + 0.07 * (6 - min(turns_away, 6))), 2),
                    eta_s=round(turns_away * SECONDS_PER_TURN, 1),
                    eta_to_payment_s=round((pay_start - i) * SECONDS_PER_TURN, 1)
                    if pay_start and i < pay_start else None,
                    last_prediction_correct=True if nxt in forecast_fired else None,
                )
                break

        # Persist for the whole stage. Clearing it on victim turns made the
        # card blink in and out, which reads as a glitch rather than advice.
        coach = None
        if (c := COACH.get(stage)):
            coach = CoachSuggestion(
                line=c[0], tactic=stage.value, why=c[1],
                urgency=c[2], sources=["coach-library-v1"],
            )

        # Guardian fires on entering ISOLATION — break the isolation, the wedge.
        if stage == Stage.ISOLATION and guardian.state == GuardianState.IDLE:
            guardian = GuardianInfo(
                state=GuardianState.ALERTING, name="Aditya (son)", alerted_at_s=t
            )

        # Payment attempt at the first PAYMENT_EXECUTION turn -> HELD.
        if stage == Stage.PAYMENT_EXECUTION and payment.state == PaymentState.NONE:
            payment = PaymentInfo(
                state=PaymentState.HELD,
                amount_inr=450000,
                payee="Sanjay Enterprises",
                held_reason="Transfer attempted during CRITICAL threat with an "
                            "active isolation pattern",
                held_at_s=t,
            )

        emit(StateFrame(
            session_id=session_id, seq=0, t=t,
            call=CallInfo(status="active", duration_s=t, caller_number="+1-838-224-7719"),
            transcript=Transcript(final=list(finals)),
            stage=StageState(
                current=stage,
                confidence=finals[-1].confidence,
                since_s=round(t - stage_started_at, 1),
                distribution={stage: finals[-1].confidence},
            ),
            coercion=CoercionState(
                index=coercion_val, trend=trend,
                history=coercion_hist[-24:],
                features={"pause_ratio": round(0.2 + coercion_val / 400, 3),
                          "speech_rate_wpm": round(150 - coercion_val * 0.35, 1),
                          "compliance_hits": float(sum(
                              1 for u in finals if u.victim_state == VictimState.COMPLIANT))},
            ),
            threat=ThreatState(score=score, level=level, drivers=drivers),
            manipulation_map=ManipulationMap(**tactics),
            forecast=forecast,
            trust_passport=TrustPassport(
                claimed_identity="CBI Mumbai Crime Branch",
                final_trust_pct=trust, checks=list(checks),
            ),
            number_intel=build_number_intel(i),
            coach=coach, guardian=guardian, payment=payment,
        ))

        # --- edges ---
        if stage != prev_stage:
            emit(Event(session_id=session_id, seq=0, t=t,
                       kind=EventKind.STAGE_CHANGED,
                       payload={"from": prev_stage.value if prev_stage else None,
                                "to": stage.value}))
            if forecast_fired and stage in forecast_fired:
                emit(Event(session_id=session_id, seq=0, t=t,
                           kind=EventKind.FORECAST_HIT,
                           payload={"stage": stage.value}))
        if forecast:
            forecast_fired.add(forecast.next_stage)

        if level != prev_level:
            emit(Event(session_id=session_id, seq=0, t=t,
                       kind=EventKind.THRESHOLD_CROSSED,
                       payload={"level": level.value, "score": score}))

        if guardian.state == GuardianState.ALERTING and guardian.alerted_at_s == t:
            emit(Event(session_id=session_id, seq=0, t=t,
                       kind=EventKind.GUARDIAN_ALERTED,
                       payload={"name": guardian.name}))

        # Only on entering the stage. Re-firing the same urgent coach line
        # every turn would re-trigger its entrance animation and read as a
        # stuck UI rather than an escalation.
        if coach and coach.urgency == "urgent" and stage != prev_stage:
            emit(Event(session_id=session_id, seq=0, t=t,
                       kind=EventKind.COACH_URGENT, payload={"line": coach.line}))

        if payment.state == PaymentState.HELD and payment.held_at_s == t:
            emit(Event(session_id=session_id, seq=0, t=t,
                       kind=EventKind.PAYMENT_ATTEMPTED,
                       payload={"amount_inr": payment.amount_inr}))
            emit(Event(session_id=session_id, seq=0, t=t,
                       kind=EventKind.PAYMENT_HELD,
                       payload={"amount_inr": payment.amount_inr,
                                "reason": payment.held_reason}))

        prev_stage, prev_level = stage, level

    emit(Event(session_id=session_id, seq=0,
               t=round(len(turns) * SECONDS_PER_TURN, 2),
               kind=EventKind.CALL_ENDED, payload={"outcome": "payment_blocked"}))
    return messages


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--call", default="gold_0001_digital_arrest")
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--print", dest="show", action="store_true")
    args = ap.parse_args()

    messages = build(load_gold_call(args.call))
    args.out.write_text(json.dumps(messages, indent=2, ensure_ascii=False))

    states = [m for m in messages if m["type"] == "state"]
    events = [m for m in messages if m["type"] == "event"]
    print(f"{len(messages)} messages ({len(states)} state, {len(events)} event) -> {args.out}")
    print(f"duration {states[-1]['t']:.0f}s")

    if args.show:
        print()
        for m in messages:
            if m["type"] == "state":
                th = m.get("threat") or {}
                fc = m.get("forecast")
                f = (f"  forecast {fc['next_stage']} {fc['probability']:.0%} "
                     f"in {fc['eta_s']:.0f}s") if fc else ""
                print(f"{m['t']:6.1f}s [{m['stage']['current']:<20}] "
                      f"threat {th.get('score', 0):5.1f} {th.get('level', ''):<9}"
                      f" trust {m['trust_passport']['final_trust_pct']:5.1f}%{f}")
            else:
                print(f"{m['t']:6.1f}s   >> {m['kind']} {json.dumps(m['payload'])[:70]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
