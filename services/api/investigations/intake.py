"""
Turning a request into evidence — task 1.6's front door.

**Why it exists.** `POST /api/investigations` accepts two very different
things: a JSON body with a pasted message, and a multipart upload with a
screenshot, a PDF or an APK. Both have to become the same `list[EvidenceItem]`,
or every agent downstream needs to know which door the evidence came through.
This module is that convergence, and it is also where ARCHITECTURE.md §8's
upload controls live: a size cap enforced *while reading* rather than after,
a bound on how many artefacts one submission may carry, and filename
sanitisation.

**What it consumes.** Bytes and inline strings, with the filename and MIME type
the uploader claimed — both recorded, neither trusted.

**What it outputs.** `EvidenceItem`s ready to go on `InvestigationState.inputs`,
plus any degradation tags collected on the way.

**How it connects.** `routes/investigations.py` calls `read_capped()` per
uploaded part and then `build_items()`; `stores/blobs.py` holds the bytes;
`agents/classify` reads them back through `EvidenceItem.uri` on the first graph
node.

**How it is evaluated.** `test_investigations_api.py`: a 4 MB+1 upload is
refused, a ninth artefact is refused, a traversing filename is defanged, a
UTF-8 payload is inlined and a binary one is not, and an unwritable blob store
degrades the submission instead of failing it.

**Limitations, stated.** There is no per-organisation storage quota — §8 names
one and this task does not build it, so eight 4 MB uploads per submission is
the only bound on disk growth. Nothing is scanned for malware; the APK agent
(2.8) is what handles a hostile upload, in a network-less container, and until
it exists an uploaded APK is stored and classified but not opened.

Why intake does not reject on magic bytes
-----------------------------------------
`CLAUDE.md` requires uploads to be validated "by magic bytes, not extension",
and the sniffing that does it lives in `agents/classify/sniff.py`. It runs on
the first graph node rather than here, and that placement is the point rather
than an omission.

There is no allowlist to reject against: the product's promise is "upload
anything", so a type that is not on a list is not by itself a reason to refuse.
What matters is the *disagreement* — an APK named `photo.jpg`, a PDF declared
`text/plain` — and a disagreement is evidence. Rejecting at the door would turn
the most interesting fact about a hostile upload into a 415 with nothing
recorded. So the declared type and the filename are written down verbatim, the
classifier decides what the bytes actually are, and the mismatch becomes a
`type_conflict` finding on the case. The routing decision is still made from the
bytes, which is what the invariant is protecting.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import List, Optional, Protocol, Sequence

from schema.models import EvidenceItem, utc_now_iso

from ..config import settings
from ..stores.blobs import EvidenceBlobs

#: How many artefacts one submission may carry. Not a technical limit — a
#: bound on the blast radius of a single request, since each may be
#: `max_upload_bytes` and all of them are held in memory while being hashed.
MAX_ITEMS = 8

#: Bytes read per chunk while enforcing the cap. Small enough that a refused
#: upload is refused after ~64 KB rather than after the whole body has been
#: buffered, large enough that a 4 MB file is 64 reads.
CHUNK = 64 * 1024

#: The longest pasted artefact accepted inline, in characters. The same cap
#: `/api/analyze/text` already uses, so the two front doors agree about what
#: "a message" is. Anything longer is an upload, and becomes a blob.
MAX_INLINE_CHARS = 200_000

#: An uploaded file is *also* inlined as `text` when it is no bigger than this
#: and decodes cleanly as UTF-8. `EvidenceItem.text` is documented as being for
#: "payloads that are genuinely small and textual", and this is the measurement
#: of that phrase. Note what it is not: it does not decide the item's *type*.
#: That is the classifier's job, on the bytes, and this only decides whether a
#: copy small enough to carry can ride along in the state.
INLINE_FILE_BYTES = 64 * 1024

#: Filename characters kept. Everything else — path separators, control
#: characters, anything non-ASCII — is replaced, so a name can never escape the
#: directory it is displayed in or smuggle a terminal escape into a log line.
_FILENAME_KEEP = re.compile(r"[^A-Za-z0-9 ._-]")


class IntakeError(ValueError):
    """Base class for a submission this service will not accept."""


class EvidenceTooLarge(IntakeError):
    """One artefact exceeded `settings.max_upload_bytes`."""


class TooManyItems(IntakeError):
    """More than `MAX_ITEMS` artefacts in one submission."""


class NoEvidence(IntakeError):
    """Nothing to investigate. An empty case is not a case."""


class Readable(Protocol):
    """The one method this module needs from an upload.

    A Protocol rather than `fastapi.UploadFile` so the cap can be tested with
    ten lines of fake and so nothing in this package imports the web framework.
    """

    async def read(self, size: int = -1) -> bytes: ...


async def read_capped(source: Readable, limit: Optional[int] = None) -> bytes:
    """Read an upload, refusing the moment it passes `limit`.

    Chunked, and this is the whole point: `await file.read()` followed by a
    length check — which is what the older `/api/analyze/*` routes do — has
    already buffered the entire body by the time it decides to reject it, so a
    500 MB upload costs 500 MB of memory to say no to. Here the refusal happens
    one chunk past the cap.
    """
    cap = settings.max_upload_bytes if limit is None else limit
    buf = bytearray()
    while True:
        chunk = await source.read(CHUNK)
        if not chunk:
            break
        buf.extend(chunk)
        if len(buf) > cap:
            raise EvidenceTooLarge(
                f"one piece of evidence may be at most {cap // 1024 // 1024} MB"
            )
    return bytes(buf)


def sanitise_filename(name: Optional[str]) -> Optional[str]:
    """A filename safe to store, log and render.

    The basename only, so `../../etc/passwd` and `C:\\Windows\\x.dll` both
    collapse to a leaf. The result is never used to build a path — blobs are
    named by their sha256 — so this is about display and logging rather than
    traversal, and it is done anyway because a name that reaches a UI, a PDF and
    an audit row should not be able to carry control characters.
    """
    if not name:
        return None
    leaf = name.replace("\\", "/").rsplit("/", 1)[-1]
    cleaned = _FILENAME_KEEP.sub("_", leaf).strip(" .")
    return cleaned[:120] or None


@dataclass(frozen=True)
class Submission:
    """One artefact as it arrived, before it is anything.

    Exactly one of `data` and `text` is set: `data` for an uploaded part,
    `text` for a JSON body. Keeping them distinct rather than encoding the
    string to bytes at the boundary means an inline paste is never given a
    filename it did not have, and an upload is never inlined just because it
    happened to be readable.
    """

    data: Optional[bytes] = None
    text: Optional[str] = None
    filename: Optional[str] = None
    declared_type: Optional[str] = None


@dataclass
class Intake:
    """What a submission became."""

    items: List[EvidenceItem] = field(default_factory=list)
    degraded: List[str] = field(default_factory=list)


def _inline_text(data: bytes) -> Optional[str]:
    """A small UTF-8 payload as a string, else None.

    Deliberately strict: a NUL byte means binary regardless of what UTF-8 says
    about it, and no other codec is attempted. Guessing cp1252 the way
    `/api/analyze/file` does is right for a route whose only job is to read the
    text; here a failed decode is not a dead end, because the bytes are in the
    blob store and an agent that knows the format will read them properly.
    """
    if len(data) > INLINE_FILE_BYTES or b"\x00" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def build_items(
    case_id: str,
    submissions: Sequence[Submission],
    blobs: Optional[EvidenceBlobs] = None,
) -> Intake:
    """Turn a submission into evidence items, storing any bytes.

    Raises `NoEvidence` on an empty submission and `TooManyItems` past the cap.
    A blob store that cannot write degrades — the item keeps its hash, its
    metadata and any inline text, and the tag says what was lost — because an
    unwritable disk should not cost a frightened person their answer.
    """
    if not submissions:
        raise NoEvidence("submit at least one piece of evidence")
    if len(submissions) > MAX_ITEMS:
        raise TooManyItems(f"at most {MAX_ITEMS} pieces of evidence per investigation")

    intake = Intake()
    for i, sub in enumerate(submissions, start=1):
        item_id = f"ev-{i:02d}"
        received = utc_now_iso()
        filename = sanitise_filename(sub.filename)

        if sub.data is not None:
            digest = hashlib.sha256(sub.data).hexdigest()
            uri = blobs.write(case_id, digest, sub.data) if blobs is not None else None
            if uri is None and "store:blobs:unwritable" not in intake.degraded:
                # Named the same as the health tag on purpose: one string for
                # one condition, so a degraded investigation and a degraded
                # status line are searchable together.
                intake.degraded.append("store:blobs:unwritable")
            intake.items.append(
                EvidenceItem(
                    id=item_id,
                    filename=filename,
                    declared_type=sub.declared_type,
                    size_bytes=len(sub.data),
                    sha256=digest,
                    uri=uri,
                    text=_inline_text(sub.data),
                    received_at=received,
                )
            )
            continue

        text = sub.text or ""
        if not text.strip():
            raise NoEvidence("a submitted message may not be empty")
        if len(text) > MAX_INLINE_CHARS:
            raise EvidenceTooLarge(
                f"a pasted message may be at most {MAX_INLINE_CHARS:,} characters — "
                "upload it as a file instead"
            )
        encoded = text.encode("utf-8")
        intake.items.append(
            EvidenceItem(
                id=item_id,
                filename=filename,
                declared_type=sub.declared_type,
                size_bytes=len(encoded),
                sha256=hashlib.sha256(encoded).hexdigest(),
                text=text,
                received_at=received,
            )
        )

    return intake


__all__ = [
    "CHUNK",
    "INLINE_FILE_BYTES",
    "MAX_INLINE_CHARS",
    "MAX_ITEMS",
    "EvidenceTooLarge",
    "Intake",
    "IntakeError",
    "NoEvidence",
    "Readable",
    "Submission",
    "TooManyItems",
    "build_items",
    "read_capped",
    "sanitise_filename",
]
