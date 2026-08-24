"""
What a piece of evidence *is* — decided from the bytes, not from what the
uploader claimed.

**Why it exists.** Every routing decision in the graph keys off `input_types`,
so this is the first thing that can be wrong and the last thing anyone checks.
It is also a security control: `CLAUDE.md` requires uploads to be validated "by
magic bytes, not extension", and the reason is concrete — an APK renamed
`.jpg` reaching an agent written to expect an image is how a malware sample
gets handled by code that never expected one.

**What it consumes.** Bytes, and — as *hints only* — a filename and the MIME
type the uploader declared.

**What it outputs.** A `Detection`: the types found (several, when the evidence
genuinely is several things), the media type actually detected, the reason it
was decided, and any conflict between what was claimed and what is true.

**How it connects.** `agent.py` wraps this as the registered
`input_classifier`; the graph's classify node applies the result to
`state.input_types`, which is what `can_handle()` reads.

**How it is evaluated.** `test_input_classifier.py` measures accuracy over a
200-item corpus built from real file structures, 20 of them adversarial. The
bar is ≥98%, and the test prints every miss.

**Limitations, stated.**

* `SCREENSHOT` is only claimed on strong evidence — a filename that says so, or
  an exact match to a known device resolution. A 4:3 photo and a 4:3 screenshot
  are not separable from pixels alone, and guessing would put a wrong label on
  the most common evidence type there is.
* `QR` is never emitted. Whether an image contains a QR code is decided by
  decoding it, which is task 2.5's agent; claiming it here would mean either
  decoding every image in the classifier or asserting something unverified.
* `SMS` is only claimed when an Indian alphanumeric sender header is present
  (`AX-SBIINB`, `VM-HDFCBK`). Every other short message is `TEXT`, because
  nothing in a pasted string distinguishes an SMS from a WhatsApp message, and
  a routing decision built on a guess is worse than one built on TEXT.
* Container formats are read, never executed or extracted. A ZIP's central
  directory is listed to tell an APK from a DOCX; no member is ever decompressed,
  which is also what keeps a zip bomb inert.

**Evidence is data.** Text is matched against patterns here and never
interpreted. A screenshot whose OCR says "ignore previous instructions" is a
string that fails to look like a URL, and nothing more.
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from io import BytesIO
from typing import Optional, Sequence, Tuple

from schema.models import InputType

#: Enough for every signature below, and for a decode probe. Bounded so a 4 MB
#: upload does not become a 4 MB regex target.
SNIFF_BYTES = 8192

#: Entries listed from a ZIP central directory. An APK declares itself in the
#: first handful of names; reading ten thousand to find out is a denial of
#: service with extra steps.
MAX_ZIP_ENTRIES = 512


@dataclass(frozen=True)
class Detection:
    """What the bytes say, and how confidently.

    `types` is ordered most-specific-first and may hold several members: a
    screenshot is an IMAGE *and* a SCREENSHOT, and an SMS containing a link is
    TEXT *and* URL. Ambiguity is expressed by returning more than one, never by
    picking a favourite — the acceptance criterion for 1.4, and the reason
    `input_types` is a list on the contract.

    `conflicts` is the security-relevant field. It records a declared type or an
    extension that the bytes contradict, which is itself a finding: a file
    claiming to be a JPEG while being an APK is not a mistake, it is a choice
    somebody made.
    """

    types: Tuple[InputType, ...]
    media_type: Optional[str] = None
    reason: str = "unknown"
    confidence: float = 0.0
    conflicts: Tuple[str, ...] = field(default_factory=tuple)

    @property
    def primary(self) -> InputType:
        return self.types[0] if self.types else InputType.UNKNOWN


# UNKNOWN is preserved as the item's honest primary type, while TEXT is the
# deliberate routing fallback.  A future TextAgent registers for TEXT, so an
# unrecognised binary never leaves the graph with no eligible safe handler.
UNKNOWN_WITH_TEXT = (InputType.UNKNOWN, InputType.TEXT)


# --------------------------------------------------------------------------
# Layer 1 — magic bytes
# --------------------------------------------------------------------------

#: (offset, signature, media type, type). Ordered longest-signature-first within
#: a family so a more specific match wins.
_MAGIC: Sequence[Tuple[int, bytes, str, InputType]] = (
    (0, b"\x89PNG\r\n\x1a\n", "image/png", InputType.IMAGE),
    (0, b"\xff\xd8\xff", "image/jpeg", InputType.IMAGE),
    (0, b"GIF87a", "image/gif", InputType.IMAGE),
    (0, b"GIF89a", "image/gif", InputType.IMAGE),
    (0, b"BM", "image/bmp", InputType.IMAGE),
    (0, b"II*\x00", "image/tiff", InputType.IMAGE),
    (0, b"MM\x00*", "image/tiff", InputType.IMAGE),
    (0, b"%PDF-", "application/pdf", InputType.PDF),
    (0, b"ID3", "audio/mpeg", InputType.AUDIO),
    (0, b"\xff\xfb", "audio/mpeg", InputType.AUDIO),
    (0, b"\xff\xf3", "audio/mpeg", InputType.AUDIO),
    (0, b"fLaC", "audio/flac", InputType.AUDIO),
    (0, b"\x1a\x45\xdf\xa3", "video/x-matroska", InputType.VIDEO),
    (0, b"\x00\x00\x01\xba", "video/mpeg", InputType.VIDEO),
    (0, b"\x30\x26\xb2\x75", "video/x-ms-wmv", InputType.VIDEO),
)


def _riff_kind(head: bytes) -> Optional[Tuple[str, InputType]]:
    """RIFF is a container: WAV, WEBP and AVI share the first four bytes."""
    if not head.startswith(b"RIFF") or len(head) < 12:
        return None
    form = head[8:12]
    if form == b"WAVE":
        return "audio/wav", InputType.AUDIO
    if form == b"WEBP":
        return "image/webp", InputType.IMAGE
    if form == b"AVI ":
        return "video/x-msvideo", InputType.VIDEO
    return None


def _iso_bmff_kind(head: bytes) -> Optional[Tuple[str, InputType]]:
    """MP4 and friends: `....ftyp<brand>` at offset 4.

    The brand matters. `M4A ` is audio in an identical container to video, and
    sending a music file to the video agent wastes a keyframe extraction to
    learn there are no frames.
    """
    if len(head) < 12 or head[4:8] != b"ftyp":
        return None
    brand = head[8:12]
    if brand in (b"M4A ", b"M4B "):
        return "audio/mp4", InputType.AUDIO
    return "video/mp4", InputType.VIDEO


def _ogg_kind(head: bytes) -> Optional[Tuple[str, InputType]]:
    if not head.startswith(b"OggS"):
        return None
    window = head[:SNIFF_BYTES]
    if b"theora" in window or b"\x80theora" in window:
        return "video/ogg", InputType.VIDEO
    return "audio/ogg", InputType.AUDIO


def _zip_kind(data: bytes) -> Tuple[str, InputType, str]:
    """Tell an APK from a DOCX from a plain archive, by listing names only.

    Nothing is decompressed. `namelist()` reads the central directory, so a zip
    bomb never inflates, and an APK is never a step away from being executed —
    which is the APK agent's hard rule in 2.8 and starts being true here.
    """
    try:
        with zipfile.ZipFile(BytesIO(data)) as zf:
            names = []
            for i, name in enumerate(zf.namelist()):
                if i >= MAX_ZIP_ENTRIES:
                    break
                names.append(name)
    except (zipfile.BadZipFile, OSError, ValueError):
        # A truncated upload of a real APK still looks like one from its first
        # bytes; saying "a ZIP we could not read" is more useful than UNKNOWN.
        return "application/zip", InputType.UNKNOWN, "magic:zip_unreadable"

    lowered = {n.lower() for n in names}
    if "androidmanifest.xml" in lowered or any(n.endswith(".dex") for n in lowered):
        return "application/vnd.android.package-archive", InputType.APK, "magic:zip+android"
    if "word/document.xml" in lowered or "[content_types].xml" in lowered:
        return (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            InputType.DOCUMENT,
            "magic:zip+ooxml",
        )
    # A generic ZIP is neither a document nor an APK.  Calling it a document
    # would route an arbitrary archive to a parser that assumes prose, while
    # UNKNOWN has an explicit safe route to the text agent.
    return "application/zip", InputType.UNKNOWN, "magic:zip"


def sniff_magic(data: bytes) -> Optional[Tuple[InputType, str, str]]:
    """`(type, media_type, reason)` from the leading bytes, or None."""
    head = data[:SNIFF_BYTES]
    if not head:
        return None

    riff = _riff_kind(head)
    if riff:
        return riff[1], riff[0], f"magic:{riff[0]}"

    iso = _iso_bmff_kind(head)
    if iso:
        return iso[1], iso[0], f"magic:{iso[0]}"

    ogg = _ogg_kind(head)
    if ogg:
        return ogg[1], ogg[0], f"magic:{ogg[0]}"

    if head.startswith(b"PK\x03\x04") or head.startswith(b"PK\x05\x06"):
        media, kind, reason = _zip_kind(data)
        return kind, media, reason

    for offset, sig, media, kind in _MAGIC:
        if head[offset : offset + len(sig)] == sig:
            return kind, media, f"magic:{media}"
    return None


# --------------------------------------------------------------------------
# Layer 2 — the filename, used only when the bytes did not decide
# --------------------------------------------------------------------------

_EXTENSIONS: dict[str, Tuple[InputType, str]] = {
    ".txt": (InputType.TEXT, "text/plain"),
    ".md": (InputType.TEXT, "text/markdown"),
    ".csv": (InputType.TEXT, "text/csv"),
    ".json": (InputType.TEXT, "application/json"),
    ".vtt": (InputType.TEXT, "text/vtt"),
    ".srt": (InputType.TEXT, "application/x-subrip"),
    ".log": (InputType.TEXT, "text/plain"),
    ".eml": (InputType.EMAIL, "message/rfc822"),
    ".msg": (InputType.EMAIL, "application/vnd.ms-outlook"),
    ".html": (InputType.DOCUMENT, "text/html"),
    ".htm": (InputType.DOCUMENT, "text/html"),
    ".pdf": (InputType.PDF, "application/pdf"),
    ".apk": (InputType.APK, "application/vnd.android.package-archive"),
    ".png": (InputType.IMAGE, "image/png"),
    ".jpg": (InputType.IMAGE, "image/jpeg"),
    ".jpeg": (InputType.IMAGE, "image/jpeg"),
    ".webp": (InputType.IMAGE, "image/webp"),
    ".gif": (InputType.IMAGE, "image/gif"),
    ".mp3": (InputType.AUDIO, "audio/mpeg"),
    ".wav": (InputType.AUDIO, "audio/wav"),
    ".m4a": (InputType.AUDIO, "audio/mp4"),
    ".ogg": (InputType.AUDIO, "audio/ogg"),
    ".mp4": (InputType.VIDEO, "video/mp4"),
    ".mov": (InputType.VIDEO, "video/quicktime"),
    ".mkv": (InputType.VIDEO, "video/x-matroska"),
    ".docx": (InputType.DOCUMENT, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
}


def extension_of(filename: Optional[str]) -> str:
    if not filename or "." not in filename:
        return ""
    return "." + filename.rsplit(".", 1)[-1].lower()


def sniff_extension(filename: Optional[str]) -> Optional[Tuple[InputType, str, str]]:
    ext = extension_of(filename)
    hit = _EXTENSIONS.get(ext)
    if not hit:
        return None
    return hit[0], hit[1], f"extension:{ext}"


def _is_generic_declared_type(declared_type: str) -> bool:
    """Whether a browser supplied no meaningful content-type assertion.

    ``application/octet-stream`` is the ordinary fallback for an upload whose
    client did not know its MIME type.  Treating it as a lie would manufacture
    a security finding for benign uploads, while a concrete mismatch such as
    ``image/jpeg`` for an APK remains evidence worth recording.
    """
    value = declared_type.split(";", 1)[0].strip().lower()
    return value in {"application/octet-stream", "binary/octet-stream"}


# --------------------------------------------------------------------------
# Layer 3 — the content, for anything textual
# --------------------------------------------------------------------------

_URL_RE = re.compile(r"\bhttps?://[^\s<>\"']{3,2048}", re.I)
_BARE_URL_RE = re.compile(r"^\s*(?:https?://)?(?:[a-z0-9-]+\.)+[a-z]{2,24}(?:/\S*)?\s*$", re.I)
_PHONE_ONLY_RE = re.compile(r"^\s*(?:\+|00)?(?:91[\-\s]?)?[6-9]\d{9}\s*$")
_UPI_ONLY_RE = re.compile(r"^\s*[a-zA-Z0-9._\-]{2,64}@[a-zA-Z][a-zA-Z0-9]{1,32}\s*$")
_UPI_IN_TEXT_RE = re.compile(r"\b[a-zA-Z0-9._\-]{2,64}@(?!gmail|yahoo|outlook|hotmail|icloud|proton)[a-zA-Z][a-zA-Z0-9]{1,32}\b")
_EMAIL_ADDR_RE = re.compile(r"^\s*[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\s*$")

#: RFC-5322 headers that only a real message carries. Two or more, at the start
#: of a line, is a mail file — one alone is a quotation of one.
_EML_HEADERS = ("from:", "to:", "subject:", "date:", "received:", "message-id:", "return-path:")

_HTML_RE = re.compile(rb"<!doctype\s+html|<html[\s>]|<head[\s>]|<body[\s>]", re.I)

#: Indian alphanumeric sender IDs: two letters, a hyphen, then the brand —
#: `AX-SBIINB`, `VM-HDFCBK`, `JD-AXISBK`. A pasted WhatsApp message never has
#: one, so this is the only honest way to tell an SMS from any other text.
_SMS_SENDER_RE = re.compile(r"\b[A-Z]{2}-[A-Z0-9]{4,10}\b")


def _decode(data: bytes) -> Optional[str]:
    """Text, if these bytes plausibly are text.

    A NUL byte in the first block means binary — no text format this system
    accepts contains one, and treating a truncated MP4 as a document would send
    it to an agent that will read gibberish and report findings about it.
    """
    head = data[:SNIFF_BYTES]
    if b"\x00" in head:
        return None
    for encoding in ("utf-8", "cp1252"):
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return None


def _looks_like_eml(text: str) -> bool:
    lines = text[:4096].splitlines()
    seen = {
        line.split(":", 1)[0].lower() + ":"
        for line in lines[:60]
        if ":" in line and not line.startswith((" ", "\t"))
    }
    return len(seen.intersection(_EML_HEADERS)) >= 2


def sniff_text(text: str) -> Tuple[Tuple[InputType, ...], str, str]:
    """`(types, media_type, reason)` for something already known to be text.

    Returns several types where the content genuinely is several things. An SMS
    carrying a phishing link is TEXT *and* URL, and both agents should see it —
    that is the whole reason routing takes a list.
    """
    stripped = text.strip()

    if not stripped:
        return (InputType.TEXT,), "text/plain", "content:empty"

    if _looks_like_eml(text):
        return (InputType.EMAIL,), "message/rfc822", "content:rfc822_headers"

    # A single identifier, alone on the line, is that identifier — not prose
    # that happens to contain one.
    if _PHONE_ONLY_RE.match(stripped):
        return (InputType.PHONE,), "text/plain", "content:bare_phone"
    if _EMAIL_ADDR_RE.match(stripped):
        return (InputType.EMAIL,), "text/plain", "content:bare_email_address"
    if _UPI_ONLY_RE.match(stripped):
        return (InputType.UPI_ID,), "text/plain", "content:bare_upi"
    if _BARE_URL_RE.match(stripped) and " " not in stripped:
        return (InputType.URL,), "text/plain", "content:bare_url"

    # Prose. TEXT first, plus whatever it carries.
    extra: list[InputType] = []
    reasons = ["content:text"]
    if _SMS_SENDER_RE.search(stripped):
        extra.append(InputType.SMS)
        reasons.append("sender_id")
    if _URL_RE.search(stripped):
        extra.append(InputType.URL)
        reasons.append("url")
    if _UPI_IN_TEXT_RE.search(stripped):
        extra.append(InputType.UPI_ID)
        reasons.append("upi")

    primary = InputType.SMS if InputType.SMS in extra else InputType.TEXT
    ordered = [primary] + [t for t in extra if t is not primary]
    if primary is InputType.SMS:
        ordered.insert(1, InputType.TEXT)
    return tuple(ordered), "text/plain", "+".join(reasons)


# --------------------------------------------------------------------------
# Screenshots
# --------------------------------------------------------------------------

_SCREENSHOT_NAME_RE = re.compile(r"screen\s*shot|screenshot|screen_?capture|\bscrn\b", re.I)

#: Exact device resolutions, both orientations. A camera photo is not exactly
#: 1170x2532; a screenshot from an iPhone 13 is. Exactness is what makes this a
#: signal rather than an aspect-ratio guess that would label half the photos in
#: a gallery as screenshots.
_SCREEN_SIZES = frozenset(
    {
        (1080, 1920), (1080, 2160), (1080, 2280), (1080, 2340), (1080, 2400),
        (1080, 2412), (1170, 2532), (1179, 2556), (1206, 2622), (1284, 2778),
        (1290, 2796), (1320, 2868), (828, 1792), (750, 1334), (640, 1136),
        (1440, 2560), (1440, 2880), (1440, 3040), (1440, 3120), (1440, 3200),
        (720, 1280), (1125, 2436), (1242, 2688), (1668, 2388), (1536, 2048),
        (1620, 2160), (2048, 2732), (1280, 800), (1366, 768), (1440, 900),
        (1512, 982), (1680, 1050), (1920, 1080), (2560, 1440), (2560, 1600),
        (2880, 1800), (3024, 1964), (3456, 2234), (3840, 2160),
    }
)


def _is_screenshot(data: bytes, filename: Optional[str]) -> Optional[str]:
    """Evidence that an image is a screen capture, or None.

    Deliberately conservative. Aspect ratio alone would flag a large share of
    ordinary photographs, and a wrong SCREENSHOT label routes evidence to
    layout-aware OCR that then reports its confusion as a finding.
    """
    if filename and _SCREENSHOT_NAME_RE.search(filename):
        return "filename"
    try:
        from PIL import Image

        with Image.open(BytesIO(data)) as im:
            size = im.size
    except Exception:
        # Pillow absent, or the image is truncated. Not a screenshot claim —
        # an unmade claim, which is the correct outcome of an unread header.
        return None
    if size in _SCREEN_SIZES or (size[1], size[0]) in _SCREEN_SIZES:
        return f"resolution:{size[0]}x{size[1]}"
    return None


# --------------------------------------------------------------------------
# The whole decision
# --------------------------------------------------------------------------


def classify_bytes(
    data: bytes,
    *,
    filename: Optional[str] = None,
    declared_type: Optional[str] = None,
) -> Detection:
    """Magic bytes first, extension second, content third. Never the declaration.

    `declared_type` is compared and recorded, never routed on. That ordering is
    the security control: an APK renamed `.jpg` and served as `image/jpeg` is
    classified APK, and the two lies are attached to the detection as conflicts
    for the report to show.
    """
    conflicts: list[str] = []
    ext = extension_of(filename)

    magic = sniff_magic(data)
    if magic:
        kind, media, reason = magic
        types: Tuple[InputType, ...] = (
            UNKNOWN_WITH_TEXT if kind is InputType.UNKNOWN else (kind,)
        )

        if kind is InputType.IMAGE:
            shot = _is_screenshot(data, filename)
            if shot:
                types = (InputType.SCREENSHOT, InputType.IMAGE)
                reason = f"{reason}+screenshot:{shot}"

        declared_ext = _EXTENSIONS.get(ext)
        if declared_ext and declared_ext[0] is not kind:
            detected = kind.value if kind is not InputType.UNKNOWN else media
            conflicts.append(f"extension {ext} claims {declared_ext[0].value}, bytes are {detected}")
        if (
            declared_type
            and media
            and not _is_generic_declared_type(declared_type)
            and declared_type.split(";", 1)[0].strip().lower() != media
        ):
            conflicts.append(f"declared {declared_type}, bytes are {media}")

        return Detection(
            types=types,
            media_type=media,
            reason=reason,
            confidence=0.99,
            conflicts=tuple(conflicts),
        )

    # No signature. The filename is the second signal, but it remains a hint:
    # textual content is the third and final check, able to expose an HTML file
    # renamed `.pdf` rather than blindly accepting the extension.
    by_ext = sniff_extension(filename)
    text = _decode(data)
    if text is not None:
        if _HTML_RE.search(data[:SNIFF_BYTES]):
            if ext and ext not in (".html", ".htm"):
                conflicts.append(f"extension {ext} claims a different type, content is HTML")
            if (
                declared_type
                and not _is_generic_declared_type(declared_type)
                and "html" not in declared_type.lower()
            ):
                conflicts.append(f"declared {declared_type}, content is HTML")
            return Detection(
                types=(InputType.DOCUMENT,),
                media_type="text/html",
                reason="content:html",
                confidence=0.9,
                conflicts=tuple(conflicts),
            )

        types, media, reason = sniff_text(text)
        if by_ext and by_ext[0] is InputType.EMAIL and InputType.EMAIL not in types:
            # `.eml` with no recognisable headers: trust the name enough to try
            # the email agent, which will degrade honestly if it is wrong.
            types = (InputType.EMAIL, *types)
            reason = f"{reason}+extension:{ext}"
        elif by_ext and by_ext[0] not in types:
            conflicts.append(
                f"extension {ext} claims {by_ext[0].value}, content is {types[0].value}"
            )
        if (
            declared_type
            and not _is_generic_declared_type(declared_type)
            and declared_type.split(";", 1)[0].strip().lower() != media
        ):
            conflicts.append(f"declared {declared_type}, content is {media}")
        return Detection(
            types=types,
            media_type=media,
            reason=reason,
            confidence=0.85,
            conflicts=tuple(conflicts),
        )

    # Binary, unrecognised. The extension is the last thing left, and it is a
    # hint rather than an answer, so the confidence says so.
    by_ext = sniff_extension(filename)
    if by_ext:
        return Detection(
            types=(by_ext[0],),
            media_type=by_ext[1],
            reason=by_ext[2],
            confidence=0.4,
            conflicts=tuple(conflicts),
        )

    return Detection(
        types=UNKNOWN_WITH_TEXT,
        media_type=None,
        reason="unrecognised",
        confidence=0.0,
        conflicts=tuple(conflicts),
    )


def classify_inline_text(text: str) -> Detection:
    """A pasted message, a typed URL, a phone number — the no-file path."""
    types, media, reason = sniff_text(text)
    return Detection(types=types, media_type=media, reason=reason, confidence=0.85)
