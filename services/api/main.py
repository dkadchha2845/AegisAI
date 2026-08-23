"""
AegisAI API.

    .venv/bin/uvicorn services.api.main:app --reload --port 8000

Everything is optional except the engine. The fine-tuned classifier, the dense
retriever, and the LLM explainer all degrade to something that still answers,
and `/api/health` reports exactly which of them are live — so "is the good
model loaded?" is a question with a checkable answer rather than a hope.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import db as db_mod
from . import llm
from .auth import auth_enabled, seed_admin
from .config import settings
from .db import SessionLocal, init_db
from .engine import classifier as classifier_mod
from .engine.classifier import load_classifier
from .engine.twin import DigitalTwin
from .intel import get_intel
from .rag.coach import get_coach
from .rag.store import get_kb
from .routes import analyze, auth, intel, orgs, reports, session, shield
from .security import RateLimitMiddleware, SecurityHeadersMiddleware
from .stores import probe as store_probe

@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Startup/shutdown hook.

    `@app.on_event("startup")` is deprecated in current FastAPI; a lifespan
    context manager is the supported replacement. `warm()` is defined further
    down the module and resolved at call time, which is after import completes.
    """
    warm()
    yield


app = FastAPI(
    title="AegisAI API",
    version="0.1.0",
    description="Real-time scam-call analysis, artifact checking, and the "
                "Digital Twin forecast.",
    lifespan=lifespan,
)

# Order matters: middleware added last runs first. We want security headers on
# every response (including a 429), and the limiter to run before routing but
# after CORS has had its say on preflight. Starlette runs them outermost-first
# in reverse add order, so add headers, then rate limit, then CORS — CORS ends
# up outermost and preflight is handled before anything else.
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware, enabled=settings.rate_limit_enabled)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analyze.router)
app.include_router(session.router)
app.include_router(auth.router)
app.include_router(reports.router)
app.include_router(intel.router)
app.include_router(shield.router)
app.include_router(orgs.router)


def warm() -> None:
    """Load everything now, not on first request.

    A 3-second cold start is invisible at boot and fatal the first time a
    judge clicks Analyze.
    """
    load_classifier()
    from .engine.ocr import load_ocr
    from .ingest.asr import load_asr
    load_ocr()
    load_asr()
    get_kb()
    get_coach()
    # Provision the database and the seeded admin. Cheap and idempotent; on the
    # default in-memory DB this just recreates an empty schema each boot.
    init_db()
    _db = SessionLocal()
    try:
        seed_admin(_db)
        # Build the FIGAE fraud graph from the historical seed plus any Module 1
        # cases already persisted, so /api/intel answers on the first click. On
        # a fresh in-memory DB this is just the seed; a durable DB carries real
        # saved cases into the graph across restarts.
        from .models_db import CaseRecord

        records = [r.package_json for r in _db.query(CaseRecord).all()]
        get_intel().rebuild(extra_records=records)
    finally:
        _db.close()


def _comparison() -> Dict[str, Any]:
    """Measured macro-F1 of both backends on the held-out archetypes, if
    ml/evaluation/eval_backends.py has been run. This is what gates promotion."""
    path = classifier_mod.COMPARISON_PATH
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


@app.get("/api/health")
def health() -> Dict[str, Any]:
    classifier = load_classifier()
    kb = get_kb()
    twin = DigitalTwin()
    degraded = (list(kb.degraded) + list(twin.degraded) + db_mod.degraded()
                + store_probe.degraded_tags())
    # Only a *genuine* fallback is a degradation. When the lexical model is
    # serving because it measurably beat the checkpoint, the promotion gate did
    # its job and there is nothing to warn about — see classifier.serving_is_fallback.
    if classifier_mod.serving_is_fallback:
        degraded.append("clf:lexical_fallback")

    return {
        "ok": True,
        "contract_version": 1,
        "auth": {
            "enforced": auth_enabled(),
            "backend": "jwt-hs256",
            # In open mode the API acts as the seeded admin; say so rather than
            # implying a login happened.
            "mode": "enforced" if auth_enabled() else "open (demo)",
        },
        "database": {
            "backend": "sqlite" if (settings.database_url or "").startswith("sqlite")
                       or settings.database_url is None else "external",
            "persistent": not db_mod.EPHEMERAL,
            "url_configured": settings.database_url is not None,
        },
        # Which of the compose-stack services are actually reachable. Cached,
        # bounded, and never raising — see stores/probe.py. `in_use` is tracked
        # separately from `reachable` on purpose: Postgres being up does not
        # mean the API writes to it yet.
        "infrastructure": store_probe.probe_all(),
        "classifier": {
            "backend": classifier.backend,
            "checkpoint": str(settings.classifier_dir),
            # "Are the fine-tuned weights actually in memory?" — asked of the
            # classifier itself rather than by comparing `backend` to a string.
            # The string form reported False while the fused backend was serving
            # MuRIL, which is precisely the confident-but-wrong answer this
            # endpoint exists to prevent.
            "loaded": classifier.checkpoint_backed,
            # True when the active model is the best available one — either the
            # fine-tuned checkpoint, or the lexical model *because it won the
            # measured comparison*. False only for a genuine fallback (no
            # checkpoint / failed load), which is also the one degraded case.
            "serving_best": not classifier_mod.serving_is_fallback,
            # Why *this* backend is serving. A checkpoint can be present and
            # still not promoted — see _checkpoint_is_better().
            "reason": classifier_mod.selection_reason,
            "comparison": _comparison(),
        },
        "retrieval": {
            "backend": kb.backend,
            "chunks": len(kb.chunks),
            "documents": sorted({c.doc for c in kb.chunks}),
        },
        "twin": {
            "fitted": not twin.degraded,
            "stages": sorted(twin.transitions.keys()),
            "support": twin.support,
        },
        "coach": {"lines": sum(len(v) for v in get_coach().by_stage.values())},
        "llm": llm.status(),
        "intel": _intel_status(),
        "degraded": degraded,
    }


def _intel_status() -> Dict[str, Any]:
    """FIGAE (Module 2) health: graph size and cluster count. Wrapped so a graph
    build failure degrades the field rather than the whole health check."""
    try:
        g = get_intel().graph()
        s = g.stats()
        return {
            "backend": "networkx",
            "cases": s["total_cases"],
            "clusters": s["active_clusters"],
            "campaigns": s["campaigns"],
            "entities": s["linked_entities"],
        }
    except Exception as exc:  # noqa: BLE001 - health must never 500
        return {"backend": "networkx", "error": str(exc)[:120]}


@app.get("/api/model/card")
def model_card() -> Dict[str, Any]:
    """What the model is, what it was trained on, and where it is weak.

    Served rather than written into the frontend so it cannot drift from the
    thing actually loaded. The limitations are listed as prominently as the
    capabilities on purpose — a model card that only lists strengths is
    marketing.
    """
    classifier = load_classifier()
    twin = DigitalTwin()
    return {
        "name": "AegisAI stage classifier",
        "task": "8-way utterance classification over the scam-call arc",
        "base_model": "google/muril-base-cased",
        "active_backend": classifier.backend,
        "training_data": {
            "source": "synthetic Hinglish corpus, LLM-generated from a seeded "
                      "diversity grid, validated client-side",
            "split": "leave-archetypes-out — whole call skeletons held out for test",
            "why": "utterances within one call share names and phrasing, so an "
                   "utterance-level split leaks test into train and inflates macro-F1",
        },
        "evaluation": {
            "protocol": "macro-F1 on four whole held-out call archetypes, both "
                        "backends scored through the same serving interface "
                        "(ml/evaluation/eval_backends.py)",
            "scores": _comparison(),
            "selection": classifier_mod.selection_reason,
        },
        "limitations": [
            "The fine-tuned checkpoint currently scores macro-F1 0.22 on unseen "
            "archetypes against the lexical baseline's 0.37, so it is trained but "
            "not promoted. It reached 0.98 on validation, which is memorisation of "
            "the training archetypes, not generalisation.",
            "320 synthetic calls is too few for an 8-way classifier. This is a "
            "corpus-size problem; more and more varied calls is the fix, not more "
            "epochs.",
            "Trained on synthetic calls. Real-world transfer is unmeasured.",
            "PAYMENT_SETUP and PAYMENT_EXECUTION have 2 and 4 test examples. No "
            "per-class figure for them is quotable.",
            "Text-only. Prosodic coercion features are absent without live audio.",
            "Hinglish and English only.",
            "Not a substitute for reporting fraud on 1930 or cybercrime.gov.in.",
        ],
        "twin": {
            "kind": "first-order Markov over collapsed stage runs",
            "why_collapsed": "raw turn-to-turn matrices are ~85% self-transitions, "
                             "so the forecast would predict the stage already in progress",
            "eta_statistic": "median turns, not mean — turn counts are heavily "
                             "right-skewed and a mean ETA is dragged into uselessness",
            "fitted": not twin.degraded,
        },
    }
