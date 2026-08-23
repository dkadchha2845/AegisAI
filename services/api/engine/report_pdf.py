"""
Evidence package → PDF. The handoff artifact a field officer or bank teller
actually files.

reportlab is imported lazily and behind `pdf_available()`, exactly like torch in
classifier.py: the JSON evidence package is the source of truth and works with
no extra dependency, and a machine without reportlab returns a clear 503 rather
than a stack trace. The layout is deliberately plain — a legal-admissibility
document optimises for being unambiguous and copyable, not for looking clever.
"""

from __future__ import annotations

import io
from typing import Any, Dict


def pdf_available() -> bool:
    try:
        import reportlab  # noqa: F401
        return True
    except ImportError:
        return False


def render_pdf(package: Dict[str, Any]) -> bytes:
    """Render an evidence package dict to PDF bytes. Raises RuntimeError if
    reportlab is not installed — the caller turns that into a 503."""
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
    CRIT = colors.HexColor("#c0392b")
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
    crit = ParagraphStyle("crit", parent=body, textColor=CRIT, fontName="Helvetica-Bold")

    def esc(text: Any) -> str:
        s = "" if text is None else str(text)
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    story: list[Any] = []
    incident = package.get("incident", {})
    call = package.get("call", {})
    assess = package.get("assessment", {})

    story.append(Paragraph("AegisAI — Scam-Call Evidence Package", h1))
    story.append(Paragraph(
        f"Report {esc(package.get('report_id'))} &nbsp;·&nbsp; "
        f"generated {esc(package.get('generated_at'))}", sub))
    story.append(HRFlowable(width="100%", color=RULE, spaceBefore=6, spaceAfter=8))

    # Incident summary band.
    story.append(Paragraph(
        f"Incident: <b>{esc(incident.get('type'))}</b>", body))
    story.append(Paragraph(
        f"Peak threat <b>{esc(incident.get('peak_threat'))}/100</b> "
        f"({esc(incident.get('final_level'))}) at stage "
        f"{esc(str(incident.get('peak_stage', '')).replace('_', ' ').title())}.",
        crit if (incident.get("peak_threat") or 0) >= 70 else body))

    # Call facts table.
    story.append(Paragraph("Call", sec))
    call_rows = [
        ["Caller number", esc(call.get("caller_number") or "—")],
        ["Session ID", esc(call.get("session_id"))],
        ["Duration", f"{esc(call.get('duration_s'))} s"],
        ["Claimed identity", esc(assess.get("claimed_identity") or "none stated")],
        ["Identity trust", f"{esc(assess.get('identity_trust_pct'))}%"],
        ["Caller-number risk",
         f"{esc(assess.get('caller_number_risk'))}/100 "
         f"({esc(assess.get('caller_number_verdict'))})"],
    ]
    story.append(_kv_table(call_rows, Table, TableStyle, colors, RULE, INK, MUTED, mm))

    # Evidence.
    story.append(Paragraph("Evidence (failed checks)", sec))
    evidence = package.get("evidence", [])
    if evidence:
        ev_rows = [["#", "Category", "Finding", "Detail"]]
        for i, e in enumerate(evidence, 1):
            ev_rows.append([
                str(i), esc(e.get("category")),
                Paragraph(esc(e.get("finding")), small),
                Paragraph(esc(e.get("detail")), small),
            ])
        t = Table(ev_rows, colWidths=[8 * mm, 24 * mm, 40 * mm, 96 * mm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f3f6")),
            ("TEXTCOLOR", (0, 0), (-1, 0), INK),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(t)
    else:
        story.append(Paragraph("No failed checks recorded.", small))

    # Stage timeline.
    timeline = package.get("stage_timeline", [])
    if timeline:
        story.append(Paragraph("Manipulation timeline", sec))
        for step in timeline:
            story.append(Paragraph(
                f"<b>{esc(step.get('at_s'))}s</b> — "
                f"{esc(str(step.get('stage', '')).replace('_', ' ').title())}: "
                f"&ldquo;{esc(step.get('first_utterance'))}&rdquo;", small))

    # Transcript.
    story.append(Paragraph("Transcript (evidence)", sec))
    for turn in package.get("transcript", []):
        who = esc(turn.get("speaker"))
        story.append(Paragraph(
            f"<b>{who}</b> "
            f"<font color='#5b6673'>[{esc(turn.get('t_s'))}s]</font>: "
            f"{esc(turn.get('text'))}", small))

    # Reporting guidance + citations.
    story.append(Paragraph("Reporting guidance", sec))
    for line in package.get("reporting_guidance", []):
        story.append(Paragraph(f"• {esc(line)}", body))

    citations = package.get("citations", [])
    if citations:
        story.append(Paragraph("Sources cited", sec))
        story.append(Paragraph(", ".join(esc(c) for c in citations), small))

    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", color=RULE, spaceBefore=6, spaceAfter=6))
    story.append(Paragraph(esc(package.get("disclaimer")), small))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=16 * mm, rightMargin=16 * mm,
        topMargin=16 * mm, bottomMargin=16 * mm,
        title=f"AegisAI Evidence Package {package.get('report_id')}",
        author="AegisAI",
    )
    doc.build(story)
    return buf.getvalue()


def _kv_table(rows, Table, TableStyle, colors, RULE, INK, MUTED, mm):
    """A two-column key/value table with muted keys."""
    t = Table(rows, colWidths=[40 * mm, 128 * mm])
    t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), MUTED),
        ("TEXTCOLOR", (1, 0), (1, -1), INK),
        ("LINEBELOW", (0, 0), (-1, -1), 0.3, RULE),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return t
