#!/usr/bin/env python3
"""
AegisAI — the investigation contract's round-trip fixture.

    python schema/mock_investigation.py            # regenerate both artifacts
    python schema/mock_investigation.py --print    # show the fixture

Builds one fully-populated `InvestigationState` — every field set, every
optional present, every list non-empty — and emits it twice:

    schema/mock-investigation.json               Pydantic -> JSON
    apps/web/src/mock/investigation.fixture.ts   JSON -> TypeScript

Why two, and why the TypeScript one matters
-------------------------------------------
`check_contract.py` compares enums between the two languages. That catches a
missing enum member; it cannot catch a missing *field*. Add `retrieved_at` to
`TIRecord` in Python, forget it in `types.ts`, and both files still pass every
check while the frontend silently renders `undefined`.

The `.ts` fixture closes that hole using the TypeScript compiler itself. It is
a literal object annotated `: InvestigationState`, so `npm run typecheck` —
gate three, which already runs on every task — fails in both directions:

    field in models.py but not types.ts  ->  "object literal may only specify
                                              known properties"
    field in types.ts but not models.py  ->  "property X is missing"

A JSON fixture cannot do this. `resolveJsonModule` widens every string to
`string`, so `"status": "ok"` would no longer check against the `AgentStatus`
union and the enums would go unverified. It has to be emitted as TypeScript.

Determinism
-----------
Every value here is fixed — no `now()`, no random ids. Regenerating on an
unchanged contract must produce byte-identical files, because `check_contract.py`
regenerates in memory and fails if the committed artifacts differ. That is what
turns "someone forgot to re-run the generator" from a silent drift into a gate
failure.

The content is deliberately a realistic case rather than filler: a phishing SMS
carrying a URL and a UPI ID, one agent that succeeded, one that fell back, one
that was skipped, and one that errored — so anyone reading the fixture sees what
each `AgentStatus` is actually for.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from models import (
    INVESTIGATION_CONTRACT_VERSION,
    AgentResult,
    AgentStatus,
    EntitySet,
    EvidenceFinding,
    EvidenceItem,
    ExtractedText,
    Finding,
    FraudCategory,
    GraphContext,
    GraphNeighbour,
    InputType,
    InvestigationState,
    InvestigationStatus,
    Recommendation,
    RecommendedAction,
    RetrievedChunk,
    Severity,
    Stage,
    ThreatLevel,
    TIRecord,
    TraceSpan,
    Transcript,
    Utterance,
    VictimState,
)

JSON_OUT = HERE / "mock-investigation.json"
TS_OUT = HERE.parent / "apps" / "web" / "src" / "mock" / "investigation.fixture.ts"

T0 = "2026-08-24T09:14:02Z"
T1 = "2026-08-24T09:14:11Z"


def build() -> InvestigationState:
    """One complete investigation, with every optional field populated.

    Every optional is set on purpose: an optional left `None` here is a field
    the TypeScript check never sees, which is exactly the field that will be
    wrong. The fixture's job is to touch all of them.
    """
    return InvestigationState(
        case_id="AGIS-2026-000117",
        org_id="aegis",
        created_by="analyst@aegis.local",
        created_at=T0,
        mode="batch",
        status=InvestigationStatus.COMPLETE,
        completed_at=T1,
        inputs=[
            EvidenceItem(
                id="ev-1",
                kind=InputType.SCREENSHOT,
                filename="sms-screenshot.png",
                declared_type="image/png",
                media_type="image/png",
                size_bytes=184_320,
                sha256="9f2c" + "0" * 60,
                uri="s3://aegis-evidence/aegis/AGIS-2026-000117/ev-1.png",
                text=None,
                received_at=T0,
            ),
            EvidenceItem(
                id="ev-2",
                kind=InputType.TEXT,
                filename=None,
                declared_type=None,
                media_type="text/plain",
                size_bytes=118,
                sha256="4b71" + "0" * 60,
                uri=None,
                text=(
                    "SBI KYC suspended. Update within 2 hours at "
                    "http://sbi-secure-login.xyz/verify or pay Rs 10 to "
                    "verify@ybl to reactivate."
                ),
                received_at=T0,
            ),
        ],
        input_types=[InputType.SCREENSHOT, InputType.IMAGE, InputType.TEXT, InputType.URL],
        extracted_text=[
            ExtractedText(
                source_ref="ev-1",
                text="SBI KYC suspended. Update within 2 hours at sbi-secure-login.xyz",
                language="en",
                confidence=0.83,
                extractor="ocr:tesseract",
            ),
            ExtractedText(
                source_ref="ev-2",
                text=(
                    "SBI KYC suspended. Update within 2 hours at "
                    "http://sbi-secure-login.xyz/verify or pay Rs 10 to "
                    "verify@ybl to reactivate."
                ),
                language="en",
                confidence=1.0,
                extractor="verbatim",
            ),
        ],
        entities=EntitySet(
            phones=["9876543210"],
            upi_ids=["verify@ybl"],
            emails=["kyc-support@sbi-secure-login.xyz"],
            wallets=["1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"],
            bank_accounts=["50100234567890"],
            domains=["sbi-secure-login.xyz"],
            urls=["http://sbi-secure-login.xyz/verify"],
            ips=["203.0.113.44"],
            apps=["com.fake.sbi.kyc"],
            orgs=["State Bank of India"],
            amounts=[10.0],
            authorities=["RBI"],
            banks=["SBI"],
            locations=["Mumbai"],
            scam_keywords=["kyc", "otp"],
        ),
        transcript=Transcript(
            final=[
                Utterance(
                    id="u-1",
                    speaker="CALLER",
                    text="Sir aapka KYC suspend ho gaya hai, abhi update karna hoga.",
                    t0=0.0,
                    t1=4.2,
                    stage=Stage.FEAR_INDUCTION,
                    confidence=0.91,
                    victim_state=VictimState.ANXIOUS,
                )
            ],
            partial="Aap link kholiye",
            partial_speaker="CALLER",
        ),
        agent_results=[
            # OK — the live path worked.
            AgentResult(
                agent="url_investigation",
                version="0.1.0",
                status=AgentStatus.OK,
                confidence=0.94,
                findings=[
                    Finding(
                        label="domain_age_days",
                        value="3",
                        confidence=1.0,
                        source="whois",
                        detail="Registered 2026-08-21 via a privacy proxy.",
                    ),
                    Finding(
                        label="login_form_present",
                        value="true",
                        confidence=0.88,
                        source="html_features",
                        detail="Password field posting to a third-party origin.",
                    ),
                ],
                features={"domain_age_days": 3.0, "has_login_form": 1.0},
                latency_ms=412,
                provenance=["whois", "dns", "http_fetch"],
                error=None,
            ),
            # DEGRADED — answered, but from a fallback, and says so.
            AgentResult(
                agent="threat_intel",
                version="0.1.0",
                status=AgentStatus.DEGRADED,
                confidence=0.40,
                findings=[
                    Finding(
                        label="feed_snapshot_used",
                        value="urlhaus",
                        confidence=1.0,
                        source="cache",
                        detail="Live feed unreachable; served a 6-hour-old snapshot.",
                    )
                ],
                features={"ti_hits": 1.0},
                latency_ms=3_004,
                provenance=["urlhaus:snapshot"],
                error=None,
            ),
            # SKIPPED — not applicable. Must never read as "clean".
            AgentResult(
                agent="apk_static",
                version="0.1.0",
                status=AgentStatus.SKIPPED,
                confidence=0.0,
                findings=[],
                features={},
                latency_ms=0,
                provenance=[],
                error=None,
            ),
            # ERROR — raised, was contained, and the investigation still finished.
            AgentResult(
                agent="image_forensics",
                version="0.1.0",
                status=AgentStatus.ERROR,
                confidence=0.0,
                findings=[],
                features={},
                latency_ms=87,
                provenance=[],
                error="PIL.UnidentifiedImageError: truncated PNG",
            ),
        ],
        threat_intel=[
            TIRecord(
                indicator="sbi-secure-login.xyz",
                indicator_type="domain",
                source="urlhaus",
                malicious=True,
                confidence=0.9,
                observed_at="2026-08-23T22:10:00Z",
                retrieved_at=T1,
                reference="https://urlhaus.abuse.ch/host/sbi-secure-login.xyz/",
                cached=True,
            ),
            # The three-valued case: the feed could not answer. Not a "clean".
            TIRecord(
                indicator="verify@ybl",
                indicator_type="upi",
                source="internal_reports",
                malicious=None,
                confidence=0.0,
                observed_at=None,
                retrieved_at=T1,
                reference=None,
                cached=False,
            ),
        ],
        graph_context=GraphContext(
            prior_observations=4,
            prior_case_ids=["AGIS-2026-000042", "AGIS-2026-000088"],
            neighbours=[
                GraphNeighbour(
                    key="upi:verify@ybl",
                    kind="upi",
                    value="verify@ybl",
                    relation="SHARED_UPI",
                    shared_cases=3,
                )
            ],
            cluster_id="cluster-17",
            cluster_risk=78.5,
            centrality=0.41,
            first_seen="2026-07-02T11:00:00Z",
            last_seen="2026-08-23T18:30:00Z",
            backend="networkx",
        ),
        rag_context=[
            RetrievedChunk(
                chunk_id="rbi-2024-kyc-7",
                text=(
                    "Banks never ask customers to complete KYC through links sent "
                    "by SMS or to make a payment to reactivate an account."
                ),
                source="RBI circular DBR.AML.BC.18/2024",
                citation="RBI DBR.AML.BC.18/2024 §4.2",
                score=0.81,
                retriever="hybrid",
            )
        ],
        risk_features={
            "domain_age_days": 3.0,
            "has_login_form": 1.0,
            "ti_hits": 1.0,
            "graph_prior_observations": 4.0,
        },
        risk_score=88.4,
        risk_level=ThreatLevel.HIGH,
        confidence=0.86,
        classification=FraudCategory.BANKING_IMPERSONATION,
        evidence=[
            EvidenceFinding(
                id="f-1",
                title="Domain registered three days ago",
                detail=(
                    "sbi-secure-login.xyz was registered on 2026-08-21 behind a "
                    "privacy proxy and hosts a login form."
                ),
                severity=Severity.HIGH,
                confidence=0.94,
                contribution=0.31,
                agent="url_investigation",
                sources=["whois", "http_fetch"],
            ),
            EvidenceFinding(
                id="f-2",
                title="UPI ID seen in three earlier cases",
                detail="verify@ybl appears in 3 prior investigations in this org.",
                severity=Severity.MEDIUM,
                confidence=0.77,
                contribution=0.18,
                agent="knowledge_graph",
                sources=["graph:cluster-17"],
            ),
        ],
        recommendations=[
            Recommendation(
                action=RecommendedAction.DO_NOT_OPEN_LINK,
                detail="Do not open sbi-secure-login.xyz. It is not an SBI domain.",
                urgency=Severity.CRITICAL,
                sources=["f-1"],
            ),
            Recommendation(
                action=RecommendedAction.VERIFY_VIA_OFFICIAL_CHANNEL,
                detail="Call the number printed on your debit card to check your KYC status.",
                urgency=Severity.HIGH,
                sources=["rbi-2024-kyc-7"],
            ),
        ],
        degraded=["ti:snapshot_fallback", "ocr:tesseract_fallback"],
        trace=[
            TraceSpan(
                span_id="sp-1",
                node="input_classifier",
                agent="input_classifier",
                version="0.1.0",
                t_start=0.0,
                t_end=0.03,
                latency_ms=31,
                status=AgentStatus.OK,
                attempt=1,
                depth=0,
                parent_span_id=None,
                error=None,
            ),
            TraceSpan(
                span_id="sp-2",
                node="url_investigation",
                agent="url_investigation",
                version="0.1.0",
                t_start=0.05,
                t_end=0.46,
                latency_ms=412,
                status=AgentStatus.OK,
                attempt=1,
                depth=1,
                parent_span_id="sp-1",
                error=None,
            ),
            TraceSpan(
                span_id="sp-3",
                node="threat_intel",
                agent="threat_intel",
                version="0.1.0",
                t_start=0.05,
                t_end=3.06,
                latency_ms=3_004,
                status=AgentStatus.DEGRADED,
                attempt=2,
                depth=1,
                parent_span_id="sp-1",
                error=None,
            ),
        ],
    )


# --------------------------------------------------------------------------
# Emitters
# --------------------------------------------------------------------------


def to_json(state: InvestigationState) -> str:
    return json.dumps(state.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"


def _ts_literal(value: object, indent: int) -> str:
    """Render JSON-shaped data as a TypeScript literal.

    Only the four JSON value kinds appear here, because the input is always
    `model_dump(mode="json")`. Anything else is a bug in the contract — a field
    that does not survive JSON serialisation cannot cross the wire either — so
    it raises rather than being coerced into something that looks fine.
    """
    pad = "  " * indent
    inner = "  " * (indent + 1)
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return json.dumps(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        if not value:
            return "[]"
        items = ",\n".join(inner + _ts_literal(v, indent + 1) for v in value)
        return "[\n" + items + ",\n" + pad + "]"
    if isinstance(value, dict):
        if not value:
            return "{}"
        items = ",\n".join(
            f"{inner}{json.dumps(k)}: {_ts_literal(v, indent + 1)}" for k, v in value.items()
        )
        return "{\n" + items + ",\n" + pad + "}"
    raise TypeError(f"not JSON-shaped: {type(value).__name__}")


def to_typescript(state: InvestigationState) -> str:
    body = _ts_literal(state.model_dump(mode="json"), 0)
    return f"""// GENERATED — do not edit. Source: schema/mock_investigation.py
// Regenerate: ./scripts/sync-contract.sh
//
// This file exists to be type-checked, not to be imported by the app.
//
// It is one `InvestigationState` serialised by Pydantic and annotated with the
// TypeScript type, so `npm run typecheck` proves the two halves of the contract
// describe the same object. A field added to schema/models.py and forgotten in
// schema/types.ts fails here as an excess property; a field in types.ts that
// the backend never emits fails here as a missing one. The enum check in
// schema/check_contract.py cannot see either case.
import type {{ InvestigationState }} from "../types/contract";

export const INVESTIGATION_FIXTURE: InvestigationState = {body};
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json-out", type=Path, default=JSON_OUT)
    ap.add_argument("--ts-out", type=Path, default=TS_OUT)
    ap.add_argument("--print", dest="show", action="store_true")
    args = ap.parse_args()

    state = build()

    args.json_out.write_text(to_json(state))
    args.ts_out.parent.mkdir(parents=True, exist_ok=True)
    args.ts_out.write_text(to_typescript(state))

    print(f"investigation contract v{INVESTIGATION_CONTRACT_VERSION}")
    print(f"  {args.json_out}")
    print(f"  {args.ts_out}")

    if args.show:
        print()
        print(to_json(state))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
