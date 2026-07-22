# KAVACH — AI for Digital Public Safety

[![CI](https://github.com/dkadchha2845/presage/actions/workflows/ci.yml/badge.svg)](https://github.com/dkadchha2845/presage/actions/workflows/ci.yml)
[![Tests](https://img.shields.io/badge/tests-84%20passing-22C55E)](https://github.com/dkadchha2845/presage/actions)
[![PS6](https://img.shields.io/badge/ET%20AI%20Hackathon%202026-PS%206-1A6BFF)](./docs/SUBMISSION_DOCUMENT.md)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

> **Real-time AI shield against Digital Arrest Scams and Voice Fraud.**  
> KAVACH intervenes *before* the money moves — coaching citizens, detecting the 7-step scam arc, and generating court-admissible intelligence for law enforcement.

> Not a substitute for reporting fraud on **1930** or at **cybercrime.gov.in**.

---

## 📋 Hackathon Submission — ET AI Hackathon 2026

| Field | Value |
|---|---|
| **Problem Statement** | PS 6 — AI for Digital Public Safety: Defeating Counterfeiting, Fraud & Digital Arrest Scams |
| **Presentation** | [`docs/PRESENTATION.html`](./docs/PRESENTATION.html) — open in any browser |
| **Detailed Document** | [`docs/SUBMISSION_DOCUMENT.md`](./docs/SUBMISSION_DOCUMENT.md) |
| **Demo Script** | [`attached_assets/demo_script_1784735112763.md`](./attached_assets/demo_script_1784735112763.md) |
| **GitHub** | https://github.com/dkadchha2845/presage |
| **Status** | 84 tests passing · CI green · Ships on clean clone (no GPU, no key, no network) |

### Judging Criteria

| Criterion | Weight | KAVACH |
|---|---|---|
| Innovation | 25% | First real-time 7-stage psychological arc classifier. Deterministic + LLM hybrid. Digital Twin forecasts time-to-payment. |
| Business Impact | 25% | Directly addresses ₹1,776 crore / 9-month loss. Scales to 1.2B citizens via telecom integration. |
| Technical Excellence | 20% | 84 tests. Schema-first contract. Reproducible ML. SIGSEGV fix. CI on py3.9 + py3.12. |
| Scalability | 15% | SQLite → Postgres in one env var. NetworkX → Neo4j (same interface). Multi-tenant RBAC ready. |
| User Experience | 15% | GSAP + WebGL landing. Command palette. ARIA-compliant maps. Mock stream replay. Light + dark. |

---

## The Problem

India registered **1.14 million cybercrime complaints** in 2023 (+60% YoY). Digital arrest scams defrauded citizens of **₹1,776 crore** in just the first nine months of 2024 (MHA data).

A digital arrest scam is not a single lie you can catch with a keyword. It is a **seven-step psychological arc** run by a practised operator over 20–90 minutes:

| # | Stage | What the caller is doing |
|---|---|---|
| 1 | `GREETING` | Establishing a normal, calm frame |
| 2 | `AUTHORITY_CLAIM` | "I'm Inspector Sharma, CBI, badge 4471" |
| 3 | `FEAR_INDUCTION` | "A parcel in your name contained narcotics. Non-bailable." |
| 4 | `ISOLATION` | "Do not disconnect. Do not tell your family. This is confidential." |
| 5 | `VERIFICATION_DEMAND` | "Confirm your Aadhaar, your account balance, the OTP" |
| 6 | `PAYMENT_SETUP` | "Transfer to this supervised account. It's fully refundable." |
| 7 | `PAYMENT_EXECUTION` | The money moves |

Plus `BENIGN` — a real bank calling about a real transaction, using **the same vocabulary**. The eighth class is the hardest, and is the broadest class in the taxonomy by design (false positive discipline).

By the time a human notices something is wrong, they are usually at step 5 or 6 — well past the point where the fear is doing the work. **The KAVACH intervention window is steps 2–5 — approximately 10–15 minutes to act.**

---

## Three Modules

### Module 1 — RSSIE: Real-time Scam Session Intelligence Engine

The citizen-facing live protection cockpit.

- **Whisper ASR + Pyannote diarization** — local-only transcription, PII never leaves the backend
- **8-class stage classifier** — MuRIL checkpoint with lexical fallback, promotion gate on measured F1
- **Coercion Indexer** — analyses only the victim's utterances for distress, independent of the classifier
- **Identity Passport** — mechanical rule checks against what CBI/Customs actually do (PASS/FAIL/UNKNOWN + citation)
- **Script Similarity** — dense + lexical match against known scam scripts, gated at 0.45
- **Number Spoofing Intelligence** — Caller-ID/authority mismatch, VoIP, international routing, call frequency
- **Digital Twin** — Markov-chain model: forecasts "minutes until payment execution"
- **4 Hz WebSocket** — StateFrame snapshots pushed to the UI in real time
- **Coach library** — 14 human-reviewed lines delivered verbatim. LLM may rank, never writes.
- **Evidence PDF** — MHA/cybercrime-compatible, reproducible, court-admissible

### Module 2 — FIGAE: Fraud Intelligence Graph & Analytics Engine

The law enforcement intelligence dashboard.

- **NetworkX fraud knowledge graph** — nodes: phone numbers, UPI IDs, bank accounts, device fingerprints
- **Community detection** — finds coordinated campaigns. 9 clusters from 114 seeded cases.
- **Cluster risk scoring** — LOW → CRITICAL, dynamic. Centrality metrics identify kingpin nodes.
- **Link prediction** — surfaces hidden connections between unrelated fraud reports
- **India geospatial hotspot map** — react-leaflet with India gazetteer. Inter-district intelligence sharing.
- **AI investigation reports** — per-cluster, auto-generated. FC-001 reproduces the FC-021 exemplar.
- **Entity extraction** — auto-extracts UPI VPAs, phone numbers, bank accounts from transcripts
- **Multi-tenant RBAC** — Owner / Admin / Analyst / Viewer. Append-only audit log.

### Module 3 — CFSRP: Citizen Fraud Shield & Response Platform

The public-facing self-service layer — no login required.

- **Threat verification** — fuses Module 1 scoring + Module 2 cluster lookup
- **Stage-aware coaching** — 14 verbatim human-reviewed coach lines
- **Emergency response** — helpline directory + emergency checklist
- **Evidence vault** — token-addressed CitizenReport (share with police without revealing identity)
- **Complaint generator** — structured PDF for 1930/NCRB submission
- **Awareness feed** — real-time scam alerts, publicly accessible

---

## How It Works

```
utterance (typed / ASR / OCR)
    │
    ├─► classifier.py   8-way stage distribution (never a bare argmax)
    │                   MuRIL checkpoint, or lexical fallback
    │
    ├─► coercion.py     victim stress — VICTIM's side only, independent
    │
    ├─► passport.py     mechanical identity checks vs. institutional SOPs
    │                   PASS / FAIL / UNKNOWN + citation
    │
    ├─► scripts.py      dense + lexical scam-script similarity (0–1)
    │
    └─► threat.py       fuse() weights four signals into one score:
                            0.40 × stage probability
                            0.25 × coercion pressure
                            0.20 × identity failure
                            0.15 × script similarity
                        + ratchet: fast up (×1.5) · slow down (×0.7)
                        + named drivers returned (not just a number)
                            │
                            ▼
                   twin.py  fitted transition matrix
                            ⇒ "≈4m20s until PAYMENT_EXECUTION"
                            │
                            ▼
                   session.py  StateFrame snapshot + Events
                            │
              ┌─────────────┼──────────────┐
              ▼             ▼              ▼
        score ≥ 70    score ≥ 55    coach line pulled verbatim
        guardian      hold payment  from coach_library.json
```

---

## Architecture

```
┌─ apps/web ──────────┐   WebSocket + REST   ┌─ services/api ──────────────────────┐
│ React 18 · TypeScript│◄───────────────────►│ FastAPI · Python 3.9–3.12           │
│ home · dashboard    │                      │                                     │
│ console · analyzer  │                      │ engine/  classifier, threat, twin,  │
│ guardian · knowledge│                      │          coercion, passport, upi,   │
│ intel · shield      │                      │          spoofing, scripts, report  │
│                     │                      │                                     │
│ GSAP · Three.js     │                      │ rag/     BM25 + dense · KB (31 chunks)│
│ react-leaflet       │                      │ intel/   NetworkX graph · geo        │
└─────────────────────┘                      │ shield/  citizen-facing public API  │
           ▲                                 │ auth/    pbkdf2 + HS256 (stdlib)    │
           │ contract                        │ db/      SQLite default → Postgres  │
    schema/types.ts ◄── check_contract.py ──►schema/models.py                     │
                                             └─────────────────────────────────────┘
                                                          ▲
                                         ml/  corpus → train.py → artifacts/
```

`schema/` is the single source of truth. `check_contract.py` fails the build if Python enums and TypeScript unions drift apart.

---

## Quick Start

**Prerequisites:** Python 3.9+, Node 18+. No GPU, no API key, no network at runtime.

```bash
git clone https://github.com/dkadchha2845/presage.git
cd presage
```

### 1. Backend — port 8000

```bash
python3 -m venv .venv
.venv/bin/pip install -r services/api/requirements.txt
.venv/bin/uvicorn services.api.main:app --reload --port 8000
```

### 2. Frontend — port 5173

```bash
npm install --prefix apps/web
npm run dev --prefix apps/web
# → http://localhost:5173
```

### 3. Verify

```bash
curl http://localhost:8000/api/health
# All systems live — or honest degraded status per component
```

### 4. Optional: Enable Gemini explanations

```bash
cp .env.example .env
# Set GEMINI_API_KEY= in .env, then restart the backend
```

The web app renders from a mock stream if the API is down. The API answers without the web app. Neither needs the other to start.

---

## Presentation & Demo

| Artefact | How to use |
|---|---|
| **Presentation** (`docs/PRESENTATION.html`) | Open in any browser. Arrow keys or buttons to navigate. Press `F` for fullscreen. 11 slides. |
| **Detailed document** (`docs/SUBMISSION_DOCUMENT.md`) | Full technical write-up, metrics, deliverables checklist |
| **Demo script** (`attached_assets/demo_script_1784735112763.md`) | 3–4 minute judge demo walkthrough |
| **Architecture diagrams** (`attached_assets/architecture_1784735112762.md`) | Mermaid source for all diagrams |

---

## What Each Screen Does

| Route | Screen | Who |
|---|---|---|
| `/` | Landing — WebGL hero + GSAP entrance | All |
| `/login` | Login — 3D tilt, seeded role roster | All |
| `/dashboard` | System health, active sessions, stats | Analyst+ |
| `/console` | Live Protection cockpit (Threat Meter + Coach) | Citizen / Analyst |
| `/guardian` | Evidence vault — save cases, export PDF | Analyst+ |
| `/analyzer` | Stateless single-utterance analysis + image OCR | Analyst+ |
| `/knowledge` | RAG knowledge assistant (cited corpus answers) | Analyst+ |
| `/intel` | Fraud graph + India scam map + cluster list | Analyst+ |
| `/shield` | Citizen Fraud Shield — public, no login | Citizen |
| `/model` | ML model card, backend comparison | Analyst+ |
| `/cases` | Case book — saved evidence, audit log | Admin+ |

---

## API Reference

| Endpoint | Method | Function |
|---|---|---|
| `/api/health` | GET | System status — live vs degraded per component |
| `/api/analyze` | POST | Stateless single-utterance analysis |
| `/api/analyze/image` | POST | OCR + threat analysis of image uploads |
| `/api/analyze/knowledge/ask` | POST | RAG knowledge assistant (cited answers) |
| `/api/session/start` | POST | Start a live session |
| `/api/session/{id}/frame` | WS | 4 Hz live StateFrame stream |
| `/api/session/{id}/push` | POST | Push an utterance to a live session |
| `/api/session/{id}/report` | GET | JSON evidence package |
| `/api/session/{id}/report.pdf` | GET | PDF evidence package (court-admissible) |
| `/api/intel/graph` | GET | Fraud graph nodes + edges |
| `/api/intel/clusters` | GET | Campaign cluster list with risk scores |
| `/api/intel/map` | GET | Geospatial hotspot data |
| `/api/shield/verify` | POST | Citizen threat verification (public) |
| `/api/shield/coach` | GET | Stage-aware coaching lines (public) |
| `/api/cases` | GET/POST | Case book (auth required) |
| `/api/auth/login` | POST | Authenticate, receive HS256 token |

---

## Project Layout

```
presage/
├── apps/web/              React 18 + TypeScript frontend
│   └── src/
│       ├── pages/         Route-level page components
│       ├── components/    Shared UI components
│       └── hooks/         useLiveSession, useHealth, useStreamPlayer
│
├── services/api/          FastAPI backend
│   ├── engine/            Core scoring engine
│   │   ├── classifier.py  Stage classifier (MuRIL + lexical)
│   │   ├── threat.py      4-signal weighted fusion
│   │   ├── twin.py        Digital Twin (time-to-payment forecast)
│   │   ├── coercion.py    Victim-side stress index
│   │   ├── passport.py    Identity verification (PASS/FAIL/UNKNOWN)
│   │   ├── scripts.py     Scam-script similarity
│   │   ├── spoofing.py    Number spoofing intelligence
│   │   ├── report.py      Evidence package (JSON)
│   │   └── report_pdf.py  Evidence package (PDF)
│   ├── intel/             Module 2 — FIGAE fraud graph
│   ├── shield/            Module 3 — CFSRP citizen platform
│   ├── rag/               BM25 + dense retrieval + coach library
│   ├── routes/            FastAPI routers (17 endpoints)
│   ├── auth.py            pbkdf2 + HS256 auth
│   ├── db.py              SQLAlchemy (SQLite default / Postgres)
│   ├── security.py        Rate limiter + CSP headers
│   └── config.py          Settings via env vars
│
├── schema/                Single source of truth
│   ├── models.py          Pydantic enums (Python)
│   ├── types.ts           TypeScript unions
│   ├── check_contract.py  Fails build on Python↔TS drift
│   └── mock-stream.json   24 StateFrames for offline UI
│
├── ml/                    ML training pipeline
│   ├── generate_calls.py  LLM-generated scam call corpus
│   ├── build_dataset.py   Dataset builder + transition matrix
│   ├── train.py           MuRIL fine-tune
│   └── eval_backends.py   Measured backend comparison
│
├── docs/
│   ├── PRESENTATION.html       Hackathon presentation (11 slides)
│   ├── SUBMISSION_DOCUMENT.md  Detailed submission document
│   └── IMPLEMENTATION-REPORT.md Full implementation report
│
├── .github/workflows/ci.yml    CI (py3.9 + py3.12 + frontend)
├── .env.example                Environment template
└── STATUS.md                   Running build status
```

---

## Design Decisions Worth Knowing

### 1. Deterministic Scoring First

The core threat scoring is done via classic NLP, regex, and behavioural heuristics — not LLMs. This ensures results are fast, defensible, reproducible, and cannot hallucinate a fake scam or clear a real one.

### 2. LLM as Explainer, Never Decider

Gemini Flash is used only at the very end of the pipeline to translate deterministic findings into plain, empathetic language for the citizen. It never touches the score or the coach lines.

### 3. Local-First Audio and Image Processing

Whisper and Tesseract run locally on the backend. Sensitive audio and documents are never shipped to third-party APIs for transcription.

### 4. BENIGN is the Hardest Class

A real bank calling about a real transaction uses the same vocabulary as a scammer impersonating a bank. The BENIGN class is intentionally the largest and broadest in training data — false positive discipline is structural, not a post-hoc threshold.

### 5. Pre-warming Models

Heavy ML models are loaded into memory on API startup (`@app.on_event("startup")`), ensuring that the first request during a real emergency has zero cold-start latency.

### 6. Coach Lines are Human-Reviewed and Verbatim

The LLM may rank or reword explanations. It never writes the coach line. The 14 lines in `coach_library.json` are human-reviewed and delivered verbatim — because in a crisis, clear, tested language matters more than creative generation.

---

## Scoring Engine

```python
ThreatScore = (
    0.40 × stage_probability     # What scam stage is this?
  + 0.25 × coercion_index        # How scared is the victim?
  + 0.20 × identity_fail_score   # Did the caller fail institutional rules?
  + 0.15 × script_similarity     # Does this match known scam scripts?
)
# Ratchet: rises fast (×1.5), falls slowly (×0.7)
# Ensures a brief pause doesn't reset an active alert
```

Thresholds (all in `engine/session.py`, one screen):

| Level | Score | Action |
|---|---|---|
| CALM | 0–30 | Monitor |
| WATCH | 31–50 | Advisory |
| WARNING | 51–70 | Coach panel |
| CRITICAL | 71–100 | Full guardian mode |
| Payment Hold | 55+ | Block payment flow |

---

## Training Pipeline

Full offline chain, all steps reproducible:

```bash
# 1. Generate synthetic scam call corpus
.venv/bin/python ml/generate_calls.py

# 2. Augment with paraphrases
.venv/bin/python ml/paraphrase.py

# 3. Build dataset + Digital Twin transition matrix
.venv/bin/python ml/build_dataset.py

# 4. Fine-tune MuRIL
.venv/bin/python ml/train.py

# 5. Compare backends — promotion gate on measured F1
.venv/bin/python ml/eval_backends.py
```

Corpus (338 calls) is committed. Checkpoint is regenerable, not lost.

Split: **leave-archetypes-out by call** — the strict validation that caught memorisation.

---

## Tests

```bash
# All tests (84 passing)
.venv/bin/python -m pytest services/api/tests -q

# Contract check (Python ↔ TypeScript enum sync)
.venv/bin/python schema/check_contract.py

# Frontend typecheck + build
npm run typecheck --prefix apps/web
npm run build --prefix apps/web
```

| Test suite | Count | Coverage |
|---|---|---|
| `test_verdicts.py` | 16 | Stage classifier regression |
| `test_intel.py` | 10 | Fraud graph + community detection |
| `test_shield.py` | 9 | Citizen shield flows |
| `test_security.py` | 5 | Rate limiter, CSP, login backoff |
| `test_orgs.py` | 3 | Multi-tenant org isolation |
| `test_auth.py` | — | Auth + RBAC |
| `test_casebook.py` | — | Evidence save + audit log |
| `test_ocr.py` | — | Image analysis |
| `test_report.py` | — | PDF generation |
| `test_scripts.py` | — | Script similarity |
| `test_spoofing.py` | — | Number spoofing |
| **Total** | **84** | **All passing** |

---

## Working Together on This Repo

### Before You Push

```bash
.venv/bin/python -m pytest services/api/tests -q
.venv/bin/python schema/check_contract.py
npm run typecheck --prefix apps/web
```

### Don't Commit

- `.env` (real keys)
- `ml/artifacts/*.pt` weights (~3.6 GB). Commit `backend_comparison.json` and `metrics.json` instead and ask collaborators to retrain.
- `node_modules/`, `.venv/`

### Handing Over

Update `STATUS.md` when you finish something. It is the running record — the next person shouldn't have to reverse-engineer the diff.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: pydantic` | Used system `python3` | Use `.venv/bin/python schema/check_contract.py` |
| `ModuleNotFoundError: services` | Ran uvicorn from subdirectory | Run from repo root |
| Web loads but top bar says API offline | API not running / CORS | Start API on port 8000 — CORS allows 5173 only |
| `degraded: ["rag:lexical", "clf:lexical_fallback"]` | Normal — lexical won the promotion gate | Optional: install dense extras from `services/api/requirements.txt` |
| `Address already in use` on 8000 | Older uvicorn still running | `lsof -ti:8000 \| xargs kill` |
| Training loss stuck at 2.079 (`ln 8`) | Apple MPS backend | Train on CPU — it's the default for this reason |
| `npm run dev` — Vite can't resolve `@/…` | Ran npm from repo root | Use `--prefix apps/web`, or `cd apps/web` first |
| Gemini explanations not working | Retired model default | Set `GEMINI_API_KEY` in `.env` and ensure `PRESAGE_LLM=gemini` |

---

## Not in This Build

- **Live audio:** WebSocket streaming is plumbed but microphone access needs browser permission flow (demo uses pre-recorded audio).
- **OCR is optional:** Requires `tesseract` binary installed; without it, `image` path returns `ocr:unavailable` and asks you to type the text.
- **No real notifications:** Push notification wiring is pending.
- **No payment rails:** Evidence vault uses token-based sharing, not payment.
- **Synthetic training only:** Real-world transfer is unmeasured. The leave-archetypes-out split is honest about generalisation.
- **No persistence by default:** Sessions live in memory and die with the process. Set `DATABASE_URL` for persistence.
- **MuRIL retrain:** Full 2-hour retrain is pending — lexical currently wins the promotion gate on this corpus.

---

*KAVACH — Every citizen's device is now a shield.*  
*Not a substitute for reporting fraud on 1930 or at cybercrime.gov.in.*
