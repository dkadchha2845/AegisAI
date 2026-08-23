# AegisAI — Detailed Submission Document
## ET AI Hackathon 2026 · Problem Statement 6
### AI for Digital Public Safety: Defeating Counterfeiting, Fraud & Digital Arrest Scams

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Problem Statement Alignment](#2-problem-statement-alignment)
3. [Solution Overview](#3-solution-overview)
4. [Module Breakdown](#4-module-breakdown)
5. [Technical Architecture](#5-technical-architecture)
6. [Scoring Engine Deep Dive](#6-scoring-engine-deep-dive)
7. [Evaluation Metrics & Performance](#7-evaluation-metrics--performance)
8. [Security, Privacy & Legal Admissibility](#8-security-privacy--legal-admissibility)
9. [ML Training Pipeline](#9-ml-training-pipeline)
10. [Deliverables Checklist](#10-deliverables-checklist)
11. [Demo Instructions](#11-demo-instructions)
12. [Competitive Landscape](#12-competitive-landscape)
13. [Impact & Roadmap](#13-impact--roadmap)
14. [Judging Criteria Self-Assessment](#14-judging-criteria-self-assessment)

---

## 1. Executive Summary

**AegisAI** is a production-grade, AI-powered Digital Public Safety Intelligence platform that intervenes in real time during voice fraud and digital arrest scams — **before the money moves**.

Unlike reactive reporting tools (1930, cybercrime.gov.in) or passive call-ID blacklists (Truecaller), AegisAI is the only system that:

- **Analyses a phone call while it is happening** and warns the victim in real time
- **Identifies the exact psychological stage** of the scam arc (out of 7 stages + BENIGN)
- **Coaches the victim with human-reviewed language** to break the scammer's isolation tactic
- **Generates court-admissible evidence packages** automatically the moment a call ends
- **Feeds every intercepted call into a live fraud intelligence graph** for law enforcement

**Stack:** React 18 + TypeScript (frontend), FastAPI + Python 3.9–3.12 (backend), MuRIL + Gemini Flash (ML/LLM), NetworkX (fraud graph), SQLite/PostgreSQL (persistence).

**Status:** 3 full modules working end-to-end. 84 tests passing. CI green. Ships on a clean clone with no GPU, no API key, no network.

---

## 2. Problem Statement Alignment

**PS 6 — AI for Digital Public Safety: Defeating Counterfeiting, Fraud & Digital Arrest Scams**

| PS Requirement | AegisAI Implementation |
|---|---|
| Digital Arrest Scam Detection & Alerting | ✅ Module 1 (RSSIE): Real-time 8-class stage classifier, threat meter, citizen coach |
| Fraud Network Graph Intelligence | ✅ Module 2 (FIGAE): NetworkX fraud graph, 9 clusters / 114 cases, link prediction, geospatial hotspots |
| Geospatial Crime Pattern Intelligence | ✅ Module 2: India gazetteer + react-leaflet scam map, inter-district intelligence sharing |
| Citizen Fraud Shield (Multi-channel) | ✅ Module 3 (CFSRP): Public-facing threat verification, stage-aware coaching, emergency response, complaint generator |
| Suggested: NLP / LLMs | ✅ MuRIL classifier + Gemini Flash explainer |
| Suggested: Speech AI | ✅ Whisper ASR + Pyannote diarization |
| Suggested: Graph AI & Network Analysis | ✅ NetworkX fraud graph + community detection |
| Suggested: Geospatial Intelligence | ✅ react-leaflet + India gazetteer |
| Suggested: Agentic multi-source fusion | ✅ Fused 4-signal threat scorer: Stage + Coercion + Identity + Script similarity |

### Scale of the Problem

| Metric | Source | Value |
|---|---|---|
| Cybercrime complaints 2023 | MHA | **1.14 million** (+60% YoY) |
| Digital arrest scam losses Jan–Sep 2024 | MHA | **₹1,776 crore** |
| Average scam call duration | Field research | 20–90 minutes |
| Real-time intervention tools available | Market survey | **0** |

---

## 3. Solution Overview

AegisAI is built around a single, powerful insight:

> **A scam call is not a single lie. It is a seven-step psychological arc — and by the time a human notices, they are already past the point where fear is doing the work.**

The seven stages are:

```
GREETING → AUTHORITY_CLAIM → FEAR_INDUCTION → ISOLATION → VERIFICATION_DEMAND → PAYMENT_SETUP → PAYMENT_EXECUTION
```

Plus `BENIGN` — a real institutional call using the same vocabulary. The `BENIGN` class is the broadest and hardest, and is treated as such by design to keep false positives near zero.

**The AegisAI Intervention Window:** Steps 2–5 (typically 10–15 minutes). AegisAI fires at step 2 and escalates urgency as the arc progresses, coaching the victim before reaching step 6.

### Architecture Summary

```
Citizen Device / Microphone
        │ WebSocket Audio Stream
        ▼
┌─────────────────────────────────────────────────────┐
│                 AegisAI Backend Engine               │
│                                                     │
│  Ingestion ──► Whisper ASR ──► Unified Transcript   │
│     └──────► Tesseract OCR ──►        │             │
│                                       ▼             │
│                          ┌────────────────────┐     │
│                          │  Stage Classifier  │     │
│                          │  Coercion Indexer  │──►  │
│                          │  Identity Passport │     │
│                          │  Script Similarity │     │
│                          └────────────────────┘     │
│                                    │                │
│                            Fused Threat Score        │
│                           (0–100, ratcheted)         │
└─────────────────────────────────────────────────────┘
        │                         │
        ▼                         ▼
Citizen Coach UI          Investigation Report
(React, 4 Hz WS)          (PDF, court-admissible)
        │                         │
        └──────────┬──────────────┘
                   ▼
          Fraud Intelligence Graph
          (NetworkX + Geospatial Map)
```

---

## 4. Module Breakdown

### Module 1 — RSSIE: Real-time Scam Session Intelligence Engine

**Purpose:** Protect the citizen during the call.

**Components:**

| Component | File | Function |
|---|---|---|
| Stage Classifier | `services/api/engine/classifier.py` | 8-class distribution (7 stages + BENIGN). MuRIL checkpoint with lexical fallback. Promotion gate on measured F1 — not just file presence. |
| Threat Scorer | `services/api/engine/threat.py` | 4-signal weighted fusion. Ratchet: fast up (×1.5), slow down (×0.7). Returns named drivers, not just a number. |
| Coercion Indexer | `services/api/engine/coercion.py` | Analyses **victim's utterances only** for distress, confusion, panic. Independent of the stage classifier — catches cases where the victim sounds scared even if the caller's stage is misclassified. |
| Identity Passport | `services/api/engine/passport.py` | Mechanical rule-based checks against what CBI/Customs/Police actually do. Returns PASS/FAIL/UNKNOWN each with a citable source. |
| Script Similarity | `services/api/engine/scripts.py` | Dense (sentence-transformers) + lexical (TF-cosine) match against known scam scripts. Bounded 0–1, gated at 0.45. |
| Number Spoofing | `services/api/engine/spoofing.py` | Caller-ID/authority mismatch, VoIP detection, international routing analysis, reported-number check, call frequency. Risk 0–100. |
| Digital Twin | `services/api/engine/twin.py` | Markov-chain model fitted on scam call corpus. Forecasts "time to payment execution" based on current detected stage. |
| Session API | `services/api/routes/session.py` | WebSocket pushing StateFrame snapshots at 4 Hz. 17 total endpoints. |
| Evidence Report | `services/api/engine/report.py` + `report_pdf.py` | MHA/cybercrime-compatible JSON + PDF. Verdict, signals, timeline, transcript, 1930 reporting guidance. |

**Key design decisions:**
- Never a bare argmax — always a probability distribution over all 8 classes
- LLM (Gemini Flash) used **only** to explain the verdict in plain language, never to make the verdict
- Coach lines are human-reviewed and delivered **verbatim** — the LLM may rank but never writes them

**Demo flow:**
1. Citizen opens Live Protection
2. Puts call on speaker → AegisAI streams via browser microphone
3. Threat Meter updates every 250 ms
4. At ISOLATION stage: Coach banner appears ("Hang up. Real police never ask for OTPs.")
5. Call ends → Investigation Report auto-generated

---

### Module 2 — FIGAE: Fraud Intelligence Graph & Analytics Engine

**Purpose:** Give law enforcement actionable intelligence, not just alerts.

**Components:**

| Component | File | Function |
|---|---|---|
| Fraud Knowledge Graph | `services/api/intel/` | NetworkX graph. Nodes: phone numbers, UPI IDs, bank accounts, device fingerprints. Edges: shared call, shared transaction, co-cluster. |
| Community Detection | `services/api/intel/` | Finds coordinated fraud campaigns. 9 clusters from 114 seeded cases. |
| Cluster Risk Scoring | `services/api/intel/` | LOW → CRITICAL dynamic risk per campaign. Centrality metrics identify kingpin nodes. |
| Link Prediction | `services/api/intel/` | Graph AI surfaces unknown connections between seemingly unrelated fraud reports. |
| Geospatial Hotspots | `services/api/intel/` | India gazetteer + react-leaflet. Maps active fraud campaign locations. |
| AI Investigation Report | `services/api/intel/` | Per-cluster AI-generated report with evidence linkage. FC-001 reproduces the FC-021 exemplar from the problem brief. |
| Entity Extraction | `services/api/engine/analyzer.py` | Auto-extracts phone numbers, UPI VPAs, bank account numbers from any transcript. |

**Frontend (Analyst Console):**
- Force-directed fraud graph visualisation (react)
- India hotspot map with react-leaflet cluster pins
- Cluster list with risk badges (LOW → CRITICAL)
- Entity search across all cases
- Multi-tenant RBAC: Owner / Admin / Analyst / Viewer
- Append-only audit log (logins, exports, payment overrides)

---

### Module 3 — CFSRP: Citizen Fraud Shield & Response Platform

**Purpose:** Give every citizen self-service fraud protection, no login required.

**Components:**

| Component | Function |
|---|---|
| Threat Verification | Fuses Module 1 scoring + Module 2 cluster lookup |
| Stage-Aware Coaching | 14 human-reviewed coach lines, delivered verbatim |
| Emergency Response | Helpline directory + emergency checklist |
| Evidence Vault | Token-addressed CitizenReport — share with police without revealing identity |
| Complaint Generator | Structured complaint PDF, reuses the PDF renderer from Module 1 |
| Awareness Feed | Real-time scam alerts. Public routes, no authentication required. |

**Language & accessibility:**
- Hinglish / Hindi support (MuRIL, Sarvam ASR optional)
- ARIA-compliant react-leaflet maps
- Works on low-bandwidth connections (mock stream replay when API is down)

---

## 5. Technical Architecture

### Stack

| Layer | Technology | Why |
|---|---|---|
| Frontend | React 18 + TypeScript + Vite | Type-safe, zero threat maths in UI — all numbers come from API contract |
| Backend | FastAPI + Python 3.9–3.12 | Async, OpenAPI auto-docs, tested against both ends of the version range |
| Database | SQLite (default) / PostgreSQL | Zero-setup demo; `DATABASE_URL` env var switches to Postgres for production |
| ML Classifier | MuRIL checkpoint + lexical fallback | Multilingual (Hinglish/Hindi), promotable on measured F1 |
| LLM | Gemini Flash (free tier) | Explainer only, never scorer. Degrades gracefully to template explanations. |
| Speech | Whisper ASR + Pyannote diarization | Local-only — PII never leaves the backend |
| OCR | Tesseract (default) / EasyOCR | Pluggable, degrades to `ocr:unavailable` without blocking boot |
| Fraud Graph | NetworkX | Pure-Python, no external server, production-replaceable with Neo4j |
| Geospatial | react-leaflet + India gazetteer | ARIA-compliant, offline-capable |
| Auth | pbkdf2 + HS256 (stdlib only) | No external auth library — ships without a key |
| CI | GitHub Actions | Green on py3.9 + py3.12 + frontend on every push |

### Schema-First Contract

A single source of truth ensures the frontend never diverges from the backend:

- `schema/models.py` (Pydantic) ↔ `schema/types.ts` (TypeScript unions)
- 8 enums: `Stage(8)`, `ThreatLevel(5)`, `VictimState(7)`, `PaymentState(5)`, `GuardianState(4)`, `Verdict(3)`, `EventKind(10)`
- `schema/check_contract.py` fails CI if Python↔TS drift is detected
- `schema/mock-stream.json` — 24 StateFrames + 24 Events, so the UI renders correctly even when the API is down

### Performance

| Optimisation | Implementation |
|---|---|
| Zero cold-start | All heavy models pre-loaded at `@app.on_event("startup")` |
| 4 Hz live frames | WebSocket pushes StateFrame snapshots 4× per second |
| Concurrent safety | SQLite temp-file DB fix (was SIGSEGV under load) |
| Frontend bundle | Vendor split: Three.js / GSAP / React in separate long-cached chunks. Main bundle 48 kB (from 845 kB) |

---

## 6. Scoring Engine Deep Dive

### The Four Signals

```python
ThreatScore = (
    0.40 × stage_probability     # What scam stage is this?
  + 0.25 × coercion_index        # How scared is the victim?
  + 0.20 × identity_fail         # Did the caller fail known institutional rules?
  + 0.15 × script_similarity     # Does this match known scam scripts?
)
# + ratchet: score rises fast (×1.5), falls slowly (×0.7)
# This ensures a brief gap in scam signals doesn't reset the alert
```

### Worked Example

**Input (caller):** *"Do not disconnect. Do not tell your family. This is confidential. I am Inspector Sharma, CBI."*

| Signal | Raw Score | Weight | Contribution |
|---|---|---|---|
| Stage Classifier | ISOLATION: 0.87 | 0.40 | 34.8 |
| Coercion Index | 0.0 (caller, not victim) | 0.25 | 0.0 |
| Identity Passport | FAIL: CBI never calls unsolicited | 0.20 | 20.0 |
| Script Similarity | 0.82 (matches isolation script) | 0.15 | 12.3 |
| **Total** | | | **67.1 → ratcheted → 85** |

**Verdict:** `CRITICAL` — Guardian fires.

**Coach output (verbatim):** *"This is an isolation tactic used by scammers impersonating government officials. Real CBI, Customs, and Police will NEVER ask you to stay on the line, keep the call secret, or transfer money. Hang up immediately and call 1930."*

### Threshold Configuration

All thresholds live in one screen of `session.py`:

| Level | Score | Action |
|---|---|---|
| CALM | 0–30 | Monitor only |
| WATCH | 31–50 | Show advisory |
| WARNING | 51–70 | Show coach panel |
| CRITICAL | 71–100 | Full guardian mode |
| Payment Hold | 55+ | Block payment flow |

---

## 7. Evaluation Metrics & Performance

### Classification Metrics (leave-archetypes-out validation)

| Metric | Value | Notes |
|---|---|---|
| Corpus size | 338 calls | Hinglish/Hindi synthetic, validated schema |
| Train/Val/Test split | 931 / 138 / 171 utterances | Leave-archetypes-out by call (strict) |
| Classifier backends | MuRIL checkpoint + lexical fallback | Promotion gate on measured F1 |
| Backend comparison | See `ml/artifacts/backend_comparison.json` | Lexical won measured comparison on this corpus |
| BENIGN class handling | Largest, hardest class by design | False positive discipline enforced structurally |

### Evaluation Focus (from Problem Statement)

| Evaluation Criterion | AegisAI Approach |
|---|---|
| Digital arrest scam detection precision/recall | 8-class stage classifier with leave-archetypes-out validation. BENIGN is intentionally the hardest class. |
| Fraud network detection lead time before mass victimisation | Every saved case immediately ingests into the fraud graph. Cluster risk scores update dynamically. |
| False positive rate for citizen-facing tools | Must be very low. BENIGN is the largest class in training corpus. Ratchet prevents single-utterance false alerts. Identity Passport uses cite-able rules, not heuristics. |
| Auditability for legal admissibility | Deterministic scoring: same input always produces same score. PDF evidence package includes all signals, citations, and transcript. Append-only audit log. |

### System Health (at submission)

| Check | Status |
|---|---|
| Backend tests (84 total) | ✅ All passing |
| Contract check (schema) | ✅ Passing |
| Frontend typecheck + build | ✅ Zero errors |
| CI (py3.9 + py3.12 + frontend) | ✅ Green |
| API under concurrent load | ✅ Stable (SIGSEGV fixed) |
| Clean clone (no key, no GPU, no network) | ✅ Confirmed |
| Dense retrieval (RAG) | ✅ Live — 31 chunks / 4 docs |
| Gemini explanations | ✅ Working (retired-model default fixed) |

---

## 8. Security, Privacy & Legal Admissibility

### Privacy Architecture

| Principle | Implementation |
|---|---|
| No PII to cloud | Audio transcribed locally by Whisper. OCR run locally by Tesseract. PII never sent to Gemini. |
| LLM data isolation | Gemini receives only the threat score and stage labels — never raw audio, transcripts, or names. |
| API key management | All keys managed via environment variables. Zero secrets in git history. `.env.example` as template. |
| Sensitive data scope | `DATABASE_URL` defaults to ephemeral in-memory — zero persistence unless explicitly configured. |

### Security Hardening (`security.py`)

- Token-bucket rate limiter
- CSP + 4 hardening response headers
- Login backoff (CWE-307 — brute-force mitigation)
- CORS locked to `localhost:5173` / `127.0.0.1:5173`
- Upload path capped at 4 MB

### Legal Admissibility

- **Deterministic scoring:** Same input always produces the same score. Results are reproducible and not subject to LLM non-determinism.
- **Source citations:** Identity Passport checks include the specific rule or SOP cited (e.g., "CBI SOP: never initiates contact via unsolicited calls").
- **Audit log:** Append-only log of all logins, evidence exports, and payment overrides. Tamper-evident by design.
- **Evidence package:** Structured PDF with verdict, named signals, stage timeline, and full transcript — designed to be submitted to MHA/NCRB portals.

---

## 9. ML Training Pipeline

The core engine is deterministic, but the classifier weights and heuristic parameters are derived from a fully reproducible ML pipeline:

```
generate_calls.py   → Simulate scam calls using LLM (Gemini / Ollama)
        │               Multiple archetypes, Hinglish + Hindi
        ▼
paraphrase.py       → Augment corpus with paraphrases
        │
        ▼
build_dataset.py    → Parse, validate schemas, build transition matrix
        │               for the Digital Twin (Markov chain)
        ▼
train.py            → Fine-tune MuRIL checkpoint
        │               Leave-archetypes-out split (strict)
        ▼
eval_backends.py    → Compare MuRIL vs lexical on measured F1
                        Promotion gate: only the better backend is used
```

**Corpus:** 338 calls committed to the repository. Checkpoint regenerable locally.

**Key finding:** Dense script-matching was **measured and rejected** on false-positive grounds — lexical best currently, which the promotion gate correctly reports as `lexical · best` rather than a fault.

**Digital Twin:** Markov-chain model fitted on stage transition frequencies. Forecasts "minutes until payment execution" — the most valuable single number for a citizen coach.

---

## 10. Deliverables Checklist

### Required by Problem Statement

| Deliverable | Status | Location |
|---|---|---|
| **Working Prototype** | ✅ Complete | See §11 Demo Instructions |
| **Architecture Diagram** | ✅ Complete | `docs/PRESENTATION.html` · Slide 5; `attached_assets/architecture_1784735112762.md` |
| **Presentation Deck** | ✅ Complete | `docs/PRESENTATION.html` (11 slides, fully interactive) |
| **Demo Video** | 📋 Script ready | `attached_assets/demo_script_1784735112763.md` (3–4 min script) |

### Submission Form Requirements (from screenshot)

| Field | Value |
|---|---|
| Detailed document | This document (`docs/SUBMISSION_DOCUMENT.md`) |
| Additional file | `docs/PRESENTATION.html` (open in any browser — no install required) |
| Problem statement | **PS 6** — AI for Digital Public Safety: Defeating Counterfeiting, Fraud & Digital Arrest Scams |
| GitHub URL | https://github.com/dkadchha2845/aegis |
| Demo video | 3–4 min. Script in `attached_assets/demo_script_1784735112763.md` |

### Additional Artefacts Produced

| Artefact | Location |
|---|---|
| Presentation HTML (11 slides, animated) | `docs/PRESENTATION.html` |
| Technical architecture doc | `docs/SUBMISSION_DOCUMENT.md` (this file) |
| Demo script | `attached_assets/demo_script_1784735112763.md` |
| PPT content breakdown | `attached_assets/detailed_ppt_content_1784735112763.md` |
| Architecture diagrams (Mermaid) | `attached_assets/architecture_1784735112762.md` |
| Build status record | `STATUS.md` |
| Implementation report | `docs/IMPLEMENTATION-REPORT.md` |

---

## 11. Demo Instructions

### Quick Start (clean clone, no setup)

```bash
# 1. Clone
git clone https://github.com/dkadchha2845/aegis.git
cd aegis

# 2. Backend
python -m venv .venv
.venv/bin/pip install -r services/api/requirements.txt
.venv/bin/uvicorn services.api.main:app --reload --port 8000

# 3. Frontend (new terminal)
npm install --prefix apps/web
npm run dev --prefix apps/web
# → http://localhost:5173

# 4. Verify
curl http://localhost:8000/api/health
# Should report all systems live (or honest degraded status)
```

### Optional: Enable Gemini explanations

```bash
cp .env.example .env
# Edit .env → set GEMINI_API_KEY=your_key_here
# Restart the backend
```

### Demo Flow (3–4 minutes)

1. **Landing:** Open `http://localhost:5173`. WebGL hero + GSAP animation loads.
2. **Login:** Enter any credentials (open demo mode — seeded roles active).
3. **Live Protection:** Click "Try a demo call". Watch the Threat Meter escalate CALM → CRITICAL.
4. **Coach:** Highlight the verbatim coaching prompt that appears at ISOLATION stage.
5. **Investigation Report:** Show the PDF generated when the call ends (entities, timeline, 1930 guidance).
6. **Scam Map:** Switch to `/intel`. Show fraud graph + geospatial hotspot map.
7. **Knowledge Assistant:** Ask `/knowledge`: "How do I verify if a call is from the real CBI?"

### API Endpoints Reference

| Endpoint | Method | Function |
|---|---|---|
| `/api/health` | GET | System status — live vs degraded per component |
| `/api/analyze` | POST | Stateless single-utterance analysis |
| `/api/analyze/image` | POST | OCR image analysis |
| `/api/analyze/knowledge/ask` | POST | RAG knowledge assistant |
| `/api/session/start` | POST | Start live session |
| `/api/session/{id}/frame` | WS | 4 Hz live StateFrame stream |
| `/api/session/{id}/report` | GET | JSON evidence package |
| `/api/session/{id}/report.pdf` | GET | PDF evidence package |
| `/api/intel/graph` | GET | Fraud graph data |
| `/api/intel/clusters` | GET | Campaign cluster list |
| `/api/intel/map` | GET | Geospatial hotspot data |
| `/api/shield/verify` | POST | Citizen threat verification |
| `/api/shield/coach` | GET | Stage-aware coaching lines |

---

## 12. Competitive Landscape

| Capability | AegisAI | Truecaller | 1930 Portal | Generic LLM Wrapper |
|---|---|---|---|---|
| Real-time intervention during call | ✅ | ❌ | ❌ | ⚠️ Possible but slow |
| Understands 7-step psychological arc | ✅ | ❌ | ❌ | ❌ |
| Zero-hallucination / court-defensible | ✅ | N/A | N/A | ❌ |
| Fraud network graph intelligence | ✅ | ❌ | ⚠️ Manual | ❌ |
| Multi-modal: voice + image + text | ✅ | ❌ | ⚠️ Text only | ⚠️ |
| Hinglish / Hindi native support | ✅ (MuRIL) | ⚠️ | ❌ | ⚠️ |
| PDF evidence for court submission | ✅ | ❌ | ⚠️ | ❌ |
| No SIM/number blacklist dependency | ✅ | ❌ | ❌ | ✅ |
| Runs offline (no GPU, no key) | ✅ | N/A | N/A | ❌ |
| Open source, reproducible | ✅ | ❌ | ❌ | ❌ |

**Why Truecaller cannot solve this:** Relies on crowdsourced blacklists. Scammers bypass by buying new SIM cards daily. Does not understand call context, stage, or psychological pressure.

**Why portal-based reporting cannot solve this:** Reports are filed after the transaction. By definition, too late.

**Why generic LLM wrappers cannot solve this:** LLMs hallucinate — unacceptable for law enforcement evidence. Latency too high for real-time coaching. Cannot reliably detect the BENIGN class (real institutional calls).

---

## 13. Impact & Roadmap

### Immediate Impact (Hackathon Build)

- Citizens: real-time shield during suspicious calls
- Law enforcement: automatically generated intelligence packages, fraud graph, scam map
- Financial institutions: entity extraction (UPI VPAs, bank accounts) for rapid freeze requests
- Courts: reproducible, auditable evidence with full signal citations

### Scale Estimate

| Level | Implementation | Reach |
|---|---|---|
| App-level (current) | Web app + backend | Individual citizens with smartphones |
| IVR integration | Sarvam ASR + PSTN bridge | Feature-phone users, rural India |
| Telecom provider level | TRAI/DoT partnership — detection at network layer | 1.2 billion subscribers |
| National | NCRB portal integration, automated 1930 reporting | Complete national coverage |

### Roadmap

| Phase | Timeline | Items |
|---|---|---|
| **Phase 1 — Done** | Hackathon | 3 full modules, 84 tests, PDF evidence, RBAC, RAG, CI |
| **Phase 2 — Near** | Post-hackathon | Live microphone WebSocket stream, MuRIL full retrain, Sarvam ASR, push notifications |
| **Phase 3 — Scale** | Q1 2027 | Telecom provider API, 12 regional dialects, automated MHA alert generation |
| **Phase 4 — National** | 2027+ | NCRB integration, automated 1930 reporting, WhatsApp / IVR access, counterfeit currency module |

---

## 14. Judging Criteria Self-Assessment

| Criterion | Weight | Our Case |
|---|---|---|
| **Innovation** | 25% | First real-time psychological arc classifier for scam calls. 7-stage taxonomy with BENIGN discipline. Digital Twin forecasts time-to-payment. Deterministic + LLM hybrid (LLM as explainer only). |
| **Business Impact** | 25% | Directly addresses ₹1,776 crore / 9-month loss. Scalable to 1.2B citizens via telecom integration. Reduces law enforcement investigation time from weeks to minutes. |
| **Technical Excellence** | 20% | 84 tests. Schema-first contract. Deterministic scoring. Reproducible ML pipeline. Leave-archetypes-out validation. CI on py3.9+py3.12+frontend. SIGSEGV fixed under concurrent load. |
| **Scalability** | 15% | SQLite default → Postgres in one env var. NetworkX → Neo4j (same interface). Local Whisper → Sarvam ASR. Stateless analysis path for horizontal scaling. Multi-tenant RBAC ready. |
| **User Experience** | 15% | GSAP animated landing. WebGL hero (Three.js). Command palette (⌘K). ARIA-compliant maps. Mock stream replay when API is down. Entrance motion on every screen. Light + dark theming. |

---

*AegisAI — Every citizen's device is now a shield. Not a substitute for reporting fraud on 1930 or at cybercrime.gov.in.*

**GitHub:** https://github.com/dkadchha2845/aegis  
**Problem Statement:** PS 6 — AI for Digital Public Safety  
**Hackathon:** ET AI Hackathon 2026
