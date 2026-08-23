"""
OCR — reading the text out of a screenshot (Module 1 image inputs: fake police
notices, payment screenshots, QR codes).

The engine is pluggable and every backend is optional, on purpose. The rest of
the product runs on a clean clone with no network and no heavy wheels; OCR must
not break that promise. So this follows the same discipline as the classifier
and the PDF renderer:

  * `AEGIS_OCR` picks the backend — `tesseract` (default), `easyocr`, or `none`.
  * Each backend imports its dependency lazily and *probes* it (Tesseract also
    needs its system binary, which a `pip install` does not provide), falling
    back to `NullOcr` if anything is missing.
  * When no engine is available the caller gets `degraded: ["ocr:unavailable"]`
    and a message telling them to type the text — never a confident verdict on
    an empty string, which is the failure this whole product is careful about.

Extracted text is not scored here. It is handed to the same `analyze_text`
pipeline as a pasted message, so a screenshot and a paste reach one verdict.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..config import settings


@dataclass
class OcrResult:
    text: str
    engine: str                 # tesseract | easyocr | none
    degraded: list[str] = field(default_factory=list)
    #: Decoded QR / barcode payloads found in the image, if a decoder is present.
    qr_payloads: list[str] = field(default_factory=list)


class OcrEngine:
    name = "abstract"

    def extract(self, image_bytes: bytes) -> str:
        raise NotImplementedError


class NullOcr(OcrEngine):
    """No OCR available. Answers honestly rather than pretending."""

    name = "none"

    def extract(self, image_bytes: bytes) -> str:
        return ""


class TesseractOcr(OcrEngine):
    """pytesseract + Pillow. Light and offline, but needs the `tesseract`
    system binary — which `pip install pytesseract` does *not* install, so the
    constructor probes for it and raises if it is missing."""

    name = "tesseract"

    def __init__(self) -> None:
        import pytesseract  # noqa: F401
        from PIL import Image  # noqa: F401

        self._pt = pytesseract
        self._Image = Image
        # Probe the binary. Raises pytesseract.TesseractNotFoundError if the
        # wheel is installed but the engine is not, which we treat as "no OCR".
        self._pt.get_tesseract_version()

    def extract(self, image_bytes: bytes) -> str:
        import io

        img = self._Image.open(io.BytesIO(image_bytes))
        return self._pt.image_to_string(img)


class EasyOcr(OcrEngine):
    """easyocr — stronger on stylised / multilingual text (the module names it),
    but heavy: it pulls torch and downloads models on first run. Opt-in via
    AEGIS_OCR=easyocr."""

    name = "easyocr"

    def __init__(self) -> None:
        import easyocr  # noqa: F401

        # English + Hindi covers the digital-arrest corpus. Constructed once and
        # cached by load_ocr; the first construction is slow (model download).
        self._reader = easyocr.Reader(["en", "hi"], gpu=False)

    def extract(self, image_bytes: bytes) -> str:
        import numpy as np  # noqa: F401
        from PIL import Image

        import io

        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        lines = self._reader.readtext(np.array(img), detail=0)
        return "\n".join(lines)


_BACKENDS = {
    "tesseract": TesseractOcr,
    "easyocr": EasyOcr,
    "none": NullOcr,
}

_cached: OcrEngine | None = None
#: Why the active OCR backend was chosen — surfaced on /api/health.
selection_reason = "not yet loaded"


def load_ocr() -> OcrEngine:
    """Best available OCR engine for the configured backend. Cached."""
    global _cached, selection_reason
    if _cached is not None:
        return _cached

    # Via settings, not os.getenv: reading the environment directly here
    # bypassed the PRESAGE_* back-compat alias, so an un-migrated .env
    # silently fell back to tesseract instead of the configured backend.
    requested = settings.ocr_backend.strip().lower()
    if requested == "none":
        selection_reason = "disabled by AEGIS_OCR=none"
        _cached = NullOcr()
        return _cached

    cls = _BACKENDS.get(requested, TesseractOcr)
    try:
        _cached = cls()
        selection_reason = f"{cls.name} ready"
        return _cached
    except Exception as exc:  # noqa: BLE001 - any import/probe failure => degrade
        print(f"[aegis] OCR backend {requested!r} unavailable ({exc}); OCR disabled")
        selection_reason = f"{requested} unavailable: {exc}"
        _cached = NullOcr()
        return _cached


def _decode_qr(image_bytes: bytes) -> list[str]:
    """Best-effort QR/barcode decode. Optional — returns [] if no decoder is
    installed. A QR that resolves to a UPI deep link is exactly the payload the
    analyzer already knows how to score."""
    try:
        import io

        from PIL import Image
        from pyzbar.pyzbar import decode  # type: ignore
    except Exception:  # noqa: BLE001 - decoder absent
        return []
    try:
        img = Image.open(io.BytesIO(image_bytes))
        return [d.data.decode("utf-8", "replace") for d in decode(img)]
    except Exception:  # noqa: BLE001 - unreadable image
        return []


def extract_text(image_bytes: bytes) -> OcrResult:
    """Run the configured OCR engine over an image. Always returns a result;
    when nothing is available the `degraded` list says so."""
    engine = load_ocr()
    qr = _decode_qr(image_bytes)

    if isinstance(engine, NullOcr):
        return OcrResult(
            text="", engine="none",
            degraded=["ocr:unavailable"], qr_payloads=qr,
        )

    try:
        text = (engine.extract(image_bytes) or "").strip()
    except Exception as exc:  # noqa: BLE001 - runtime OCR failure
        return OcrResult(
            text="", engine=engine.name,
            degraded=[f"ocr:failed:{type(exc).__name__}"], qr_payloads=qr,
        )

    degraded: list[str] = []
    if not text:
        degraded.append("ocr:empty")
    return OcrResult(text=text, engine=engine.name, degraded=degraded, qr_payloads=qr)


import re

#: Text that appears on a genuine payment-app confirmation screen. Used to tell
#: "the victim sent us proof they already paid" apart from "the scammer sent a
#: fake notice" — the two need opposite responses, and the difference is
#: entirely in which side the screenshot came from.
_PAYMENT_MARKERS = re.compile(
    r"\b(paid to|sent to|transaction successful|txn id|utr|upi ref|debited)\b", re.I
)

def looks_like_payment_confirmation(text: str) -> bool:
    return bool(_PAYMENT_MARKERS.search(text))

def status() -> dict:
    engine = load_ocr()
    return {"backend": engine.name, "available": not isinstance(engine, NullOcr)}

