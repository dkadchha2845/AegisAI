# AegisAI — Asset Inventory & Honest Gap Analysis

**Date:** 2026-08-23 · **Baseline verified:** 84 backend tests pass, contract consistent,
frontend typecheck clean, production build succeeds.

This document exists so no plan is built on a guess. Everything in "What Exists"
was read or executed on 2026-08-23. Everything in "What Does Not Exist" is
absent from the codebase — not partially built, not stubbed. Per master-context
rule #7, nothing is claimed to work until it is implemented and tested.

---

## 1. Where AegisAI comes from

AegisAI is not a greenfield project. It inherits ~30,000 lines of working,
tested code from **KAVACH/PRESAGE**, a real-time digital-arrest scam-call
detection engine built for the ET AI Hackathon 2026 (PS-6, "AI for Digital
Public Safety"). That engine solved one slice of the AegisAI problem — *live
voice-call fraud* — to a genuinely high standard.

The pivot is one of **breadth and architecture**, not a restart:

| | KAVACH (inherited) | AegisAI (target) |
|---|---|---|
| Input | Voice call, text, image, UPI ID | Any digital evidence: email, SMS, screenshot, QR, URL, PDF, APK, audio, video, phone, UPI, live call |
| Shape | Linear pipeline, one domain | Agent graph, many specialised investigators |
| Output | Threat score + coach line + evidence PDF | Investigation report: risk, evidence chain, relationship graph, recommended actions |
| Scoring | Hand-weighted signal fusion | Hybrid: ML risk model + rules + LLM + graph + threat intel |
| Memory | Per-session | Cross-case, persistent, graph-linked |
| Purpose | Hackathon demo | Capstone + research paper + deployable product |

**Strategic read:** the inherited engine is the strongest single component
AegisAI will have, and it is the hardest one to build. Conversation-level fraud
analysis over a 7-stage psychological arc, with a fine-tuned multilingual model
and false-positive discipline, is *the* differentiator versus every "upload a
screenshot, ask an LLM" project. It should be preserved and promoted to a
first-class agent, not diluted.

---

## 2. What Exists (verified)

### 2.1 Backend — FastAPI, `services/api/` (~50 modules, 84 tests)

**Analysis engine (`engine/`)**
- `classifier.py` — 8-class scam-stage classifier. Fine-tuned **MuRIL** checkpoint
  (macro-F1 **0.767** on a zero-leak, 7/8-held-out-archetype split) wrapped as a
  `FusedStageClassifier` (MuRIL sharpened + lexical max-fused). Promotion gated
  on measured F1 via `ml/evaluation/eval_backends.py`; degrades to lexical and tags
  `clf:lexical_fallback`.
- `threat.py` — weighted multi-signal fusion producing score + ranked drivers.
- `coercion.py` — coercion index computed on **victim** utterances only,
  independent of the stage classifier.
- `twin.py` — Digital Twin: Markov transition model forecasting next stage,
  ETA, and time-to-payment.
- `passport.py` — Identity Trust Passport: mechanical PASS/FAIL/UNKNOWN checks
  against what CBI/Customs actually do, each with a citation.
- `spoofing.py` — caller-ID/authority mismatch, VoIP, international routing.
- `scripts.py` + `features/script_templates.py` — dense + lexical similarity to
  known scam scripts, gated at 0.45.
- `ocr.py` — pluggable OCR (tesseract default, easyocr optional) + QR via zbar.
- `upi.py`, `report.py`, `report_pdf.py` — UPI checks, evidence package, MHA/
  cybercrime-compatible PDF via reportlab.
- `features/` — behaviour, callflow, emotion, linguistic, video, spoofing extractors.

**Input processing (`ingest/`)** — Whisper ASR, pyannote diarization, language
detection (Hindi/Hinglish/English), normalisation, metadata, pipeline.

**Intelligence (`intel/`)** — NetworkX fraud knowledge graph, community
detection, cluster risk scoring, centrality, link prediction, entity extraction
(UPI/phone/bank/email/website/locations), India geospatial points, per-cluster
investigation reports.

**Citizen shield (`shield/`)** — artefact verification, guidance, helplines,
evidence vault with tokenised access, auto-generated cybercrime complaint (+PDF).

**RAG (`rag/`)** — dense retrieval via sentence-transformers with deterministic
TF-IDF/BM25 fallback; 31 chunks over 4 curated knowledge docs (RBI advisories,
scam playbooks, scam variants, UPI safety). Returns citations.

**LLM (`llm.py`)** — Gemini-backed **explanations only, never scoring**. Optional;
degrades silently-but-tagged.

**Platform** — `auth.py` (pbkdf2 + HS256, stdlib only), `orgs.py` (multi-tenant),
`models_db.py`, `db.py` (SQLAlchemy; in-memory default, `DATABASE_URL` to
persist), `audit.py` (append-only), `security.py` (rate limit + security headers).

**API surface** — 50 routes across analyze / session / auth / reports / intel /
shield / orgs, plus a 4 Hz WebSocket pushing `StateFrame` snapshots.

### 2.2 Contract — `schema/`

A genuine schema-first contract: `models.py` (Pydantic) and `types.ts` are kept
in lockstep, verified by `check_contract.py`, synced to the frontend by
`scripts/sync-contract.sh`. `StateFrame` = idempotent snapshot; `Event` = one-shot
edge. **This is a real architectural asset and must survive the pivot.**

### 2.3 Frontend — `apps/web/`, React 18 + TypeScript + Vite

17 routes: landing, login, citizen home, analyze, live protection, reports,
learn, emergency, profile, dashboard, analyst console, guardian, analyzer,
intel, model card, admin. Leaflet scam map, three.js threat field, GSAP motion,
command palette, light+dark tokens, route boundaries, auth context.
**The frontend is a pure renderer** — no threat maths in React; every number is
a contract field.

### 2.4 ML — `ml/`

- `aegis/` (was `presage/`) — taxonomy, schema, seeds, entities, Hinglish
  handling, generation LLM backends. The shared domain vocabulary.
- `rssie/` (was `kavach/`) — multi-head RSSIE model package (MuRIL encoder →
  sequence head → scam/type/stage/transfer-risk heads). Separate from the
  single-head classifier currently served.
- `train.py`, `build_dataset.py`, `generate_calls.py`, `paraphrase.py`,
  `validate_corpus.py`, `eval_backends.py` — a reproducible corpus + training
  pipeline.
- `data/` — 1,692 synthetic calls, split train/val/test with a fitted
  transition matrix.
- `artifacts/` — 3.5 GB of checkpoints including the promoted stage classifier.

### 2.5 Engineering practice already in place

- 84 passing tests, CI on py3.11 + py3.12.
- **Explicit degradation**: every optional capability has a fallback that still
  answers and records a tag in `degraded`. No network call in the request path.
- **False-positive discipline**: BENIGN is the broadest class by design; soft
  signals stay in weighted fusion so legitimate metadata cannot manufacture a scam.
- Promotion gate: a model ships only if measured F1 beats the incumbent.

---

## 3. What Does Not Exist (the real work)

Ordered by architectural blast radius. Each maps to a phase in `TASKS.md`.

| # | Missing | Why it matters | Phase |
|---|---|---|---|
| 1 | **Agent abstraction** — there is no `Agent` type, no `AgentResult`, no registry | Everything in the master spec is phrased in agents; today it is a linear pipeline | 1 |
| 2 | **LangGraph orchestration** — no graph, no conditional routing, no per-node retry/timeout | Required for branching, parallel fan-out, reproducible traces | 1 |
| 3 | **`InvestigationState`** — the shared state object from master §24 | The contract every agent reads/writes | 1 |
| 4 | **Input Classification Agent** — nothing routes by evidence type | "Upload anything" is impossible without it | 1 |
| 5 | **URL / domain investigation** — no WHOIS, DNS, SSL, redirect, typosquat, brand-impersonation checks | The single most common phishing evidence type | 2 |
| 6 | **Email agent** — no header/SPF/DKIM/DMARC analysis | Email is a named input in master §2 | 2 |
| 7 | **APK static analysis** — nothing | Named in master §11; high novelty for Indian remote-access scams | 2 |
| 8 | **Image forensics / vision** — OCR exists, but no EXIF, ELA, CLIP, logo/brand matching | Master §9 | 2 |
| 9 | **Threat intelligence agent** — no external feeds, no provenance record | Master §12; every indicator needs source+timestamp+confidence | 2 |
| 10 | **Neo4j** — graph is in-process NetworkX, dies with the process | Cross-case relationship discovery at scale; a headline research claim | 3 |
| 11 | **Qdrant** — vector store is in-house | Semantic investigation memory | 3 |
| 12 | **PostgreSQL** — SQLite only | Concurrent writes, real persistence, JSONB evidence | 3 |
| 13 | **Cross-case memory** — "seen in 3 previous investigations" is not implemented | Master §15; the compounding-value story | 3 |
| 14 | **ML risk engine** — scoring is hand-weighted, no XGBoost/LightGBM, no calibration | Master §16; without it there is no ML baseline to compare against | 4 |
| 15 | **SHAP / feature attribution** | Master §18 wants evidence with confidence and source | 4 |
| 16 | **Streaming STT** — Whisper is batch | Master §20 real-time pipeline | 6 |
| 17 | **WebRTC protected call (Mode A)** | Master §19; currently mic-only in-browser | 6 |
| 18 | **SMS ingestion** | Named input, no channel exists | 6 |
| 19 | **Async job system** — no Redis, no Celery; everything is request-path | APK/URL/video analysis cannot run synchronously | 1/10 |
| 20 | **Agent trace UI + graph explorer** — no React Flow, no Cytoscape | Master §22; makes the architecture legible to examiners | 7 |
| 21 | **Multimodal dataset** — corpus is call-transcripts only | Master §26; the paper's novelty depends on it | 8 |
| 22 | **Research harness** — no baselines, no ablations, no latency benchmark | Master §28/29; without it there is no paper | 9 |
| ~~23~~ | ~~Docker / deployment~~ — ✅ dev stack done 2026-08-23 (colima + `infra/compose/dev.yml`). Production images remain | 10.3 |

---

## 4. Known defects and risks carried over

| Severity | Item | Action |
|---|---|---|
| ✅ Resolved | ~~Python 3.9~~ — migrated to **3.12.14** on 2026-08-23 (task 0.2). torch 2.13, transformers 4.57, numpy 2.5, networkx 3.6. Classifier predictions verified bit-identical across the upgrade. | Done |
| 🟡 Medium | **English scam scoring is borderline on short inputs** — the aggregate score rewards accumulated pressure across many turns. Hindi/Hinglish is strong. | Phase 4/8 — retrain + calibrate |
| 🟡 Medium | **Full-corpus retrain never run** (~2 h CPU). Current checkpoint is good but trained on a subset. | Phase 8 |
| 🟡 Medium | `ml/artifacts/` is **3.5 GB inside the repo tree**. Not viable long-term. | Phase 0.5 — DVC or object storage |
| 🟢 Low | **Gemini API key in local `.env`** — verified **never committed**; `.env` is untracked and gitignored, and `git log --all -- .env` plus a history grep for `AIza` are both empty. Still rotate before any public demo. | Phase 0.5 |
| 🟢 Low | `on_event` startup hooks are deprecated in current FastAPI. | Phase 0.2 |
| 🟢 Low | Dense *script* matching measured **worse** than lexical on Hinglish false-positive discipline; kept behind `AEGIS_DENSE_SCRIPTS`. | Keep flagged; revisit with more data |
| 🟢 Low | No frontend tests. | Phase 7 |

### New risks introduced by the AegisAI scope

| Severity | Risk | Mitigation |
|---|---|---|
| 🔴 High | **SSRF via the URL investigation agent.** It fetches attacker-supplied URLs. Naive implementation lets a user pivot into the internal network or cloud metadata (169.254.169.254). | Egress allowlist, DNS re-resolution pinning, block private/link-local ranges, dedicated network namespace, no redirects to private IPs. Phase 2.3 — non-negotiable. |
| 🔴 High | **APK analysis = handling live malware.** | Static only, in a container with no network and a read-only mount; never execute. Phase 2.8. |
| 🟠 Med | **Live-call legality and consent.** Two-party consent varies; covert recording is out of scope by design. | Explicit consent gate, visible recording indicator, configurable retention, deletable recordings. Master §32. |
| 🟠 Med | **Threat-intel rate limits / cost** could make the request path fail. | Cache-first with TTL, async enrichment, degrade-and-tag. Never block a verdict on an external call. |
| 🟠 Med | **Scope is very large for one capstone.** | Phased plan with a defensible MVP at the end of Phase 2; every later phase is additive, not load-bearing. |

---

## 5. What carries forward, unchanged

These are architectural invariants inherited from KAVACH. They are *why* the
codebase is trustworthy, and they apply to every new agent:

1. **`schema/` is the single source of truth.** Pydantic and TypeScript change
   in the same commit; `check_contract.py` proves it.
2. **The frontend is a pure renderer.** No thresholds or scoring in React.
3. **Degradation is explicit.** Every path has a fallback that still answers and
   records a tag. The UI shows degradation rather than a confident number built
   on nothing.
4. **False positives are a first-class failure.** A signal becomes dispositive
   only when genuinely conclusive.
5. **The LLM explains; it never scores.** Extended for AegisAI: the LLM may also
   *extract structured fields* and *rank*, but the risk number comes from the
   ML model + rules + graph.
6. **No network call in the request path** without a cached fallback.
