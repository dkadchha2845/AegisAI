"""
OCR regressions — mostly about the *absence* of OCR.

CI and a clean clone have neither the Tesseract binary nor easyocr, so the
behaviour that matters most is the graceful one: no engine must mean an honest
`ocr:unavailable`, never a confident verdict on an empty read. If an engine
*is* installed locally these still hold — they assert the fallback contract,
not a particular backend.
"""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient

from services.api import engine  # noqa: F401  (namespace)
from services.api.engine import ocr as ocr_mod
from services.api.main import app


@pytest.fixture(autouse=True)
def _reset_ocr_cache():
    ocr_mod._cached = None
    yield
    ocr_mod._cached = None


def _load(monkeypatch, backend: str) -> ocr_mod.OcrEngine:
    monkeypatch.setenv("PRESAGE_OCR", backend)
    ocr_mod._cached = None
    return ocr_mod.load_ocr()


def test_none_backend_is_null(monkeypatch):
    assert isinstance(_load(monkeypatch, "none"), ocr_mod.NullOcr)


def test_missing_backend_falls_back_to_null(monkeypatch):
    # tesseract with no system binary (CI) must degrade rather than raise.
    engine_obj = _load(monkeypatch, "tesseract")
    # Either the binary is present (local dev) or we fell back to Null.
    assert isinstance(engine_obj, (ocr_mod.TesseractOcr, ocr_mod.NullOcr))


def test_extract_text_never_raises_and_reports_degradation(monkeypatch):
    _load(monkeypatch, "none")
    res = ocr_mod.extract_text(b"not really an image")
    assert res.engine == "none"
    assert "ocr:unavailable" in res.degraded
    assert res.text == ""


def test_qr_decode_is_optional_and_safe():
    # No decoder, or an unreadable blob — must return a list, never raise.
    assert ocr_mod._decode_qr(b"\x00\x01\x02not-an-image") == []


def test_image_route_degrades_without_ocr(monkeypatch):
    monkeypatch.setenv("PRESAGE_OCR", "none")
    ocr_mod._cached = None
    client = TestClient(app)
    resp = client.post(
        "/api/analyze/image",
        files={"file": ("notice.png", b"fake-png-bytes", "image/png")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["verdict"] == "INSUFFICIENT"
    assert "ocr:unavailable" in body["degraded"]
    assert body["ocr"]["engine"] == "none"


def test_image_route_rejects_non_image():
    client = TestClient(app)
    resp = client.post(
        "/api/analyze/image",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 415
