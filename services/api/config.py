"""
Runtime configuration for the AegisAI API.

Every capability here is optional and degrades to something that still works
offline. That is deliberate: the demo runs on a conference wifi that may or
may not resolve DNS, so nothing in the request path is allowed to *require*
a network call. When a capability is unavailable the engine records a tag in
`StateFrame.degraded` rather than silently substituting a worse answer —
the UI shows the degradation, which is more honest than a confident number
built on nothing.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader — real environment variables always win.

    The repo ships a .env.example and the README tells people to copy it, but
    nothing was reading the file: every capability it configured (Gemini
    explanations, a persistent DATABASE_URL) silently stayed off. A dependency
    on python-dotenv is not worth it for KEY=value lines, so parse them here.
    """
    try:
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip("'\"")
            if key and key not in os.environ:
                os.environ[key] = value
    except OSError:
        pass


_load_dotenv(REPO_ROOT / ".env")


def _env(name: str, default: Any = None) -> Any:
    """Read `AEGIS_*`, falling back to the pre-rename `PRESAGE_*` spelling.

    The project was renamed PRESAGE/KAVACH -> AegisAI. A developer's local
    `.env` is untracked, so it still carries the old prefix; silently ignoring
    it would turn a configured capability off with no signal, which is exactly
    the failure mode this file exists to prevent. Honour both, prefer the new.
    """
    raw = os.getenv(name)
    if raw is None and name.startswith("AEGIS_"):
        raw = os.getenv("PRESAGE_" + name[len("AEGIS_"):])
    return default if raw is None else raw


ML_DIR = REPO_ROOT / "ml"
ARTIFACT_DIR = Path(_env("AEGIS_ARTIFACTS", ML_DIR / "artifacts"))
KNOWLEDGE_DIR = Path(__file__).resolve().parent / "knowledge"
DATA_DIR = ML_DIR / "data"


def _flag(name: str, default: bool = False) -> bool:
    raw = _env(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    # --- Model serving ----------------------------------------------------
    # Path to the fine-tuned MuRIL checkpoint exported by the training
    # notebook. Absent => the engine falls back to the lexical classifier and
    # tags `clf:lexical_fallback`.
    classifier_dir: Path = ARTIFACT_DIR / "stage-classifier"
    # Fitted transition matrix + dwell times for the Digital Twin.
    twin_path: Path = DATA_DIR / "processed" / "transitions.json"

    # --- Retrieval --------------------------------------------------------
    knowledge_dir: Path = KNOWLEDGE_DIR
    # sentence-transformers if installed, else deterministic TF-IDF. Both
    # return citations; only the ranking quality differs.
    prefer_dense_embeddings: bool = _flag("AEGIS_DENSE_RAG", True)

    # --- OCR (image inputs — screenshots, notices, QR) --------------------
    # tesseract (default) | easyocr | none. Every backend is optional and
    # degrades to `ocr:unavailable` if its dependency (or Tesseract's system
    # binary) is missing, so a clean clone still starts.
    ocr_backend: str = _env("AEGIS_OCR", "tesseract")

    # --- LLM (explanations only, never scoring) ---------------------------
    llm_backend: str = _env("AEGIS_LLM", "none")
    llm_model: str | None = _env("AEGIS_MODEL") or None
    gemini_key: str | None = os.getenv("GEMINI_API_KEY") or None
    ollama_host: str = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")

    # --- Persistence & auth -----------------------------------------------
    # SQLAlchemy URL. Unset => an ephemeral in-memory SQLite (tagged
    # `db:ephemeral`), so the clean-clone demo still boots with zero setup.
    # Point it at a file or Postgres to persist: DATABASE_URL=sqlite:///aegis.db
    database_url: str | None = os.getenv("DATABASE_URL") or None
    # Off by default so the demo needs no login. Flip on to require a bearer
    # token on protected routes: AEGIS_AUTH=1.
    auth_enforced: bool = _flag("AEGIS_AUTH", False)
    # HMAC signing key for session tokens. Empty => a per-process key is
    # generated (dev), and tokens do not survive a restart — set this in prod.
    secret_key: str = _env("AEGIS_SECRET_KEY", "")
    token_ttl_s: int = int(_env("AEGIS_TOKEN_TTL", str(12 * 3600)))
    # Seeded on first boot if the user table is empty. Change the password.
    default_admin_email: str = _env("AEGIS_ADMIN_EMAIL", "admin@aegis.local")
    default_admin_password: str = _env("AEGIS_ADMIN_PASSWORD", "changeme")

    # --- Transport & hardening --------------------------------------------
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")
    # In-process rate limiting + security headers. On by default; flip off with
    # AEGIS_RATELIMIT=0 for a load test or a single-tenant offline appliance.
    rate_limit_enabled: bool = _flag("AEGIS_RATELIMIT", True)
    # Frames per second pushed over the socket. 4 is plenty: the transcript
    # updates on utterance boundaries, and the meter interpolates in CSS.
    frame_hz: float = float(_env("AEGIS_FRAME_HZ", "4"))
    max_upload_bytes: int = 4 * 1024 * 1024


settings = Settings()
