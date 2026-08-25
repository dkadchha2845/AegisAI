"""
Where an uploaded artefact's *bytes* live — task 1.6.

**Why it exists.** Task 1.5 built the evidence store and stated the hole it
left: `EvidenceItem.uri` "points at an object store that does not exist, so
today an uploaded screenshot's bytes are not durable — only its hash, metadata
and any inline text. Uploads are 1.6." This is that object store, at the size
this project actually needs one. Without it `POST /api/investigations` with a
file attached would be a route that accepts a screenshot, classifies it, and
throws it away — and every Phase 2 agent (OCR, QR, image forensics, APK) needs
to read the bytes again *after* intake, on a graph node, from a `uri`.

**What it consumes.** Bytes, plus the organisation and case they belong to.

**What it outputs.** A `uri` to put on `EvidenceItem.uri`, and the bytes back
when asked for that uri.

**How it connects.** `investigations/intake.py` writes here during intake;
`agents/classify/agent.py` reads here when an item carries a uri and this
process does not already hold the blob; `routes/investigations.py` erases here
when a case is deleted.

**How it is evaluated.** `test_investigations_api.py` — a round trip, a
cross-organisation read that fails, a path-traversal uri that fails, erasure
that actually removes the file, and an unwritable root that degrades instead of
raising.

**Limitations, stated.** This is a directory on a local disk, not S3 and not a
replicated object store; two API replicas do not share it. There is no per-org
quota (ARCHITECTURE.md §8 names one and this task does not implement it), and
nothing here is encrypted at rest — that is volume encryption at deploy time,
and claiming it in a docstring would be an unmeasured security claim. The root
is a per-process temp directory unless `AEGIS_EVIDENCE_DIR` is set, exactly
like the ephemeral database, so a clean clone still boots with zero setup.

Why blobs are scoped to a case rather than content-addressed globally
---------------------------------------------------------------------
The obvious design stores one copy per sha256 and lets any case that uploaded
the same screenshot share it. That is a better deduplication story and a worse
erasure story, and erasure is the requirement here: `DELETE /{id}` is a
right-to-be-forgotten path, and under global content addressing "may I delete
these bytes" becomes "is any other case still referencing them", which is a
reference count. A right to erasure that depends on a reference count being
correct is one that fails quietly, in the direction of keeping data.

So the layout is `<root>/<org>/<case>/<sha256>`: deleting a case is deleting a
directory, it is complete by construction, and it cannot take another case's
evidence with it. The sha256 still names the file, so a repeated upload inside
one case is still stored once and the name still proves the content.
"""

from __future__ import annotations

import atexit
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Optional

from ..config import settings
from ..db import EPHEMERAL as DB_EPHEMERAL

#: `aegis-blob:<org>/<case>/<sha256>`. Self-contained on purpose: an agent
#: holding one `EvidenceItem` can resolve it without being told which case it
#: came from, and the org component is what lets the read be refused when the
#: caller is scoped to a different tenant.
URI_SCHEME = "aegis-blob:"

#: Every path component is validated against this before it touches the
#: filesystem. The components are minted by this service, but they make a round
#: trip through a database column, and a store that reconstructs a path from a
#: value it read back is one `../../` away from serving an arbitrary file.
_SAFE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class BlobRejected(ValueError):
    """A uri that does not name something this store could ever have written.

    Distinct from "not found": a malformed or traversing uri is a caller bug or
    an attack, and collapsing it into `None` would hide both.
    """


def _default_root() -> Path:
    """The blob root, and whether it survives a restart.

    A configured directory is used exactly as given. Without one this mirrors
    `db.py`: a per-process temp directory, deleted at exit, so the zero-setup
    clone still accepts an upload and nothing is left behind afterwards.
    """
    if settings.evidence_dir is not None:
        return Path(settings.evidence_dir)
    tmp = Path(tempfile.mkdtemp(prefix="aegis-evidence-"))

    @atexit.register
    def _cleanup() -> None:  # pragma: no cover - process teardown
        shutil.rmtree(tmp, ignore_errors=True)

    return tmp


#: Resolved once, at import, for the same reason `db.engine` is: a root that
#: could change mid-process would mean a uri written before the change cannot
#: be read after it.
ROOT: Path = _default_root()

#: True when the bytes do not survive a restart.
EPHEMERAL: bool = settings.evidence_dir is None


def degraded() -> list[str]:
    """Health tags for the blob root.

    `blobs:ephemeral` is reported **only** when the database is durable and this
    is not. An install where everything is ephemeral is already fully described
    by `db:ephemeral`, and a second tag saying the same thing trains people to
    ignore both. The mismatch is the surprising state and the one worth naming:
    a case that survives a restart whose screenshot does not is a case whose
    report cannot be re-rendered, and that should be discovered on the status
    line rather than three weeks later.
    """
    tags: list[str] = []
    if EPHEMERAL and not DB_EPHEMERAL:
        tags.append("blobs:ephemeral")
    if not writable():
        tags.append("store:blobs:unwritable")
    return tags


def writable() -> bool:
    """Can this process actually write a blob? Answered by trying.

    Checked rather than assumed because the failure it guards against —
    a read-only mount, a full disk, a directory owned by someone else — is
    exactly the kind that a permissions bit does not predict.
    """
    try:
        ROOT.mkdir(parents=True, exist_ok=True)
        probe = ROOT / ".writable"
        probe.write_bytes(b"")
        probe.unlink()
        return True
    except OSError:
        return False


def status() -> dict[str, object]:
    """What `/api/health` says about evidence storage."""
    return {
        "backend": "filesystem",
        "root": str(ROOT),
        "persistent": not EPHEMERAL,
        "writable": writable(),
    }


def _components(uri: str) -> tuple[str, str, str]:
    """Split and validate a uri. Raises `BlobRejected` on anything unsafe."""
    if not uri.startswith(URI_SCHEME):
        raise BlobRejected(f"not a blob uri: {uri[:64]!r}")
    parts = uri[len(URI_SCHEME):].split("/")
    if len(parts) != 3:
        raise BlobRejected("a blob uri is <org>/<case>/<sha256>")
    org, case, digest = parts
    if not (_SAFE.match(org) and _SAFE.match(case) and _SHA256.match(digest)):
        raise BlobRejected("blob uri component failed validation")
    return org, case, digest


class EvidenceBlobs:
    """The bytes of one organisation's evidence.

    Scoped at construction and with no cross-org accessor, for the same reason
    `EvidenceStore` is: a repository that *cannot express* another tenant's read
    is a design, where a route that remembers to check is a discipline. `read()`
    refuses a uri belonging to another organisation even when the file is right
    there on the disk.
    """

    def __init__(self, org_id: str) -> None:
        if not org_id or not _SAFE.match(org_id):
            raise ValueError(f"EvidenceBlobs needs a filesystem-safe org id, got {org_id!r}")
        self.org_id = org_id

    # -- writes ------------------------------------------------------------

    def write(self, case_id: str, digest: str, data: bytes) -> Optional[str]:
        """Store one artefact and return its uri, or None if storage is down.

        None rather than an exception: an unwritable evidence directory must
        degrade the investigation, not fail it. The item keeps its hash, its
        metadata and any inline text, the classifier still runs on the bytes
        this process is holding, and the caller records the degradation.
        """
        if not (_SAFE.match(case_id) and _SHA256.match(digest)):
            raise BlobRejected("case id or digest failed validation")
        target = ROOT / self.org_id / case_id / digest
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            # Write-then-rename: a reader can never observe a partial file, and
            # a crash mid-write leaves a temp file rather than a blob whose name
            # promises a hash its contents do not have.
            fd, tmp_name = tempfile.mkstemp(dir=str(target.parent), prefix=".part-")
            try:
                with os.fdopen(fd, "wb") as fh:
                    fh.write(data)
                os.replace(tmp_name, target)
            except OSError:
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass
                raise
        except OSError:
            return None
        return f"{URI_SCHEME}{self.org_id}/{case_id}/{digest}"

    # -- reads -------------------------------------------------------------

    def read(self, uri: str) -> Optional[bytes]:
        """The bytes behind a uri, or None if they are not there any more.

        Raises `BlobRejected` for a uri that is malformed or belongs to another
        organisation — the two cases a caller must not be able to confuse with
        "this evidence has been erased".
        """
        org, case, digest = _components(uri)
        if org != self.org_id:
            raise BlobRejected(
                f"blob belongs to org {org!r}; this store is scoped to {self.org_id!r}"
            )
        try:
            return (ROOT / org / case / digest).read_bytes()
        except OSError:
            return None

    # -- erasure -----------------------------------------------------------

    def delete_case(self, case_id: str) -> int:
        """Remove every blob of one case. Returns how many files went.

        Counted rather than returning a bool because erasure is the one
        operation whose report should be specific: "deleted the case and its 3
        artefacts" is auditable, "ok" is not.
        """
        if not _SAFE.match(case_id):
            raise BlobRejected("case id failed validation")
        folder = ROOT / self.org_id / case_id
        if not folder.is_dir():
            return 0
        count = sum(1 for p in folder.iterdir() if p.is_file())
        shutil.rmtree(folder, ignore_errors=True)
        return count


__all__ = [
    "EPHEMERAL",
    "ROOT",
    "URI_SCHEME",
    "BlobRejected",
    "EvidenceBlobs",
    "degraded",
    "status",
    "writable",
]
