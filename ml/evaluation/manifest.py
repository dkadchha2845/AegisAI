"""
Checkpoint identity: bind measured metrics to the exact model that produced them.

This project has now been bitten twice by metric files drifting from the model
they describe:

  * A stale `backend_comparison.json` (macro-F1 0.221) pinned serving to the
    weaker lexical model for weeks, while the checkpoint on disk actually
    scored 0.767.
  * `stage-classifier/metrics.json` records macro-F1 0.269 for a checkpoint
    whose real score is 0.767 — it describes an earlier model, and it is one of
    only two artifact files committed to git.

Both are the same bug: a number in a file with nothing tying it to a model. A
JSON file cannot go stale if it carries the fingerprint of the weights it was
measured against, because the mismatch becomes checkable.

So the manifest records *what was measured*, *on which split*, and *of which
exact bytes*. `verify()` then answers "do these metrics describe the checkpoint
I actually have?" — a question that previously had no answer.

Written by `eval_backends.py` (which already pays the model-load cost) and
checked by `make verify-checkpoint`.
"""

from __future__ import annotations

import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

MANIFEST_NAME = "checkpoint_manifest.json"

#: Files that define a checkpoint's behaviour. The tokenizer is included on
#: purpose: identical weights with a different vocab decode differently, and
#: that has to count as a different model.
FINGERPRINT_FILES = (
    "pytorch_model.bin",
    "model.safetensors",
    "config.json",
    "tokenizer.json",
    "vocab.txt",
)

_CHUNK = 1024 * 1024


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(_CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def fingerprint(model_dir: Path) -> Dict[str, Any]:
    """Content hashes of every file that defines this checkpoint's behaviour.

    Absent files are simply skipped — a safetensors export and a .bin export
    are both valid, and requiring both would reject a legitimate checkpoint.
    """
    files: Dict[str, Dict[str, Any]] = {}
    for name in FINGERPRINT_FILES:
        p = model_dir / name
        if p.exists():
            files[name] = {"sha256": _sha256(p), "bytes": p.stat().st_size}
    combined = hashlib.sha256(
        "".join(f"{k}:{v['sha256']}" for k, v in sorted(files.items())).encode()
    ).hexdigest()
    return {"files": files, "combined_sha256": combined}


def build(
    model_dir: Path,
    results: Dict[str, Dict[str, float]],
    split: str,
    n_examples: int,
) -> Dict[str, Any]:
    """Assemble the manifest for a just-completed evaluation."""
    return {
        "schema": 1,
        "measured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "checkpoint_dir": model_dir.name,
        "fingerprint": fingerprint(model_dir),
        "evaluation": {
            "split": split,
            "n_examples": n_examples,
            "results": results,
            # Named so nobody has to guess which script produced this.
            "produced_by": "ml/evaluation/eval_backends.py",
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
    }


def write(manifest: Dict[str, Any], out_dir: Path) -> Path:
    path = out_dir / MANIFEST_NAME
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    return path


def load(path: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def verify(model_dir: Path, manifest: Dict[str, Any]) -> tuple[bool, str]:
    """Do these metrics describe the checkpoint on disk?

    Returns (ok, human-readable reason). Never raises: a missing checkpoint is
    a normal state (CI has none), not an error.
    """
    if not model_dir.exists():
        return False, f"no checkpoint at {model_dir}"

    recorded = manifest.get("fingerprint", {}).get("files", {})
    if not recorded:
        return False, "manifest carries no fingerprint"

    actual = fingerprint(model_dir)["files"]

    missing = sorted(set(recorded) - set(actual))
    if missing:
        return False, f"checkpoint is missing {', '.join(missing)}"

    drifted = [
        name for name, rec in recorded.items()
        if actual[name]["sha256"] != rec["sha256"]
    ]
    if drifted:
        return False, (
            f"{', '.join(drifted)} changed since the metrics were measured — "
            "the recorded scores describe a different model. Re-run "
            "ml/evaluation/eval_backends.py."
        )
    return True, "checkpoint matches the recorded metrics"


def main() -> int:
    """`make verify-checkpoint` — check the on-disk model against the manifest."""

    ml_dir = Path(__file__).resolve().parents[1]
    artifacts = ml_dir / "artifacts"
    model_dir = artifacts / "stage-classifier"
    manifest = load(artifacts / MANIFEST_NAME)

    if manifest is None:
        print(f"no {MANIFEST_NAME} — run ml/evaluation/eval_backends.py first")
        return 0  # not a failure: a clean clone has neither file

    ok, reason = verify(model_dir, manifest)
    scores = manifest["evaluation"]["results"]
    print(f"manifest measured {manifest['measured_at']} on split "
          f"'{manifest['evaluation']['split']}' ({manifest['evaluation']['n_examples']} examples)")
    for backend, s in sorted(scores.items()):
        print(f"  {backend:10s} macro-F1 {s['macro_f1']:.4f}")
    print(f"\n{'OK  ' if ok else 'FAIL'} {reason}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
