# AegisAI — Phase 0 Audit

**Date:** 2026-10-09 · **Commit:** `f39f44e` (`main`) · **Auditor:** Claude Code
**Brief:** [`AEGIS_AGENT_BRIEF.md`](../AEGIS_AGENT_BRIEF.md) §3

This audit maps what the brief says AegisAI *is* onto what the code *does*.
Every ✅ below was run on 2026-10-09; anything not run today says so. No code
was changed to produce it.

> **The project is not at the starting line the brief assumes.** It already has
> a working rules file, an architecture document, four ADRs, a 2,300-line task
> history and 603 backend tests. The useful output of this audit is therefore
> the *gap* between that work and the brief's pitch — and one defect in the
> research claim that outranks everything else (B-01).

---

## 1. Stack and how to run

| Layer | What is used |
|---|---|
| Backend | Python 3.12.14 (`.venv`), FastAPI, Pydantic v2, SQLAlchemy + Alembic, 9 routers / 73 routes (72 REST + 1 WebSocket; recounted from source during T-01 — the original 61 undercounted) |
| Orchestration | **LangGraph 0.6** (`services/api/orchestration/graph.py`), Celery + Redis worker with an in-process fallback |
| Stores | PostgreSQL 16 · Neo4j 5.26 · Qdrant 1.12 · Redis 7.4 via colima + `infra/compose/dev.yml`. All four are optional; SQLite / NetworkX / in-house retrieval / in-process execution are the fallbacks |
| ML | Fine-tuned MuRIL stage classifier fused with a lexical classifier; sentence-transformers retrieval; Markov "digital twin". `torch` and `transformers` are commented out of `services/api/requirements.txt` — installed locally, absent on the deploy |
| LLM | Provider-abstracted in `services/api/llm.py` (Gemini, Ollama, Anthropic). Explanations only. Gemini is configured locally |
| Frontend | React 18.3, TypeScript 5.6, Vite 5.4, react-router 7, GSAP, three.js, Leaflet. 22 page components. Node 24 locally, Node 20 in CI |
| Contract | `schema/models.py` ↔ `schema/types.ts`, proven by `schema/check_contract.py` |
| Deploy | Render (API) + Vercel (SPA); `render.yaml` sets `AEGIS_AUTH=1`. **Production was not probed in this audit** |

```bash
make install                              # backend deps + npm ci
colima start && make up                   # backing stores (optional)
make api                                  # :8000
make worker                               # Celery, needs `make up`
make web                                  # :5173
make gates                                # the four gates
AEGIS_REQUIRE_SERVING_BEST=1 make gates   # the same, refusing a fallback classifier
make check                                # gates + ruff + mypy
```

### What was run today, and what it said

| Command | Result |
|---|---|
| `AEGIS_REQUIRE_SERVING_BEST=1 make gates` | **Exit 0.** 603 collected: 577 passed, 26 skipped, 0 failed. Contract consistent. Typecheck and production build clean |
| `make lint` · `make types` | ruff: all checks passed. mypy: no issues in 37 source files |
| API boot (`DATABASE_URL=""`, ephemeral DB) | Booted. `classifier: fused`, `loaded: true`, retrieval `dense` (31 chunks), twin fitted, 8 agents registered in 4 tiers, `degraded: ["db:ephemeral"]` |
| Browser pass | Landing, login, Analyze, Investigate and Model card render. One investigation submitted through the UI. No horizontal overflow on `/investigate` at 375 px |

The gates and the API ran in the main checkout, which is the only place the
3.5 GB of model weights exist.

### What was **not** verified today

- **Anything behind the dev stack.** colima was not running, so Postgres,
  Redis, Neo4j and Qdrant were all unreachable. The 26 skips are the
  broker-backed queue tests; migrations were proven on SQLite only (the gate
  output says so itself). The Celery worker path, `kill -9` recovery and the
  PostgreSQL migration were last verified on 2026-08-27 per the task history.
- Audio (`/api/analyze/audio`) and image (`/api/analyze/image`) analysis,
  password reset, the evidence vault and complaint PDF.
- A fresh-clone install. The audit ran in the existing checkout.
- `pip-audit` / `npm audit`.
- The deployed site.

Tasks T-07 and T-08 exist to close the first and third.

---

## 2. Repo map

| Path | What it is |
|---|---|
| `schema/` | The contract: `StateFrame`, `Event`, `InvestigationState`, `AgentResult`; mock fixtures; the drift check |
| `services/api/agents/` | Agent protocol (`base.py`), registry, `classify/` (input classifier + magic-byte sniffing), `inherited/` (7 adapters over the call engine) |
| `services/api/orchestration/` | LangGraph build, per-node timeout/retry policy, trace recorder, determinism helpers |
| `services/api/investigations/` | Intake (size caps, hashing), runner, report (JSON + PDF) |
| `services/api/jobs/` · `services/worker/` | Broker probe, Redis progress journal, cost-class routing; Celery app and tasks |
| `services/api/stores/` | Evidence repository (org-scoped), blob storage, infrastructure probes |
| `services/api/engine/` | **The inherited KAVACH engine**: classifier, threat fusion, coercion, twin, passport, spoofing, scripts, OCR, UPI, reports |
| `services/api/ingest/` | Whisper ASR, diarization, language detection, normalisation |
| `services/api/intel/` | NetworkX fraud graph, clusters, centrality, link prediction, entity extraction |
| `services/api/shield/` · `rag/` | Citizen verification, evidence vault, complaint; retrieval and coach lines |
| `services/api/routes/` | analyze · investigations · session · auth · reports · intel · shield · orgs · research |
| `services/api/` (root) | `auth.py`, `permissions.py`, `orgs.py`, `audit.py`, `security.py`, `config.py`, `db.py`, `llm.py`, `migrations/` |
| `apps/web/src/` | Pages, components (`landing/`, `layout/`, `intel/`, `map/`, `report/`, `three/`, `ui/`), 7 stylesheets incl. `tokens.css` |
| `packages/aegis_core/` | Shared taxonomy, entities, Hinglish handling (installed editable) |
| `ml/` | Corpus generation, training, the promotion-gate evaluation, 1,617 labelled turns, 3.5 GB of gitignored artifacts |
| `research/` | **Empty** — five directories holding `.gitkeep` |
| `infra/` | Compose stack, Dockerfiles, deploy config, seeds |
| `docs/` | Architecture, auth, datasets, deployment, research plan, UI audit, 4 ADRs, task history |
| `Skills/` | 1,613 tracked files (43 MB) of third-party agent-skill bundles. Not part of the product |
| `ui-design/` | 14 tracked HTML mockups, several titled "AI Stylist Chat" / "wardrobe" — not this product |
| `attached_assets/` | Hackathon-era decks and a problem-statement PDF |

---

## 3. Feature status

✅ working, verified today · 🟡 partial · 🎭 mocked · ❌ missing

| Feature | Intended (brief §2) | Status | Evidence | Notes |
|---|---|---|---|---|
| Text scam analysis | Risk score with explanation | ✅ | `POST /api/analyze/text` | Hinglish digital-arrest script → 93 CRITICAL. Bank debit SMS → 7.5 CALM. Delivery SMS → 7.5 CALM. Short English KYC phish → 95 CRITICAL |
| Agentic investigation | Agents investigate, produce a verdict | 🟡 | `POST /api/investigations`, `/investigate` | Runs 7 graph steps, 6 agents, 24 findings in under a second. **Returns no risk score, no entities and no recommendations** (B-02, B-03). The UI says "Not scored" rather than inventing one |
| LangGraph orchestration | 6 + 1 agents on LangGraph | 🟡 | `orchestration/graph.py` | Real `StateGraph`, per-node timeout and retry, trace. Four sequential tiers with concurrency inside each. No entity fan-out, no recursion |
| Adversarial verifier (A7) | Can reject or downgrade a finding | ❌ | — | Not in code. **Not in any existing doc or plan either** |
| Modality: text / chat | — | ✅ | analyze + investigation paths | The only modality the graph's content agents read |
| Modality: audio / call | — | 🟡 | `ingest/asr.py`, `/api/analyze/audio` | Batch Whisper on the legacy path. Not a graph agent. Not run today |
| Modality: image / document | — | 🟡 | `engine/ocr.py`, `/api/analyze/image` | Tesseract OCR + zbar QR on the legacy path. Not a graph agent. Not run today |
| Modality: transaction / metadata | — | 🟡 | `engine/upi.py`, `engine/spoofing.py` | UPI and number-spoofing checks exist. `number_spoofing` is registered but had nothing to read on a pasted message |
| Calibrated late fusion | Per-modality scores, calibrated, fused | ❌ | `engine/threat.py` | Scoring is hand-weighted signal fusion on the legacy path. No per-modality score, no calibration, no ECE anywhere in the repo |
| Scam-stage state machine | Tracks the victim's stage | ✅ / 🟡 | `/api/session/*` | Four-turn arc ran today: AUTHORITY_CLAIM → FEAR_INDUCTION → ISOLATION → AUTHORITY_CLAIM. The last turn ("transfer 50000") should be PAYMENT_SETUP (B-04). Stage accuracy on unseen scam types is poor (B-01) |
| Investigation case file | Structured, exportable | 🟡 | `/api/investigations/{id}/report`, `.pdf` | JSON and a valid PDF both returned 200. Honest but thin: findings and trace, no score, entities or actions |
| Live intervention | Alerts during an ongoing scam | 🟡 | `/api/session`, `/live`, `/analyst/console` | Utterance → frame works over REST; a WebSocket route, coach lines, payment hold and guardian acknowledgement endpoints exist. Text utterances only: no streaming STT, no WebRTC. Latency unmeasured |
| Live console demo | — | 🎭 | `hooks/useStreamPlayer.ts` | Defaults to a recorded fixture, **labelled "recorded stream"** in the UI, with a one-click switch to live |
| Auth and roles | victim / investigator / admin | ✅ | `auth.py`, `permissions.py` | Seven roles, single grant map, revocable sessions. Demo sign-in as Analyst worked. Default dev mode is open (S-01) |
| Investigator dashboard | Review cases | 🟡 | `/intel`, `/dashboard`, `/reports` | Graph, clusters and a case book exist. No case queue or triage workflow |
| Fraud knowledge graph | Cross-case links | 🟡 | `intel/` | NetworkX, in-process: 114 cases, 9 clusters, 47 entities, seeded. Not connected to the investigation graph |
| RAG | Cited guidance | 🟡 | `rag/store.py` | 31 chunks over 4 documents. Not a graph agent |
| Export | Case file export | ✅ | report PDF | 5.6 KB PDF produced today |
| Admin | Users, orgs, audit | 🟡 | `/admin/dashboard`, `/api/audit` | Present; not exercised today beyond the endpoints answering |
| Evaluation harness | Metrics → results file | ❌ | `research/` | Only the stage-classifier comparison exists, and it is contaminated (B-01) |
| SAGE-style baseline | Tabular baseline to beat | ❌ | — | SAGE is not mentioned anywhere in the repository |
| Frontend tests | Unit + e2e | ❌ | `apps/web/` | None. One consistency script (`check-landing-session.mjs`) |

---

## 4. Architecture coverage

### Layers

| Brief layer | Status | Where it lives |
|---|---|---|
| Ingestion | ✅ | `investigations/intake.py` (caps enforced while reading, hashing, filename sanitising), `agents/classify/sniff.py` (magic bytes) |
| Perception | 🟡 | Text only inside the graph. OCR, QR and ASR exist in `engine/` and `ingest/` but are reachable only from the legacy routes |
| Agentic core | 🟡 | LangGraph graph with 8 registered agents — 1 classifier and 7 adapters over the call engine |
| Decision | ❌ in the graph / 🟡 legacy | The graph's judge tier holds `digital_twin` and `threat_fusion` adapters but writes no `risk_score`. The legacy path scores with hand-set weights |
| Presentation | ✅ | React SPA, pure renderer, schema-typed |

### Agents: the pitch against the registry

The brief says **6 specialists + 1 adversarial verifier**. The registry holds
**8 agents with a different decomposition**, and `docs/ARCHITECTURE.md` targets
about 17. Nothing in the repository names "the six".

| Registered today | Tier | Version |
|---|---|---|
| `input_classifier` | extract | 1.0.0 |
| `number_spoofing` | investigate | 1.0.0 |
| `coercion_tracker`, `script_match`, `stage_classifier`, `trust_passport` | reason | 1.0.0 |
| `digital_twin`, `threat_fusion` | judge | 1.0.0 |

A proposed reconciliation, so the pitch, the paper and the code tell one story.
**[ASSUMPTION — needs your confirmation, see Q2]**: the "6 + 1" are *roles*,
each implemented by one or more registry agents.

| Role | Covers | Built today |
|---|---|---|
| A1 Intake and classification | type sniffing, routing | ✅ `input_classifier` |
| A2 Conversation and text | stage, coercion, script match, trust passport, twin | 🟡 five adapters, text only |
| A3 Visual and document | OCR, QR, screenshots | ❌ in graph (legacy code exists) |
| A4 URL and infrastructure | domain, redirect, typosquat | ❌ |
| A5 Financial and identity | UPI, phone, spoofing | 🟡 `number_spoofing` only |
| A6 Intelligence | fraud graph, RAG, threat intel | ❌ in graph (legacy code exists) |
| **A7 Adversarial verifier** | challenges findings before the judge | ❌ |
| Decision layer (not an agent) | calibrated fusion, explanation | ❌ |

### Other named pieces

| Piece | Status | Note |
|---|---|---|
| LangGraph graph | ✅ | Real, tested, traced |
| Fusion step | 🟡 | Hand-weighted, legacy path only |
| Calibration | ❌ | — |
| Scam-stage state machine | ✅ | 8 stages + Markov forecast, in the live session |
| Case-file generator | 🟡 | Two of them: the legacy evidence package and the investigation report |
| Live intervention | 🟡 | Text-driven; real-time claim unmeasured |

---

## 5. Bugs and errors

### B-01 — Critical — The classifier's headline result is a train/test leak

**Files:** `ml/artifacts/backend_comparison.json`, `ml/artifacts/checkpoint_manifest.json`,
`ml/evaluation/eval_backends.py`, and every document that quotes 0.767.

The served MuRIL weights were written at 04:17 on 2026-07-21, from the original
split in commit `85a2aee`. The split was rebuilt in `5afb554` at 19:32 the same
day. The weights were not retrained, and the promotion gate then scored the old
weights on the new test set — most of which they had been trained on.

Measured today, read-only:

| Subset of the current 423-turn test split | n | Lexical macro-F1 | MuRIL macro-F1 |
|---|---|---|---|
| All turns (the published figure — leaked) | 423 | 0.375 | **0.767** |
| Archetypes whose turns are verbatim in the original train + val | 311 | 0.317 | **1.000** |
| Archetypes the model never saw | 112 | **0.431** | 0.300 |

311 of 423 test turns — every `courier_parcel`, `loan_app_harassment` and
`refund_overpayment` turn — are exact-text members of the data the checkpoint
was trained on. MuRIL scores them perfectly. On the 112 turns it has not seen,
**it loses to the keyword baseline**, and the gate is promoting it on the
strength of the leak.

The served backend is `fused` (MuRIL max-fused with lexical); the fused backend
was not scored separately on the unseen subset today.

**Why it is critical:** this is the project's only measured ML result, it is
stated as "zero-leak" in `README.md`, `docs/RESEARCH.md`, `docs/INVENTORY.md`,
`docs/DATASETS.md`, ADR-0003, `docs/DEPLOYMENT.md` and two HTML dossiers, and
the product's own Model card page displays it under the heading "Measured, not
assumed". `CLAUDE.md`'s advice to "check the promotion gate before retraining"
rests on the same reading. Any report, slide or paper draft citing the leaked
0.767 needs correcting before a review.

**Reproduce:** extract `ml/data/processed/{train,val}.jsonl` at `85a2aee`, count
current test turns whose text appears in them, and score both backends on the
two halves through `ml/evaluation/eval_backends.py`'s own `evaluate()`. T-06
commits that script.

**Also measured 2026-10-09, during T-04:** on the *original* 171-turn test split
— the one these weights were actually held out from — MuRIL scores 0.221 and
lexical 0.372. That 0.221 is exactly the figure in the `metrics.json` committed
with the weights in `85a2aee`. So the earlier account, in which 0.221 was a
"stale" file suppressing a good checkpoint, had it backwards: 0.221 was the
honest number and 0.767 the leak.

**Status:** documents, code comments and the wording the product serves were
corrected in T-04. **The gate was fixed in T-05 (2026-10-10):** it now refuses
to score a checkpoint on data it was trained on, the leaked comparison is gone
from the repository, and the lexical classifier serves. What remains is a
model that deserves promotion — T-38 and T-45.

### B-02 — High — The agentic investigation produces no verdict

**Files:** `services/api/investigations/report.py`, `agents/inherited/fusion.py`

The same Hinglish digital-arrest message scores **93 CRITICAL** on
`/api/analyze/text` and comes back from `/api/investigations` with
`risk_score: null`, `scored: false`. Inside that investigation, `threat_fusion`
reports `threat_level: ELEVATED` — a third answer. The report says plainly that
it is unscored, which is correct behaviour, but it means the flow the project
is named after cannot yet tell a user whether something is a scam, while the
older flow beside it can.

### B-03 — Medium — Investigations extract no entities

The input classifier correctly detects `TEXT`, `URL` and `UPI_ID` in a message
containing a link, a UPI ID and a phone number, and `state.entities` is still
`{}`. The legacy path extracts the same entities. No agent in the graph writes
them, so nothing downstream (graph lookup, URL checks, the case file) has
anything to work on.

### B-04 — Medium — The decisive payment turn is mis-staged

In a live session, "Abhi 50000 RBI safe account mein transfer kariye" is
classified `AUTHORITY_CLAIM` (0.67) with `PAYMENT_SETUP` at 0.10. The same miss
was recorded on 2026-08-24. It is a symptom of B-01, on the turn where a
warning matters most.

### B-05 — Low — A benign delivery SMS still emits a script-match finding

`script_match` attached a `FEAR_INDUCTION` finding to "Your Amazon order has
been shipped…". The threat level stayed CALM, so no false positive reached the
user; the finding still appears on the report. Confidence not inspected.

### B-06 — Low — `.claude/launch.json` cannot start the API from a worktree

The `api` configuration uses a relative `.venv/bin/python`, which exists only
in the main checkout.

**Fixed in T-71 (2026-10-22):** `scripts/dev.sh api|web` runs the checkout's own code with its own `.venv` / `node_modules`, or the primary checkout's when a worktree has none; `.claude/launch.json` calls it. Verified: the API answers from a worktree with no `.venv`.

### B-08 — Medium — An English payment-demand scam is scored as legitimate

*Found 2026-10-10 during T-05; not fixed, and not caused by it.* "This is FedEx
customs. A parcel in your name contains illegal items. Pay the clearance fine of
4999 now or a police case will be filed." scores **32 WATCH, LIKELY_LEGITIMATE**
with the fused model and **25 WATCH** with the lexical one. A false negative on
a textbook script, in the language the project already knew was its weak one.
Owned by T-45 (corpus) and T-42 (fusion).

### B-07 — Medium — The current split is "leave-archetypes-out" in name only

*Found 2026-10-09 during T-04; not fixed.* `ml/data/processed/report.md` and the
Model card both describe the split as leave-archetypes-out. It holds out eight
call *skeletons*, and no text, call or skeleton is shared between train, val and
test — that part is true. But three archetypes sit on both sides through
different skeletons: `kyc_expiry` is in train (65 turns) and in test (12), and
`kyc_expiry`, `loan_app_harassment` and `genuine_police` are in both val and
test. A model retrained on this split is therefore not being tested on unseen
scam *types* for those three, and any figure from it must not be described that
way. Owned by T-38, which builds the split with an overlap test; T-45 must not
retrain before it.

---

## 6. Security issues

| ID | Severity | Issue | Evidence |
|---|---|---|---|
| S-01 | Medium | **Open demo mode is the default.** With `AEGIS_AUTH` unset, a request with no token is treated as the platform owner: `GET /api/audit` and `GET /api/auth/users` return 200 unauthenticated, and `/api/auth/demo-accounts` publishes the shared password. Intended for local demos, and `render.yaml` sets `AEGIS_AUTH=1` — but production was not checked, and one missing env var turns the deployed API into this | `curl` against the local API today. **Fixed in T-71 (2026-10-22):** auth is enforced unless `AEGIS_AUTH=0`; `make api` and `scripts/dev.sh api` set it for local demos. Verified live: with the variable unset, `/api/audit` and `/api/auth/users` return 401 and `/api/auth/demo-accounts` is empty |
| S-02 | High (when built) | The URL agent will fetch attacker-supplied URLs and the APK agent will hold live malware. Neither exists yet. The `sandbox` queue is chosen from the filename, so it is a cost class, not a boundary | `docs/ARCHITECTURE.md` §8 |
| S-03 | Medium | **Prompt-injection handling was not audited.** Evidence text reaches `llm.py` for explanations. Invariant 8 says it is quoted as untrusted data; no test was found that feeds an injection and asserts it is not followed | `services/api/llm.py` |
| S-04 | Low | No per-organisation upload quota. The 4 MB per-file cap is enforced while reading | `investigations/intake.py` |
| S-05 | Low | 1,613 third-party files under `Skills/` are tracked in the product repository — unreviewed content, licence exposure and review noise | `git ls-files Skills` |
| S-06 | Info | A live Gemini key sits in the local `.env`. It is gitignored and has never been committed; rotate it before any public demo | `git check-ignore .env` |
| S-07 | Medium | *Found during T-01.* **Routes that declare no permission.** `CLAUDE.md` says every route declares `require_permission(...)`. Twenty-five routes in three routers neither declare a permission nor identify the caller: all 8 of `/api/analyze/*` (an `ANALYZE_USE` permission exists in `permissions.py` and nothing requires it), all 7 of `/api/shield/*` (the vault is token-addressed by design), and 10 of the 13 `/api/session/*` routes — every one but the three payment actions, including the WebSocket and the evidence-package PDF. (Sign-up, login, password reset, `/api/auth/status` and `/api/auth/demo-accounts` are also unauthenticated, as they must be.) Some may be public by intent (a citizen checking a message without an account); that intent is not written down anywhere, and the session routes expose another person's live transcript to anyone holding its id. Owned by T-59 | route decorators in `services/api/routes/` |

Not found: committed secrets, wildcard CORS origins (origins are pinned;
methods and headers are `*` with credentials), path traversal at intake.

---

## 7. UI/UX issues

No screenshots were saved to the repository during this audit.

| ID | Issue | Where |
|---|---|---|
| U-01 | The Model card shows the leaked **0.767** under "Measured, not assumed" (B-01). *Fixed in T-05: the page now shows the gate's refusal and the lexical figure alone* | `/model` |
| U-02 | Two icon buttons in the app header have no accessible name. **Resolved — verified 2026-10-22 (T-71):** every product control on ten routes has an accessible name; the only unnamed controls are the dev-only Agentation toolbar (`import.meta.env.DEV`), which never ships | `components/layout/AppShell.tsx` |
| U-03 | Internal task numbers in user-facing copy: "The judgement tier has no agents yet (tasks 4.6 and 4.7)". **Fixed in T-71** — the only one in rendered strings, replaced with plain copy | `/investigate` |
| U-04 | Two entry points for one job. "Analyze" gives a score; "Investigate" gives an agent trace and no score. A user cannot know which to use | `/analyze`, `/investigate` |
| U-05 | The design system exists as code (`tokens.css`, `primitives.css`) and is undocumented; several components the brief requires — risk gauge, stage timeline, agent-trace panel, evidence viewer — are absent or one-off | `apps/web/src/styles/` |
| U-06 | No Hindi interface, for a product whose strongest model is Hindi/Hinglish | — |
| U-08 | *Found during T-03.* The landing's `--lp-ink-3` (`#6f7789`) measures **4.46:1** on `--lp-deep` — under the 4.5:1 AA floor for the captions and micro-labels it sets. Its comment in `landing.css` claims 4.6:1; the light value measures 4.14:1 on a card. **Fixed in T-71:** `#788092` / `#616977`, ≥ 4.73:1 on every landing surface | `styles/landing.css` |
| U-07 | Six `ERR_CONNECTION_REFUSED` console errors in dev before sign-in. **Not reproducible on 2026-10-22 (T-71):** a clean load of `/login` and `/` with the API up gives no console error and no failed request; the errors seen this session came only while a dev server was down | browser console |

Verified fine: the landing and login scroll, `/investigate` has no horizontal
overflow at 375 px, the app chrome renders in dark theme.

---

## 8. Code quality and tech debt

| ID | Issue |
|---|---|
| D-01 | **Two analysis pipelines.** The legacy engine behind `/api/analyze` and `/api/session`, and the investigation graph. They disagree on the same input (B-02) and every new capability must currently choose one |
| D-02 | `engine/features/` (about 600 statements) is off the serving path and duplicates `engine/spoofing.py` and `engine/scripts.py`. Carried from `docs/INVENTORY.md`; not re-measured today |
| D-03 | Stale and stray documents: `STATUS.md` (dated 22 July, titled "AegisAI / AegisAI"), the task-history header (2026-08-27, "575 tests"), `docs/INVENTORY.md` (2026-08-23), `aegis_ai_pipeline_docs.md` at the root, `attached_assets/`, `ui-design/`, `Skills/` |
| D-04 | `research/` is empty. No experiment, ablation, baseline or result has been committed |
| D-05 | Prompts are inline strings in `services/api/llm.py`, not versioned files |
| D-06 | No frontend tests and no end-to-end tests |
| D-07 | CI can only ever prove the lexical fallback, because the checkpoint is not reachable from a runner (task 1.7b, still open) |
| D-08 | No structured logging and no request or case ID carried through a run. Sixteen bare `print()` calls in served modules |
| D-09 | No shared error envelope: 57 `HTTPException` call sites return a string `detail`, validation errors return a list |
| D-10 | The brief's document set is incomplete: no PRD and no design-system document |
| D-12 | *Found during T-04.* The Model card's hand-written limitations are stale: "320 synthetic calls" (the corpus report says 338), "PAYMENT_SETUP and PAYMENT_EXECUTION have 2 and 4 test examples" (the current split has 27 and 58), and the split is described as leave-archetypes-out (B-07). Owned by T-44, which should generate the card from the manifest |
| D-13 | *Found during T-05.* The same lexical model is now served everywhere, but a checkout with no checkpoint reports it as a FALLBACK with `clf:lexical_fallback`, while a checkout holding the refused checkpoint reports it as "best available" with no tag. Both are defensible; together they are confusing. `services/api/serving.py`'s line "not what the app serves" is now untrue of a clean clone. **Fixed in T-71 (2026-10-22):** with no checkpoint, the lexical model is a fallback only when the comparison on file promotes a checkpoint this machine lacks; CI now requires `best` |
| D-14 | *Found during T-05.* Every `make eval` rewrites the tracked `ml/artifacts/checkpoint_manifest.json` with a new `measured_at`, so re-running the gate leaves the working tree dirty even when nothing changed. **Fixed in T-71 (2026-10-22):** the manifest is rewritten only when something it states changes |
| D-15 | *Found during T-01.* `docs/DATASETS.md` §2 gives the call corpus as "1,692 calls"; the generated `ml/data/processed/report.md` says 338 calls (209 scam, 129 benign) and 1,617 utterances. The PRD uses the generated figures. Owned by T-37's data card |
| D-11 | The plan is behind its own timeline. Phase 2 was scheduled for 28 Sep – 1 Nov; the last commit is 7 Sep and Phase 2 has not started. The plan totals about 1,060 hours |

---

## 9. Open questions for Dhrumil

> **Answered 2026-10-09.** The owner approved the audit and delegated the
> choices below ("do whichever suits best for all"). Each is recorded here as a
> decision taken under that delegation, and each is reversible.
>
> | Q | Decision |
> |---|---|
> | 1 Scope | **The brief's core is the committed scope.** Everything in the "Parked" table of `docs/TASKS.md` stays parked |
> | 2 The six agents | **The A1–A7 roles in §4 are the working names.** No document in the repository names the six, so this remains an `[ASSUMPTION]` in the PRD until checked against the synopsis |
> | 3 B-01 | **Correct 0.767 everywhere (T-04) and let a leak-free gate decide what serves (T-05)**, even if that is the lexical classifier. Whether any report, deck or paper draft outside this repository cites the number is not something the repository can answer — check them |
> | 4 Provisional score | **Yes.** The investigation shows the existing score, tagged `score:uncalibrated`, until calibration replaces it. T-20 is unblocked |
> | 5 SAGE | **Still open.** It cannot be decided without the paper. T-40 stays blocked; the paper will be fetched and read when T-40 opens, and nothing is claimed about it before then |
> | 6 Team and dates | **Still open.** Only the owner knows them. The PRD will carry them as `[ASSUMPTION]` placeholders; T-01 is no longer blocked on them |
> | 7 Housekeeping | **`Skills/` and `ui-design/` leave the tree; `attached_assets/` and `aegis_ai_pipeline_docs.md` move to `docs/archive/`.** Git history keeps all of it. T-10 is unblocked |
> | 8 Task-list move | Kept |
>
> **Also instructed:** all work is committed to `main`; no separate branches.

1. **Scope.** The brief pitches 6 + 1 agents, four modalities and calibrated
   late fusion. The existing plan is 11 phases, about 17 agents and 1,060
   hours, and is already behind. I recommend committing to the brief's core and
   parking the rest (APK, Neo4j, Qdrant, video, voice authenticity, SIP, SMS
   channel). `docs/TASKS.md` is written that way. Agree?
2. **The six agents.** What are the six specialists called in your synopsis or
   slides? §4 proposes a grouping; I would rather match what examiners have
   already seen.
3. **B-01.** May I correct the 0.767 claim everywhere and let a leak-free gate
   decide what serves — even if that means the product reports the lexical
   classifier until a retrain? Does any submitted report, slide deck or paper
   draft cite the number?
4. **A provisional score.** The investigation path shows "Not scored" until a
   calibrated model exists. T-20 would port the legacy score into it, tagged
   `score:uncalibrated`, so the two paths agree now. Acceptable, or keep it
   unscored until calibration lands?
5. **SAGE (arXiv:2606.08146).** I have not read this paper and nothing in the
   repository cites it. Please share the PDF or confirm the ID, so the
   "SAGE-style tabular baseline" is built against what it actually does.
6. **Team and dates.** The brief says a team of four; the repository credits
   two authors. Who is on the project, and what are the Review-1, Review-2 and
   final dates? The milestones need them.
7. **Housekeeping.** May `Skills/`, `ui-design/`, `attached_assets/` and
   `aegis_ai_pipeline_docs.md` be moved out of the repository or into
   `docs/archive/`? Nothing has been touched.
8. **The task-list move.** The previous `docs/TASKS.md` is preserved verbatim as
   `docs/TASKS_HISTORY.md` and a new one written in the brief's format. Undo
   with `git mv docs/TASKS_HISTORY.md docs/TASKS.md` if you would rather keep
   the old shape.
