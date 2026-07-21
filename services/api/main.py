"""
PRESAGE API.

    .venv/bin/uvicorn services.api.main:app --reload --port 8000

Everything is optional except the engine. The fine-tuned classifier, the dense
retriever, and the LLM explainer all degrade to something that still answers,
and `/api/health` reports exactly which of them are live — so "is the good
model loaded?" is a question with a checkable answer rather than a hope.
"""

from __future__ import annotations

import json
from typing import Any, Dict

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
from .rag.coach import get_coach
from .rag.store import get_kb
from .routes import analyze, auth, reports, session

app = FastAPI(
    title="PRESAGE API",
    version="0.1.0",
    description="Real-time scam-call analysis, artifact checking, and the "
                "Digital Twin forecast.",
)

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


@app.on_event("startup")
def warm() -> None:
    """Load everything now, not on first request.

    A 3-second cold start is invisible at boot and fatal the first time a
    judge clicks Analyze.
    """
    load_classifier()
    get_kb()
    get_coach()
    # Provision the database and the seeded admin. Cheap and idempotent; on the
    # default in-memory DB this just recreates an empty schema each boot.
    init_db()
    _db = SessionLocal()
    try:
        seed_admin(_db)
    finally:
        _db.close()


def _comparison() -> Dict[str, Any]:
    """Measured macro-F1 of both backends on the held-out archetypes, if
    ml/eval_backends.py has been run. This is what gates promotion."""
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
    degraded = list(kb.degraded) + list(twin.degraded) + db_mod.degraded()
    if classifier.backend != "muril":
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
        "classifier": {
            "backend": classifier.backend,
            "checkpoint": str(settings.classifier_dir),
            "loaded": classifier.backend == "muril",
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
        "degraded": degraded,
    }


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
        "name": "PRESAGE stage classifier",
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
                        "(ml/eval_backends.py)",
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
