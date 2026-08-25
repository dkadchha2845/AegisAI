"""
A finished investigation, as something a person reads.

**Why it exists.** `GET /api/investigations/{id}` returns an
`InvestigationState`: twenty-nine fields, an agent-results array and a trace,
which is the right answer for a client and the wrong one for a bank teller. The
report is the projection a human needs — what was submitted, what was found,
what the system will and will not claim, and what to do next — in JSON and as
the PDF that gets attached to a cybercrime complaint.

**What it consumes.** One `InvestigationState`, and nothing else. Every number
in the report is copied from a contract field; none is computed here. That is
the pure-renderer invariant applied one layer earlier than the UI: if the report
banded a risk score itself, the report and the live console could disagree about
a 69.6.

**What it outputs.** A JSON-serialisable dict, and PDF bytes.

**How it connects.** `routes/investigations.py` serves both forms;
`engine/report_pdf.pdf_available()` is reused as the "is reportlab installed"
predicate so there is one answer to that question in the service.

**How it is evaluated.** `test_investigations_api.py`: an unscored investigation
reports itself as unscored rather than as safe, every submitted artefact appears
with its hash, a degraded agent is visible in the agent table, and the PDF path
returns a 503 with instructions rather than a stack trace when reportlab is
absent.

**Limitations, stated.** `risk_score`, `evidence` and `recommendations` are
empty for every investigation this system currently produces, because the
judgement tier (tasks 4.6 and 4.7) has no agents in it. The report says so, in
those words, in the field a reader looks at first. That is the whole design
decision here and it is worth being explicit about: an unscored investigation
rendered as `0.0 / CALM` is a false negative wearing a number, and this file
would rather hand back a report that says "not scored" than one that reads as a
clearance. When 4.6 lands, the same fields fill in and this file does not change.

The disclaimer is not boilerplate
---------------------------------
`DISCLAIMER` is imported from `engine/report.py` rather than re-worded, because
the live-call package and the investigation package are two doors onto the same
product and a citizen who receives both should not be told two different things
about what they are holding.
"""

from __future__ import annotations

import io
from typing import Any, Dict, List

from schema.models import InvestigationState, utc_now_iso

from ..engine.report import DISCLAIMER, REPORTING_GUIDANCE

#: What the assessment block says while the judgement tier is empty. A sentence
#: rather than a flag, because it is shown to a person and "scored: false" on
#: its own reads as a bug rather than as a stage of the roadmap.
NOT_SCORED = (
    "This investigation has not been scored. The evidence below was collected "
    "and recorded, but the risk model and evidence-fusion agents are not yet "
    "part of this build, so no risk number is claimed. Absence of a score is "
    "not a finding of safety."
)


def _agent_rows(state: InvestigationState) -> List[Dict[str, Any]]:
    """One row per agent execution, in the order the graph merged them.

    `findings` is a count rather than the findings themselves — they are listed
    once, in full, further down. Repeating them per agent would double the size
    of the report to say the same thing twice.
    """
    return [
        {
            "agent": r.agent,
            "version": r.version,
            "status": r.status.value,
            "confidence": r.confidence,
            "latency_ms": r.latency_ms,
            "provenance": list(r.provenance),
            "findings": len(r.findings),
            "error": r.error,
        }
        for r in state.agent_results
    ]


def _findings(state: InvestigationState) -> List[Dict[str, Any]]:
    """Every agent finding, flattened and attributed.

    Flattened because a reader scans a list; attributed because a finding whose
    producer is not named cannot be checked, and an unfollowable citation is not
    a citation.
    """
    out: List[Dict[str, Any]] = []
    for result in state.agent_results:
        for finding in result.findings:
            out.append(
                {
                    "agent": result.agent,
                    "label": finding.label,
                    "value": finding.value,
                    "confidence": finding.confidence,
                    "source": finding.source,
                    "detail": finding.detail,
                }
            )
    return out


def _entities(state: InvestigationState) -> Dict[str, List[Any]]:
    """The identifier lists that are actually populated.

    Empty lists are dropped rather than rendered as sixteen empty rows: a report
    that lists every category the system *could* have found is mostly a list of
    things it did not find.
    """
    return {
        field: list(values)
        for field, values in state.entities.model_dump().items()
        if values
    }


def _inputs(state: InvestigationState) -> List[Dict[str, Any]]:
    """What was submitted, with the hash that proves it.

    `sha256` is on every row because this document may be attached to a
    complaint: "the screenshot referred to in this report" is only a meaningful
    phrase if the report says which bytes it means. `text` is truncated to a
    preview — the full inline payload is in the state, and a report is not a
    place to reprint a 200 000-character paste.
    """
    rows: List[Dict[str, Any]] = []
    for item in state.inputs:
        preview = (item.text or "").strip().replace("\n", " ")
        rows.append(
            {
                "id": item.id,
                "kind": item.kind.value,
                "filename": item.filename,
                "declared_type": item.declared_type,
                "media_type": item.media_type,
                "size_bytes": item.size_bytes,
                "sha256": item.sha256,
                "stored": item.uri is not None,
                "preview": (preview[:280] + "…") if len(preview) > 280 else (preview or None),
            }
        )
    return rows


def _trace_summary(state: InvestigationState) -> Dict[str, Any]:
    """Latency, honestly.

    `elapsed_ms` is the wall clock — the largest `t_end` — not the sum of the
    spans. With a concurrent fan-out the sum exceeds the elapsed time, and
    quoting it would overstate how long the citizen actually waited. Both are
    reported so the difference is visible rather than hidden.
    """
    if not state.trace:
        return {"spans": 0, "elapsed_ms": 0, "agent_ms": 0, "by_status": {}}
    by_status: Dict[str, int] = {}
    for span in state.trace:
        by_status[span.status.value] = by_status.get(span.status.value, 0) + 1
    return {
        "spans": len(state.trace),
        "elapsed_ms": int(max(s.t_end for s in state.trace) * 1000),
        "agent_ms": sum(s.latency_ms for s in state.trace),
        "by_status": dict(sorted(by_status.items())),
    }


def build_report(state: InvestigationState) -> Dict[str, Any]:
    """Project a finished investigation into the package a person reads."""
    scored = state.risk_score is not None
    return {
        "report_id": state.case_id,
        "generated_at": utc_now_iso(),
        "generator": "AegisAI — Agentic Multi-Modal Fraud Investigation",
        "disclaimer": DISCLAIMER,
        "case": {
            "case_id": state.case_id,
            "org_id": state.org_id,
            "created_by": state.created_by,
            "created_at": state.created_at,
            "completed_at": state.completed_at,
            "status": state.status.value,
            "mode": state.mode,
            "input_types": [t.value for t in state.input_types],
        },
        "assessment": {
            "scored": scored,
            "risk_score": state.risk_score,
            "risk_level": state.risk_level.value if state.risk_level else None,
            "confidence": state.confidence,
            "classification": state.classification.value if state.classification else None,
            "note": None if scored else NOT_SCORED,
        },
        "inputs": _inputs(state),
        "entities": _entities(state),
        "agents": _agent_rows(state),
        "findings": _findings(state),
        # Ranked, citizen-facing evidence and the actions it implies. Both are
        # produced by the judgement tier, so both are empty today; they are in
        # the shape rather than omitted, so a client written against this report
        # does not need changing when 4.6 and 4.7 fill them.
        "evidence": [e.model_dump(mode="json") for e in state.evidence],
        "recommendations": [r.model_dump(mode="json") for r in state.recommendations],
        "degraded": list(state.degraded),
        "trace": _trace_summary(state),
        "reporting_guidance": list(REPORTING_GUIDANCE),
    }


# --------------------------------------------------------------------------
# PDF
# --------------------------------------------------------------------------


def render_pdf(report: Dict[str, Any]) -> bytes:
    """Render a report dict to PDF bytes.

    Raises `RuntimeError` if reportlab is absent — the route turns that into a
    503 naming the JSON endpoint, exactly as the live-call PDF does. The layout
    is deliberately plain: a document that may be attached to a complaint
    optimises for being unambiguous and copyable.
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            HRFlowable,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError as exc:  # pragma: no cover - exercised via the route
        raise RuntimeError("reportlab is not installed") from exc

    INK = colors.HexColor("#101418")
    MUTED = colors.HexColor("#5b6673")
    WARN = colors.HexColor("#b06d0b")
    RULE = colors.HexColor("#d5dbe1")

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Title"], fontSize=18, textColor=INK,
                        spaceAfter=2, alignment=TA_LEFT)
    sub = ParagraphStyle("sub", parent=styles["Normal"], fontSize=9, textColor=MUTED,
                         spaceAfter=2)
    sec = ParagraphStyle("sec", parent=styles["Heading2"], fontSize=11.5,
                         textColor=INK, spaceBefore=12, spaceAfter=4)
    body = ParagraphStyle("body", parent=styles["Normal"], fontSize=9.5,
                          textColor=INK, leading=13)
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=8,
                           textColor=MUTED, leading=11)
    warn = ParagraphStyle("warn", parent=body, textColor=WARN)
    cellstyle = ParagraphStyle("cell", parent=styles["Normal"], fontSize=8,
                               textColor=INK, leading=10)

    def esc(value: Any) -> str:
        text = "" if value is None else str(value)
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def cell(value: Any) -> Any:
        """A table cell that wraps instead of running into the next column.

        reportlab lays a bare string out on one line and lets it overflow, so a
        finding like "extension .jpg claims IMAGE, bytes are APK" printed on top
        of the Source column beside it. A `Paragraph` wraps to the column width.
        Used for the free-text columns only; short fixed values stay strings,
        which keeps the table cheap to build.
        """
        return Paragraph(esc(value), cellstyle)

    def table(rows: List[List[Any]], widths: List[float]) -> Any:
        t = Table(rows, colWidths=widths, hAlign="LEFT")
        t.setStyle(
            TableStyle(
                [
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
                    ("TEXTCOLOR", (0, 1), (-1, -1), INK),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.5, RULE),
                    ("LINEBELOW", (0, 1), (-1, -2), 0.25, RULE),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        return t

    case = report.get("case", {})
    assessment = report.get("assessment", {})
    story: List[Any] = []

    story.append(Paragraph("AegisAI — Investigation Report", h1))
    story.append(
        Paragraph(
            f"Case {esc(report.get('report_id'))} &nbsp;·&nbsp; "
            f"generated {esc(report.get('generated_at'))}",
            sub,
        )
    )
    story.append(HRFlowable(width="100%", color=RULE, spaceBefore=6, spaceAfter=8))

    # --- assessment ---
    story.append(Paragraph("Assessment", sec))
    if assessment.get("scored"):
        story.append(
            Paragraph(
                f"<b>Risk {esc(assessment.get('risk_score'))}/100 — "
                f"{esc(assessment.get('risk_level'))}</b>"
                + (
                    f" &nbsp;·&nbsp; {esc(assessment.get('classification'))}"
                    if assessment.get("classification")
                    else ""
                ),
                body,
            )
        )
    else:
        story.append(Paragraph(esc(assessment.get("note") or NOT_SCORED), warn))

    story.append(
        table(
            [
                ["Field", "Value"],
                ["Status", esc(case.get("status"))],
                ["Submitted", esc(case.get("created_at"))],
                ["Completed", esc(case.get("completed_at")) or "—"],
                ["Submitted by", esc(case.get("created_by"))],
                ["Detected types", ", ".join(case.get("input_types") or []) or "—"],
            ],
            [35 * mm, 130 * mm],
        )
    )

    # --- evidence submitted ---
    story.append(Paragraph("Evidence submitted", sec))
    rows = [["#", "Type", "Name", "Bytes", "sha256"]]
    for item in report.get("inputs", []):
        rows.append(
            [
                esc(item.get("id")),
                esc(item.get("kind")),
                cell(item.get("filename") or "(pasted)"),
                esc(item.get("size_bytes")),
                esc((item.get("sha256") or "")[:32]),
            ]
        )
    story.append(table(rows, [16 * mm, 24 * mm, 46 * mm, 18 * mm, 61 * mm]))

    # --- findings ---
    findings = report.get("findings", [])
    story.append(Paragraph(f"Findings ({len(findings)})", sec))
    if findings:
        rows = [["Agent", "Label", "Value", "Source"]]
        for finding in findings[:60]:
            rows.append(
                [
                    esc(finding.get("agent")),
                    esc(finding.get("label")),
                    cell(str(finding.get("value") or "")[:200]),
                    cell(finding.get("source")),
                ]
            )
        story.append(table(rows, [34 * mm, 38 * mm, 56 * mm, 37 * mm]))
        if len(findings) > 60:
            story.append(
                Paragraph(f"… and {len(findings) - 60} more; see the JSON report.", small)
            )
    else:
        story.append(Paragraph("No agent reported a finding on this evidence.", body))

    # --- identifiers ---
    entities = report.get("entities", {})
    if entities:
        story.append(Paragraph("Identifiers found", sec))
        rows = [["Kind", "Values"]]
        for kind, values in sorted(entities.items()):
            rows.append([esc(kind), cell(", ".join(str(v) for v in values)[:400])])
        story.append(table(rows, [34 * mm, 131 * mm]))

    # --- agents ---
    story.append(Paragraph("Agents that ran", sec))
    rows = [["Agent", "Version", "Status", "Latency", "Sources"]]
    for agent in report.get("agents", []):
        rows.append(
            [
                esc(agent.get("agent")),
                esc(agent.get("version")),
                esc(agent.get("status")),
                f"{esc(agent.get('latency_ms'))} ms",
                cell(", ".join(agent.get("provenance") or [])),
            ]
        )
    story.append(table(rows, [38 * mm, 18 * mm, 20 * mm, 22 * mm, 67 * mm]))

    degraded = report.get("degraded", [])
    if degraded:
        story.append(Paragraph("Reduced capability during this investigation", sec))
        story.append(Paragraph(esc(", ".join(degraded)), warn))

    # --- what to do ---
    story.append(Paragraph("What to do next", sec))
    for line in report.get("reporting_guidance", []):
        story.append(Paragraph(f"• {esc(line)}", body))

    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", color=RULE, spaceBefore=4, spaceAfter=6))
    story.append(Paragraph(esc(report.get("disclaimer")), small))

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"AegisAI investigation {report.get('report_id')}",
    )
    doc.build(story)
    return buffer.getvalue()


__all__ = ["NOT_SCORED", "build_report", "render_pdf"]
