"""
Runtime configuration for the PRESAGE API.

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
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ML_DIR = REPO_ROOT / "ml"
ARTIFACT_DIR = Path(os.getenv("PRESAGE_ARTIFACTS", ML_DIR / "artifacts"))
KNOWLEDGE_DIR = Path(__file__).resolve().parent / "knowledge"
DATA_DIR = ML_DIR / "data"


def _flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
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
    prefer_dense_embeddings: bool = _flag("PRESAGE_DENSE_RAG", True)

    # --- OCR (image inputs — screenshots, notices, QR) --------------------
    # tesseract (default) | easyocr | none. Every backend is optional and
    # degrades to `ocr:unavailable` if its dependency (or Tesseract's system
    # binary) is missing, so a clean clone still starts.
    ocr_backend: str = os.getenv("PRESAGE_OCR", "tesseract")

    # --- LLM (explanations only, never scoring) ---------------------------
    llm_backend: str = os.getenv("PRESAGE_LLM", "none")
    llm_model: str | None = os.getenv("PRESAGE_MODEL") or None
    gemini_key: str | None = os.getenv("GEMINI_API_KEY") or None
    ollama_host: str = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")

    # --- Persistence & auth -----------------------------------------------
    # SQLAlchemy URL. Unset => an ephemeral in-memory SQLite (tagged
    # `db:ephemeral`), so the clean-clone demo still boots with zero setup.
    # Point it at a file or Postgres to persist: DATABASE_URL=sqlite:///kavach.db
    database_url: str | None = os.getenv("DATABASE_URL") or None
    # Off by default so the demo needs no login. Flip on to require a bearer
    # token on protected routes: PRESAGE_AUTH=1.
    auth_enforced: bool = _flag("PRESAGE_AUTH", False)
    # HMAC signing key for session tokens. Empty => a per-process key is
    # generated (dev), and tokens do not survive a restart — set this in prod.
    secret_key: str = os.getenv("PRESAGE_SECRET_KEY", "")
    token_ttl_s: int = int(os.getenv("PRESAGE_TOKEN_TTL", str(12 * 3600)))
    # Seeded on first boot if the user table is empty. Change the password.
    default_admin_email: str = os.getenv("PRESAGE_ADMIN_EMAIL", "admin@kavach.local")
    default_admin_password: str = os.getenv("PRESAGE_ADMIN_PASSWORD", "changeme")

    # --- Transport & hardening --------------------------------------------
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")
    # In-process rate limiting + security headers. On by default; flip off with
    # PRESAGE_RATELIMIT=0 for a load test or a single-tenant offline appliance.
    rate_limit_enabled: bool = _flag("PRESAGE_RATELIMIT", True)
    # Frames per second pushed over the socket. 4 is plenty: the transcript
    # updates on utterance boundaries, and the meter interpolates in CSS.
    frame_hz: float = float(os.getenv("PRESAGE_FRAME_HZ", "4"))
    max_upload_bytes: int = 4 * 1024 * 1024


settings = Settings()
