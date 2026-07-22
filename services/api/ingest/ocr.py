"""
OCR adapter — screenshots, fake police notices, payment confirmations, QR codes.

    PaddleOCR  → preferred. Best on Devanagari and on the low-quality
                 re-compressed screenshots people actually forward.
    EasyOCR    → accepted fallback.
    null       → declines.

The declining behaviour is the same principle as the ASR layer and matters for
the same reason: returning "" from a failed OCR would let a fake arrest warrant
score as an empty, therefore harmless, message. The README already states "no
OCR — type the screenshot out instead" as a deliberate product decision, and
this module keeps that promise honest by refusing rather than guessing.

QR payloads are handled separately from text OCR. A UPI QR decodes to a
`upi://pay?...` string that `engine/upi.py` already analyses structurally, so
routing it through the text path would waste the strongest check the system has.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class OCRResult:
    ok: bool
    backend: str
    text: str = ""
    #: Decoded QR / barcode payloads found in the image, if any.
    qr_payloads: list[str] = field(default_factory=list)
    mean_confidence: float = 0.0
    reason: Optional[str] = None
    degraded: list[str] = field(default_factory=list)


class OCRBackend:
    name = "abstract"

    def available(self) -> bool:
        raise NotImplementedError

    def read(self, image: bytes) -> OCRResult:
        raise NotImplementedError


class PaddleOCRBackend(OCRBackend):
    name = "paddleocr"

    def __init__(self) -> None:
        self._ocr = None

    def available(self) -> bool:
        try:
            import paddleocr  # noqa: F401
            return True
        except ImportError:
            return False

    def read(self, image: bytes) -> OCRResult:
        import numpy as np  # type: ignore
        from paddleocr import PaddleOCR  # type: ignore
        from PIL import Image  # type: ignore

        if self._ocr is None:
            # `en` covers romanised Hinglish, which is what these screenshots
            # overwhelmingly contain. Devanagari notices exist but are rarer,
            # and loading both language models doubles startup for little gain.
            self._ocr = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
        img = np.array(Image.open(io.BytesIO(image)).convert("RGB"))
        raw = self._ocr.ocr(img, cls=True) or []
        lines, confidences = [], []
        for page in raw:
            for entry in page or []:
                if len(entry) >= 2 and isinstance(entry[1], (list, tuple)):
                    lines.append(str(entry[1][0]))
                    confidences.append(float(entry[1][1]))
        return OCRResult(
            ok=bool(lines),
            backend=self.name,
            text="\n".join(lines),
            mean_confidence=sum(confidences) / len(confidences) if confidences else 0.0,
        )


class EasyOCRBackend(OCRBackend):
    name = "easyocr"

    def __init__(self) -> None:
        self._reader = None

    def available(self) -> bool:
        try:
            import easyocr  # noqa: F401
            return True
        except ImportError:
            return False

    def read(self, image: bytes) -> OCRResult:
        import easyocr  # type: ignore

        if self._reader is None:
            self._reader = easyocr.Reader(["en"], gpu=False, verbose=False)
        results = self._reader.readtext(image)
        lines = [str(r[1]) for r in results]
        confidences = [float(r[2]) for r in results]
        return OCRResult(
            ok=bool(lines),
            backend=self.name,
            text="\n".join(lines),
            mean_confidence=sum(confidences) / len(confidences) if confidences else 0.0,
        )


class NullOCRBackend(OCRBackend):
    name = "none"

    def available(self) -> bool:
        return True

    def read(self, image: bytes) -> OCRResult:
        return OCRResult(
            ok=False,
            backend=self.name,
            reason=(
                "No OCR backend is installed, so this image cannot be read. Type "
                "out what the screenshot says and paste it as text — a confident "
                "verdict on an unread image would be worse than declining."
            ),
            degraded=["ocr:unavailable"],
        )


def decode_qr(image: bytes) -> list[str]:
    """Decode any QR codes present. Independent of the OCR backend because a
    UPI QR is a structured payload, not text to be read — it goes straight to
    `engine/upi.py`, which is the strongest single check in the system."""
    payloads: list[str] = []
    try:
        import numpy as np  # type: ignore
        from PIL import Image  # type: ignore

        img = np.array(Image.open(io.BytesIO(image)).convert("RGB"))
    except (ImportError, OSError, ValueError):
        return payloads

    try:  # pyzbar handles multiple codes per image; cv2 is the fallback
        from pyzbar.pyzbar import decode  # type: ignore

        for code in decode(img):
            try:
                payloads.append(code.data.decode("utf-8"))
            except UnicodeDecodeError:
                continue
        if payloads:
            return payloads
    except ImportError:
        pass

    try:
        import cv2  # type: ignore

        detector = cv2.QRCodeDetector()
        data, points, _ = detector.detectAndDecode(cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
        if data:
            payloads.append(data)
    except (ImportError, Exception):  # noqa: BLE001 - cv2 raises bare Exception
        pass
    return payloads


_cached: OCRBackend | None = None


def load_ocr() -> OCRBackend:
    global _cached
    if _cached is not None:
        return _cached
    for backend in (PaddleOCRBackend(), EasyOCRBackend()):
        if backend.available():
            _cached = backend
            return _cached
    _cached = NullOCRBackend()
    return _cached


#: Text that appears on a genuine payment-app confirmation screen. Used to tell
#: "the victim sent us proof they already paid" apart from "the scammer sent a
#: fake notice" — the two need opposite responses, and the difference is
#: entirely in which side the screenshot came from.
_PAYMENT_MARKERS = re.compile(
    r"\b(paid to|sent to|transaction successful|txn id|utr|upi ref|debited)\b", re.I
)


def read_image(image: bytes) -> OCRResult:
    backend = load_ocr()
    qr = decode_qr(image)
    if isinstance(backend, NullOCRBackend):
        result = backend.read(image)
        # Even with no OCR, a decoded QR is a complete, checkable artifact on
        # its own — so an image that contains one is still worth analysing.
        if qr:
            result.qr_payloads = qr
            result.ok = True
            result.reason = None
            result.degraded = ["ocr:qr_only"]
        return result
    try:
        result = backend.read(image)
    except Exception as exc:  # noqa: BLE001 - OCR libs raise broadly
        return OCRResult(
            ok=False,
            backend=backend.name,
            reason=f"Could not read this image ({type(exc).__name__}). Paste the text instead.",
            degraded=["ocr:failed"],
            qr_payloads=qr,
        )
    result.qr_payloads = qr
    return result


def looks_like_payment_confirmation(text: str) -> bool:
    return bool(_PAYMENT_MARKERS.search(text))


def status() -> dict:
    backend = load_ocr()
    return {"backend": backend.name, "available": not isinstance(backend, NullOCRBackend)}
