"""
Runtime configuration for the AegisAI API.

Every capability here is optional and degrades to something that still works
offline. That is deliberate: nothing in the request path is allowed to *require*
a network call. When a capability is unavailable the engine records a tag in
`StateFrame.degraded` rather than silently substituting a worse answer — the UI
shows the degradation, which is more honest than a confident number built on
nothing.

Backed by pydantic-settings, which buys three things the hand-rolled version
could not:

  * **Validation.** `AEGIS_PG_PORT=not-a-number` fails at startup with the field
    named, instead of raising somewhere unrelated on first use.
  * **Declarative back-compat.** The project was renamed PRESAGE -> AegisAI, and
    a developer's untracked `.env` still carries the old prefix. Every renamed
    setting accepts both spellings through `AliasChoices`, so an old file keeps
    working. Silently ignoring it would switch a configured capability off with
    no signal — exactly the failure this module exists to prevent.
  * **One source of config.** Settings read straight from `os.getenv` elsewhere
    bypass that back-compat; `AEGIS_OCR` did, which meant `PRESAGE_OCR=easyocr`
    quietly fell back to tesseract.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]
ML_DIR = REPO_ROOT / "ml"
KNOWLEDGE_DIR = Path(__file__).resolve().parent / "knowledge"
DATA_DIR = ML_DIR / "data"


def _alias(name: str) -> AliasChoices:
    """Accept `AEGIS_NAME`, falling back to the pre-rename `PRESAGE_NAME`."""
    return AliasChoices(f"AEGIS_{name}", f"PRESAGE_{name}")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        # Real environment variables outrank the .env file — pydantic-settings
        # does this by default, and the test suite depends on it: conftest pins
        # DATABASE_URL and AEGIS_LLM before import so tests stay hermetic.
        extra="ignore",
        # Immutable once built, so nothing can reconfigure the app mid-request.
        frozen=True,
    )

    # --- Paths -------------------------------------------------------------
    artifact_dir: Path = Field(
        default=ML_DIR / "artifacts",
        validation_alias=_alias("ARTIFACTS"),
        description="Where trained checkpoints live.",
    )
    knowledge_dir: Path = Field(
        default=KNOWLEDGE_DIR,
        description="Curated advisory corpus for retrieval.",
    )
    twin_path: Path = Field(
        default=DATA_DIR / "processed" / "transitions.json",
        description="Fitted transition matrix + dwell times for the Digital Twin.",
    )

    # --- Which model a run is allowed to prove (task 1.7b) -----------------
    require_serving_best: bool = Field(
        default=False,
        validation_alias=_alias("REQUIRE_SERVING_BEST"),
        description="Make the gates fail when a genuine fallback classifier is "
                    "serving instead of the best available model. Off by "
                    "default, because a clean clone has no checkpoint and that "
                    "is the documented zero-setup path. Set it on a machine "
                    "that has the weights: `AEGIS_REQUIRE_SERVING_BEST=1 make "
                    "gates` is the checkpoint-backed gate run, and it says so "
                    "rather than quietly proving the stand-in. See "
                    "services/api/serving.py.",
    )

    # --- Retrieval ---------------------------------------------------------
    prefer_dense_embeddings: bool = Field(
        default=True,
        validation_alias=_alias("DENSE_RAG"),
        description="sentence-transformers if installed, else deterministic BM25. "
                    "Both return citations; only ranking quality differs.",
    )

    # --- OCR (screenshots, notices, QR) ------------------------------------
    ocr_backend: str = Field(
        default="tesseract",
        validation_alias=_alias("OCR"),
        description="tesseract | easyocr | none. Every backend is optional and "
                    "degrades to `ocr:unavailable` if its dependency is missing.",
    )

    # --- LLM (explanations and extraction only, never scoring) -------------
    llm_backend: str = Field(default="none", validation_alias=_alias("LLM"))
    llm_model: Optional[str] = Field(default=None, validation_alias=_alias("MODEL"))
    gemini_key: Optional[str] = Field(default=None, validation_alias=AliasChoices("GEMINI_API_KEY"))
    ollama_host: str = Field(default="http://127.0.0.1:11434", validation_alias=AliasChoices("OLLAMA_HOST"))

    # --- Persistence & auth ------------------------------------------------
    database_url: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("DATABASE_URL"),
        description="SQLAlchemy URL. Unset => ephemeral in-memory SQLite "
                    "(tagged `db:ephemeral`), so a clean clone boots with zero setup.",
    )
    auth_enforced: bool = Field(default=False, validation_alias=_alias("AUTH"))
    secret_key: str = Field(
        default="",
        validation_alias=_alias("SECRET_KEY"),
        description="HMAC signing key. Empty => a per-process dev key; tokens "
                    "do not survive a restart. Set this in production.",
    )
    token_ttl_s: int = Field(default=12 * 3600, ge=60, validation_alias=_alias("TOKEN_TTL"))
    default_admin_email: str = Field(default="admin@aegis.local", validation_alias=_alias("ADMIN_EMAIL"))
    default_admin_password: str = Field(default="changeme", validation_alias=_alias("ADMIN_PASSWORD"))
    demo_password: str = Field(
        default="changeme",
        validation_alias=_alias("DEMO_PASSWORD"),
        description="Shared password for the seeded demo roster (open mode only; "
                    "none of those accounts exist when AEGIS_AUTH=1). Configurable "
                    "so a shared demo box is not running on a password that is "
                    "written in the source, and defaulted to the value the sign-in "
                    "screen has always shown so nothing that worked stops working.",
    )
    signup_enabled: bool = Field(
        default=True,
        validation_alias=_alias("SIGNUP"),
        description="Whether POST /api/auth/signup accepts new public accounts. "
                    "A sign-up always creates a CITIZEN — the role is never taken "
                    "from the request — so this is a capacity/abuse switch, not a "
                    "privilege one. Off closes the route with a 403 that names the "
                    "setting.",
    )
    password_reset_ttl_s: int = Field(
        default=3600,
        ge=300,
        le=24 * 3600,
        validation_alias=_alias("PASSWORD_RESET_TTL"),
        description="How long a password-reset token stays redeemable.",
    )
    dev_password_reset: bool = Field(
        default=False,
        validation_alias=_alias("DEV_PASSWORD_RESET"),
        description="Return the password-reset token in the API response instead "
                    "of only printing it to the server log. There is no mail "
                    "transport configured in this project, so without one of the "
                    "two a reset cannot be completed at all — and handing the "
                    "token back over HTTP is exactly the thing you must never do "
                    "in production, which is why it is off by default, refused "
                    "outright when AEGIS_AUTH=1, and labelled in the response.",
    )

    # --- Backing stores (infra/compose/dev.yml) ----------------------------
    # Host/port only: liveness-probe targets for /api/health, not connection
    # strings, so nothing here can leak a credential. The whole block is inert
    # when the stack is down — the documented zero-setup path, not a degradation.
    pg_host: str = Field(default="127.0.0.1", validation_alias=_alias("PG_HOST"))
    pg_port: int = Field(default=5432, ge=1, le=65535, validation_alias=_alias("PG_PORT"))
    neo4j_host: str = Field(default="127.0.0.1", validation_alias=_alias("NEO4J_HOST"))
    neo4j_bolt_port: int = Field(default=7687, ge=1, le=65535, validation_alias=_alias("NEO4J_BOLT_PORT"))
    qdrant_host: str = Field(default="127.0.0.1", validation_alias=_alias("QDRANT_HOST"))
    qdrant_port: int = Field(default=6333, ge=1, le=65535, validation_alias=_alias("QDRANT_PORT"))
    redis_host: str = Field(default="127.0.0.1", validation_alias=_alias("REDIS_HOST"))
    redis_port: int = Field(default=6379, ge=1, le=65535, validation_alias=_alias("REDIS_PORT"))
    redis_db: int = Field(default=0, ge=0, le=15, validation_alias=_alias("REDIS_DB"))
    redis_url: Optional[str] = Field(
        default=None,
        validation_alias=_alias("REDIS_URL"),
        description="Full broker URL, for a Redis that needs a password or TLS. "
                    "Unset => built from the host/port/db above, so the compose "
                    "stack needs no extra variable. This is the one place a "
                    "credential could appear, which is why /api/health reports "
                    "it through `jobs.broker.describe()` and never verbatim.",
    )

    # --- Async job system (task 1.8) ---------------------------------------
    queue_enabled: bool = Field(
        default=True,
        validation_alias=_alias("QUEUE"),
        description="Run investigations on a Celery worker when the broker is "
                    "reachable. On by default and self-degrading: with no Redis "
                    "the graph runs in the API process exactly as it did before "
                    "1.8, tagged `queue:in_process`. Set false to pin that "
                    "behaviour — useful in tests and on a laptop demo.",
    )
    queue_visibility_timeout_s: int = Field(
        default=1800,
        ge=10,
        le=24 * 3600,
        validation_alias=_alias("QUEUE_VISIBILITY_TIMEOUT"),
        description="How long a job taken by a worker stays invisible before the "
                    "broker offers it to another one. This is what makes 'a "
                    "worker crash loses no work' finite rather than theoretical: "
                    "Celery's Redis default is an hour, so a SIGKILLed worker's "
                    "job is redelivered an hour later. It must stay LONGER than "
                    "the slowest task, or a job still running is handed to a "
                    "second worker; 30 minutes clears the `sandbox` queue's "
                    "stated budget of minutes with an order of magnitude spare.",
    )
    queue_max_retries: int = Field(
        default=2,
        ge=0,
        le=10,
        validation_alias=_alias("QUEUE_MAX_RETRIES"),
        description="Redeliveries before an investigation is dead-lettered. Low "
                    "on purpose: the graph already retries individual agents and "
                    "returns COMPLETE with a degraded tag, so a task that raises "
                    "is the orchestrator failing, which repeats.",
    )

    # --- Transport & hardening ---------------------------------------------
    cors_origins: Annotated[tuple[str, ...], NoDecode] = Field(
        default=("http://localhost:5173", "http://127.0.0.1:5173"),
        validation_alias=_alias("CORS_ORIGINS"),
        description="Browser origins allowed to call this API, comma-separated. "
                    "The two defaults are Vite's. An explicit allow-list rather "
                    "than `*` because `allow_credentials=True` and a wildcard "
                    "are not a combination any browser will honour, and should "
                    "not be one this service asks for.",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        """Accept `a,b` from the environment as well as a real sequence.

        `NoDecode` on the annotation is what makes this reachable: without it
        pydantic-settings JSON-decodes a complex field straight out of the
        environment and never calls a validator, so
        `AEGIS_CORS_ORIGINS=http://localhost:5199` took the whole startup down
        with a parse error about JSON when the mistake was a missing bracket.
        """
        if isinstance(v, str):
            return tuple(part.strip() for part in v.split(",") if part.strip())
        return v
    rate_limit_enabled: bool = Field(default=True, validation_alias=_alias("RATELIMIT"))
    frame_hz: float = Field(
        default=4.0, gt=0, le=60,
        validation_alias=_alias("FRAME_HZ"),
        description="Frames per second pushed over the socket. 4 is plenty: the "
                    "transcript updates on utterance boundaries and the meter "
                    "interpolates in CSS.",
    )
    max_upload_bytes: int = Field(default=4 * 1024 * 1024, gt=0)

    evidence_dir: Optional[Path] = Field(
        default=None,
        validation_alias=_alias("EVIDENCE_DIR"),
        description="Where uploaded evidence bytes are stored (task 1.6). Unset "
                    "=> a per-process temp directory deleted at exit, so a clean "
                    "clone accepts an upload with zero setup and leaves nothing "
                    "behind. Set this whenever DATABASE_URL is set, or a case "
                    "will outlive its own screenshots.",
    )

    @field_validator("database_url", "llm_model", "gemini_key", "evidence_dir", mode="before")
    @classmethod
    def _blank_is_unset(cls, v: object) -> object:
        """Treat "" as absent.

        conftest.py sets DATABASE_URL="" to force the ephemeral DB while still
        blocking the .env loader from overriding it — an empty string has to
        mean "explicitly nothing", not "a URL that happens to be empty".
        """
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @property
    def classifier_dir(self) -> Path:
        """The fine-tuned checkpoint. Absent => lexical fallback, tagged."""
        return self.artifact_dir / "stage-classifier"


settings = Settings()

#: Kept as a module-level constant because several modules import it directly
#: and it is derived from a setting rather than being one.
ARTIFACT_DIR = settings.artifact_dir
