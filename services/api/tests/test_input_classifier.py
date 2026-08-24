"""Measured contract tests for the input-classification agent.

The 200-case corpus is intentionally bytes-first rather than a list of MIME
labels: the cases include real container structures for APKs and DOCX-like
archives, plus renamed payloads that would be misrouted if a browser-provided
type or filename were trusted.  It is compactly generated from fixed fixtures
so every identifier is distinct while the corpus remains reviewable in one
file.
"""

from __future__ import annotations

import asyncio
import zipfile
from dataclasses import dataclass
from io import BytesIO
from typing import Iterator

import pytest

from schema.models import (
    AgentResult,
    AgentStatus,
    EvidenceItem,
    InputType,
    InvestigationState,
    utc_now_iso,
)
from services.api.agents import registry
from services.api.agents.base import AgentContext, Stage, run_agent
from services.api.agents.classify.agent import InputClassifierAgent, apply_to_state
from services.api.agents.classify.sniff import classify_bytes, classify_inline_text
from services.api.orchestration import graph as orch


@dataclass(frozen=True)
class InputCase:
    """One fixed classification fixture, including untrusted metadata."""

    id: str
    expected: tuple[InputType, ...]
    data: bytes
    filename: str | None = None
    declared_type: str | None = None
    adversarial: bool = False


def _zip(*members: tuple[str, bytes]) -> bytes:
    """A real central directory, without extracting or executing anything."""
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        for name, body in members:
            archive.writestr(name, body)
    return buf.getvalue()


APK_BYTES = _zip(("AndroidManifest.xml", b"binary manifest"), ("classes.dex", b"dex\n035\x00"))
GENERIC_ZIP_BYTES = _zip(("notes.txt", b"nothing executable"))
PNG_BYTES = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
JPEG_BYTES = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00"
PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n"
WAV_BYTES = b"RIFF\x24\x00\x00\x00WAVEfmt "
MP4_BYTES = b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00"
MKV_BYTES = b"\x1a\x45\xdf\xa3\x93B\x82\x88matroska"


def _normal_cases() -> list[InputCase]:
    """180 ordinary inputs: every supported class gets ten varied members."""
    cases: list[InputCase] = []
    for i in range(10):
        cases.extend(
            (
                InputCase(f"image-png-{i}", (InputType.IMAGE,), PNG_BYTES, f"receipt-{i}.png", "image/png"),
                InputCase(f"image-jpeg-{i}", (InputType.IMAGE,), JPEG_BYTES, f"photo-{i}.jpg", "image/jpeg"),
                InputCase(
                    f"screenshot-{i}",
                    (InputType.SCREENSHOT, InputType.IMAGE),
                    PNG_BYTES,
                    f"Screenshot {i}.png",
                    "image/png",
                ),
                InputCase(f"pdf-{i}", (InputType.PDF,), PDF_BYTES, f"notice-{i}.pdf", "application/pdf"),
                InputCase(
                    f"eml-headers-{i}",
                    (InputType.EMAIL,),
                    (
                        f"From: alerts{i}@bank.example\nTo: citizen@example.com\n"
                        f"Subject: Statement {i}\nDate: Mon, 01 Jan 2026 00:00:00 +0000\n\nHello"
                    ).encode(),
                    f"statement-{i}.eml",
                    "message/rfc822",
                ),
                InputCase(
                    f"eml-extension-{i}",
                    (InputType.EMAIL, InputType.TEXT),
                    f"Exported mail body {i}".encode(),
                    f"export-{i}.eml",
                    "message/rfc822",
                ),
                InputCase(
                    f"url-{i}",
                    (InputType.URL,),
                    f"https://account.example.test/verify/{i}".encode(),
                    None,
                    "text/plain",
                ),
                InputCase(f"apk-{i}", (InputType.APK,), APK_BYTES, f"utility-{i}.apk", "application/vnd.android.package-archive"),
                InputCase(f"audio-mp3-{i}", (InputType.AUDIO,), b"ID3\x04\x00\x00song" + bytes([i]), f"call-{i}.mp3", "audio/mpeg"),
                InputCase(f"audio-wav-{i}", (InputType.AUDIO,), WAV_BYTES, f"call-{i}.wav", "audio/wav"),
                InputCase(f"video-mp4-{i}", (InputType.VIDEO,), MP4_BYTES, f"recording-{i}.mp4", "video/mp4"),
                InputCase(f"video-mkv-{i}", (InputType.VIDEO,), MKV_BYTES, f"recording-{i}.mkv", "video/x-matroska"),
                InputCase(f"phone-{i}", (InputType.PHONE,), f"+91987654{i:04d}".encode(), None, "text/plain"),
                InputCase(f"upi-{i}", (InputType.UPI_ID,), f"merchant{i}@okaxis".encode(), None, "text/plain"),
                InputCase(
                    f"text-{i}",
                    (InputType.TEXT,),
                    f"Your bank statement {i} is ready in the official app.".encode(),
                    f"message-{i}.txt",
                    "text/plain",
                ),
                InputCase(
                    f"sms-entities-{i}",
                    (InputType.SMS, InputType.TEXT, InputType.URL, InputType.UPI_ID),
                    f"AX-SBIINB: View https://bank.example.test/{i}; pay verify{i}@okaxis".encode(),
                    None,
                    "text/plain",
                ),
                InputCase(
                    f"html-document-{i}",
                    (InputType.DOCUMENT,),
                    f"<!doctype html><html><body>Notice {i}</body></html>".encode(),
                    f"notice-{i}.html",
                    "text/html",
                ),
                InputCase(f"audio-ogg-{i}", (InputType.AUDIO,), b"OggS\x00\x02opus" + bytes([i]), f"voice-{i}.ogg", "audio/ogg"),
            )
        )
    return cases


def _adversarial_cases() -> list[InputCase]:
    """20 mismatches that prove claims and names never drive routing."""
    cases: list[InputCase] = []
    for i in range(4):
        cases.append(
            InputCase(
                f"adversarial-apk-as-jpg-{i}",
                (InputType.APK,),
                APK_BYTES,
                f"holiday-{i}.jpg",
                "image/jpeg",
                True,
            )
        )
        cases.append(
            InputCase(
                f"adversarial-html-as-pdf-{i}",
                (InputType.DOCUMENT,),
                f"<html><body>not a PDF {i}</body></html>".encode(),
                f"notice-{i}.pdf",
                "application/pdf",
                True,
            )
        )
    for i in range(3):
        cases.append(
            InputCase(f"adversarial-pdf-as-jpg-{i}", (InputType.PDF,), PDF_BYTES, f"scan-{i}.jpg", "image/jpeg", True)
        )
        cases.append(
            InputCase(f"adversarial-png-as-apk-{i}", (InputType.IMAGE,), PNG_BYTES, f"tool-{i}.apk", "application/vnd.android.package-archive", True)
        )
    for i in range(2):
        cases.append(
            InputCase(
                f"adversarial-eml-as-jpg-{i}",
                (InputType.EMAIL,),
                f"From: notices{i}@bank.example\nTo: user@example.com\nSubject: update\n\nHello".encode(),
                f"scan-{i}.jpg",
                "image/jpeg",
                True,
            )
        )
        cases.append(
            InputCase(
                f"adversarial-mime-only-apk-{i}",
                (InputType.TEXT,),
                f"This is an ordinary bank reminder {i}.".encode(),
                None,
                "application/vnd.android.package-archive",
                True,
            )
        )
    cases.extend(
        (
            InputCase(
                "adversarial-generic-zip-as-pdf",
                (InputType.UNKNOWN, InputType.TEXT),
                GENERIC_ZIP_BYTES,
                "letter.pdf",
                "application/pdf",
                True,
            ),
            InputCase(
                "adversarial-unrecognised-binary",
                (InputType.UNKNOWN, InputType.TEXT),
                b"\x00\xff\x01\xfe\x02",
                None,
                "image/jpeg",
                True,
            ),
        )
    )
    return cases


@pytest.fixture(scope="module")
def input_fixture() -> tuple[InputCase, ...]:
    """The task 1.4 corpus: 180 ordinary + 20 adversarial items."""
    cases = tuple([*_normal_cases(), *_adversarial_cases()])
    assert len(cases) == 200
    assert sum(case.adversarial for case in cases) == 20
    return cases


@pytest.fixture(autouse=True)
def registered_classifier() -> Iterator[None]:
    """Keep this module's graph checks independent of test collection order."""
    registry.clear()
    registry.register(InputClassifierAgent)
    yield
    registry.clear()


def _state(*items: EvidenceItem, input_types: list[InputType] | None = None) -> InvestigationState:
    return InvestigationState(
        case_id="AGIS-CLASSIFY-1",
        org_id="aegis",
        created_by="test@aegis.local",
        created_at=utc_now_iso(),
        inputs=list(items),
        input_types=input_types or [],
    )


def test_200_item_fixture_meets_the_measured_accuracy_bar(input_fixture: tuple[InputCase, ...]) -> None:
    """Task 1.4 acceptance criterion: ≥98%, reporting every miss."""
    misses = []
    for case in input_fixture:
        actual = classify_bytes(case.data, filename=case.filename, declared_type=case.declared_type)
        if actual.types != case.expected:
            misses.append(f"{case.id}: expected {case.expected}, got {actual.types} ({actual.reason})")

    accuracy = (len(input_fixture) - len(misses)) / len(input_fixture)
    assert accuracy >= 0.98, (
        f"input classification accuracy {accuracy:.1%}; required ≥98.0%.\n"
        + "\n".join(misses)
    )


def test_every_promised_input_type_is_covered(input_fixture: tuple[InputCase, ...]) -> None:
    covered = {kind for case in input_fixture for kind in case.expected}
    assert {
        InputType.IMAGE,
        InputType.SCREENSHOT,
        InputType.PDF,
        InputType.EMAIL,
        InputType.URL,
        InputType.APK,
        InputType.AUDIO,
        InputType.VIDEO,
        InputType.PHONE,
        InputType.UPI_ID,
        InputType.TEXT,
    }.issubset(covered)


def test_adversarial_mismatches_are_explicit_findings(input_fixture: tuple[InputCase, ...]) -> None:
    for case in input_fixture:
        if not case.adversarial or case.id == "adversarial-unrecognised-binary":
            continue
        detection = classify_bytes(case.data, filename=case.filename, declared_type=case.declared_type)
        assert detection.conflicts, f"{case.id} was classified correctly but its mismatch was hidden"


def test_ambiguous_text_preserves_all_routes() -> None:
    detection = classify_inline_text("AX-HDFCBK: pay scammer@okaxis at https://bank.example.test/verify")
    assert detection.types == (InputType.SMS, InputType.TEXT, InputType.URL, InputType.UPI_ID)


def test_unknown_input_explicitly_routes_to_the_text_agent() -> None:
    item = EvidenceItem(id="mystery", filename="payload.bin")
    state = _state(item)
    result = asyncio.run(
        InputClassifierAgent().run(state, AgentContext(org_id=state.org_id, case_id=state.case_id))
    )

    update = apply_to_state(state, result)
    routed = state.model_copy(update=update)
    assert result.status is AgentStatus.OK
    assert routed.inputs[0].kind is InputType.UNKNOWN
    assert routed.input_types == [InputType.TEXT, InputType.UNKNOWN]
    assert registry.handles_input(InputType.TEXT)(routed)


def test_an_unrecognised_zip_keeps_unknown_and_the_text_route() -> None:
    detection = classify_bytes(GENERIC_ZIP_BYTES, filename="letter.pdf", declared_type="application/pdf")
    assert detection.types == (InputType.UNKNOWN, InputType.TEXT)
    assert detection.conflicts


def test_classifier_is_registered_and_records_one_result_per_evidence_item() -> None:
    agent = registry.get("input_classifier")
    state = _state(
        EvidenceItem(id="url", text="https://bank.example.test"),
        EvidenceItem(id="upi", text="merchant@okaxis"),
    )
    result, tag = asyncio.run(
        run_agent(agent, state, AgentContext(org_id=state.org_id, case_id=state.case_id))
    )

    assert agent.version == "1.0.0"
    assert tag is None and result.status is AgentStatus.OK
    assert [finding.detail for finding in result.findings if finding.label == "detected_type"] == ["url", "upi"]


def test_graph_runs_classification_before_input_routed_agents() -> None:
    seen: list[list[InputType]] = []

    @registry.register
    class UrlOnly:
        name = "url_only_fixture"
        version = "1.0.0"
        stage = Stage.INVESTIGATE
        can_handle = registry.handles_input(InputType.URL)

        async def run(self, state: InvestigationState, _ctx: AgentContext) -> AgentResult:
            seen.append(list(state.input_types))
            return AgentResult(agent=self.name, version=self.version, status=AgentStatus.OK)

    state = _state(EvidenceItem(id="url", text="https://bank.example.test"))
    result = asyncio.run(orch.investigate(state))

    assert [entry.agent for entry in result.agent_results] == ["input_classifier", "url_only_fixture"]
    assert result.inputs[0].kind is InputType.URL
    assert result.input_types == [InputType.URL]
    assert seen == [[InputType.URL]]


def test_benign_pdf_does_not_generate_a_conflict_from_generic_upload_metadata() -> None:
    """False-positive discipline: octet-stream is an absence of a claim, not a lie."""
    detection = classify_bytes(PDF_BYTES, filename="bank-statement.pdf", declared_type="application/octet-stream")
    assert detection.types == (InputType.PDF,)
    assert detection.conflicts == ()
