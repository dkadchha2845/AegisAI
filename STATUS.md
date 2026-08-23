# AegisAI / AegisAI — build status

**Last updated:** 22 July 2026
**Verified against:** a clean run of the full check suite on this commit.

This is the running record of what is built and what is left. **Update it when
you finish something** — the person picking up next shouldn't have to
reverse-engineer the state from the diff.

> Full write-up of the latest work: [`docs/IMPLEMENTATION-REPORT.md`](docs/IMPLEMENTATION-REPORT.md).
> Phase-1 audit: [`docs/AUDIT.md`](docs/AUDIT.md).

---

## TL;DR

**All three AegisAI modules are built and demoable end to end** — Detect (Module 1
RSSIE) → Connect (Module 2 FIGAE) → Protect (Module 3 CFSRP). There are now 10
screens plus an awwwards landing and a dedicated login. Multi-tenant orgs, a
security-hardening pass, and a 5× corpus expansion landed this session, along
with a **fix for a reproducible API segfault** under concurrent load.

**Session 3 (22 Jul):** a full in-browser QA pass of every screen and flow
(8 defects found → all fixed, incl. a dead light theme and a dev-reload
data-loss trap), **dense retrieval live** (31 chunks / 4 docs), **Gemini
explanations working** (retired-model default fixed, `.env` finally loaded),
and dense script-matching **measured and rejected** on false-positive
discipline. See [`docs/IMPLEMENTATION-REPORT.md` §11](docs/IMPLEMENTATION-REPORT.md).

**Session 4 (22 Jul):** the "3 degraded" badge went to **all systems live**, honestly:
`DATABASE_URL` now defaults to a persistent SQLite file (clears `db:ephemeral`),
and the classifier no longer cries `clf:lexical_fallback` when the lexical model
is serving *because it won the measured comparison* — that is the promotion gate
working, not a fault, so it is reported as `lexical · best` (a real absent/failed
checkpoint, e.g. on CI, still degrades honestly). A **client-side login gate** now
fronts the console (load → landing; Enter → `/login`; the citizen shield stays
public), open mode **honours a presented token** so the seeded **role roster**
(owner/admin/analyst/viewer across two orgs) makes RBAC visibly real, and a
**retrieval-grounded knowledge assistant** (`/api/analyze/knowledge/ask`) answers
from cited corpus chunks only. Plus UI polish: entrance motion on every screen, a
3D tilt on the landing/login, and a styled tooltip replacing the overlapping
native one. Tests **84 pass**, contract consistent, frontend typecheck + build clean.

What's left is the **outer ring**: real audio in, real notifications out, real
payment rails, and the ~2-hour full-corpus MuRIL retrain. All additive.

| Measure | Where it stands |
|---|---|
| AegisAI modules | **3 of 3** (RSSIE + FIGAE + CFSRP) |
| Backend tests | **84 passing** (verdicts, intel, shield, security, orgs, auth, casebook, ocr, report, scripts, spoofing) |
| Contract check | **passing** (8 enums + version + 24-frame mock) |
| Frontend typecheck + build | **passing**, zero errors; main bundle 845 kB → **48 kB** (vendor split) |
| Corpus | **338 calls** — valid leave-archetypes-out benchmark (see Track 3 note) |
| Fraud graph | **114 cases → 9 clusters / 9 campaigns** |
| Runs on a clean clone | **yes** — no key, no GPU, no network |
| API under concurrent load | **stable** (was SIGSEGV — see Module fixes) |

---

## ✅ Done

### Contract (`schema/`) — complete

- `models.py` (Pydantic) and `types.ts` (TS unions) as a single source of truth
  for all 8 enums: `Stage`(8), `ThreatLevel`(5), `VictimState`(7),
  `PaymentState`(5), `GuardianState`(4), `Verdict`(3), `EventKind`(10).
- `check_contract.py` fails the build on any Python↔TS drift. **Passing.**
- `CONTRACT_VERSION = 1`, asserted on both sides.
- `mock-stream.json` — 24 `StateFrame`s + 24 `Event`s. Validated by the
  contract check, and the reason the UI still renders with the API down.

### Backend engine (`services/api/engine/`) — complete

| Module | State | Notes |
|---|---|---|
| `classifier.py` | ✅ | Both backends + **promotion gate** on measured F1, not file presence |
| `threat.py` | ✅ | 4-signal weighted fusion, returns named drivers, ratchets (fast up / slow down) |
| `twin.py` | ✅ | Fitted transition matrix + dwell times → time-to-payment forecast |
| `coercion.py` | ✅ | Victim-side stress, **independent** of the classifier. Text-only, capped lower |
| `passport.py` | ✅ | Mechanical identity checks, PASS/FAIL/**UNKNOWN**, each with a citation |
| `spoofing.py` | ✅ | **Number Spoofing Intelligence** — Caller-ID/authority mismatch, VoIP, intl routing, reported-number, format, call frequency. Risk 0-100 + PASS/FAIL/UNKNOWN checks. Feeds fusion (`W_SPOOF`) + dispositive in the analyzer |
| `report.py` / `report_pdf.py` | ✅ | **Evidence package** — MHA/cybercrime-compatible structured package (verdict, named signals, identity + number evidence with citations, stage timeline, transcript, reporting guidance). JSON + server-rendered PDF (reportlab, lazy/optional). `GET /api/session/{id}/report[.pdf]` |
| `upi.py` | ✅ | VPA + QR structural checks, no blocklist, no network call |
| `analyzer.py` | ✅ | Stateless path — reuses the *same* engine as the live path. Accepts `caller_number` (spoofing) and multi-channel `kind` (sms/whatsapp/email) |
| `ocr.py` | ✅ | **Pluggable OCR** (Tesseract default / EasyOCR / null) for image inputs — lazy, optional, degrades to `ocr:unavailable`. Optional QR decode. `POST /api/analyze/image` |
| `scripts.py` | ✅ | **Scam-script similarity** — sentence-embedding (dense) / TF-cosine (lexical) match of caller lines vs known scam scripts. Bounded 0-1, gated at 0.45, surfaced as the "Script similarity NN%" threat driver + fusion signal (`W_SCRIPT`) |

### Module 2 — FIGAE fraud intelligence (`services/api/intel/`, `routes/intel.py`) — complete

Fraud knowledge graph (NetworkX), community/campaign detection, centrality, link
prediction, geospatial hotspots (India gazetteer), dynamic cluster risk scoring
(LOW–CRITICAL), and AI investigation reports. Seeded historical repository with
reused infrastructure + live ingest of Module 1 saved cases. `FC-001` reproduces
the PDF's FC-021 exemplar. Frontend `/intel`: force-directed graph, India hotspot
map, cluster list, investigation report, entity search. **10 tests** (`test_intel.py`).

### Module 3 — CFSRP citizen shield (`services/api/shield/`, `routes/shield.py`) — complete

Threat verification (fuses Module 1 scoring + Module 2 cluster lookup), stage-aware
guidance (coach verbatim), emergency response (helpline directory + checklist),
token-addressed evidence vault (`CitizenReport`), structured complaint generator
(reuses the PDF renderer), awareness feed. Public routes. Frontend `/shield`.
**9 tests** (`test_shield.py`).

### Landing + login + multi-tenant — complete

Awwwards landing (`Home.tsx`, outside the shell, WebGL hero + GSAP), dedicated
`/login` (`Login.tsx`), all routes lazy-loaded. `Organization` model + `org_id`
scoping + `owner` role; backward compatible (default org seeded). **3 isolation
tests** (`test_orgs.py`).

### Security hardening — complete

`security.py`: token-bucket rate limiter, CSP + 4 hardening headers, login backoff
(CWE-307). **5 tests** (`test_security.py`). Plus the **temp-file DB fix** in
`db.py` that resolved a reproducible SIGSEGV under concurrent SQLite access.

### Platform (Track 2) — SaaS layer, optional and off by default

| Piece | Status | Notes |
|---|---|---|
| DB (`db.py`, `models_db.py`) | ✅ | SQLAlchemy, in-memory by default (`db:ephemeral`), persists via `DATABASE_URL`. Clean-clone demo preserved. |
| Auth + RBAC (`auth.py`, `routes/auth.py`) | ✅ | pbkdf2 + HS256 (stdlib only), roles viewer/analyst/admin, off by default (`AEGIS_AUTH`), open mode = seeded admin. |
| Persistence + audit (`routes/reports.py`, `audit.py`) | ✅ | Save evidence packages as cases; append-only audit log (logins, exports, payment overrides). |
| Frontend (`/cases`, `AuthContext`) | ✅ | Case book UI: saved cases, activity log, users, sign-in — role-scoped. Guardian "Save to case book". |
| `session.py` | ✅ | State machine → idempotent `StateFrame` snapshots + one-shot `Event` edges |

Thresholds live in one screen of `session.py`: guardian at **70**, payment hold
at **55**.

### API (`services/api/`) — complete

- **17 endpoints** across `routes/analyze.py` and `routes/session.py`, plus a
  WebSocket pushing frames at 4 Hz.
- `/api/health` reports live-vs-degraded per component. Startup warm-loads
  everything so the first click isn't a 3-second cold start.
- CORS locked to `localhost:5173` / `127.0.0.1:5173`.
- Upload path capped at 4 MB, accepts `.txt` / `.json` / `.csv`.

### Retrieval + coach (`services/api/rag/`, `knowledge/`) — complete

- BM25 **and** dense (sentence-transformers) backends, auto-selecting with
  fallback. 26 chunks across 3 curated documents (RBI advisories, scam
  playbooks, UPI safety).
- `coach_library.json` — 14 human-reviewed lines, delivered **verbatim**. An
  LLM may rank or reword the *explanation*; it never writes the line and never
  touches a score.

### Frontend (`apps/web/`) — complete

- All **7 routes** built: `/`, `/dashboard`, `/console`, `/guardian`,
  `/analyzer`, `/knowledge`, `/model`.
- `AppShell`, `CommandPalette` (`⌘K`), `RouteBoundary`, GSAP motion, a `three`
  WebGL `ThreatField`, light/dark theming.
- `useLiveSession` (WebSocket), `useHealth`, `useStreamPlayer` (mock replay).
- **Pure renderer** — zero threat maths, thresholds, or stage rules in React.
  Every number is a contract field. Typecheck clean.

### ML pipeline (`ml/`) — complete and reproducible

- Full offline chain: `generate_calls.py` → `paraphrase.py` →
  `build_dataset.py` → `train.py` → `eval_backends.py`.
- **Corpus is committed** (320 calls; 931 train / 138 val / 171 test), so the
  checkpoint is regenerable rather than lost.
- Split is **leave-archetypes-out by call** — the strict one, which is what
  caught the memorisation (see below).
- Both LLM generation backends work (Gemini free tier, local Ollama).

### Repo hygiene — done in this commit

- `.gitignore` excludes `.env`, venvs, `node_modules`, and the ~3.6 GB of model
  weights — while **keeping** `backend_comparison.json` and `metrics.json`,
  which are load-bearing.
- `.env.example` committed as the template. No secrets in history.
- Clone is **2.5 MB / 109 files**.
- `pytest` added to `requirements.txt` — it was missing, so the checks the
  README asks for could not be run on a clean clone.

### CI — added, green

`.github/workflows/ci.yml` runs on every push and PR to `main`. **~1 minute,
all jobs passing.**

| Job | What it does |
|---|---|
| `backend (py3.9)` | install → 16 verdict regressions → contract check → boot API, assert `/api/health` |
| `backend (py3.12)` | same, on the other end of the claimed range |
| `frontend` | `npm ci` → typecheck → `vite build` |

The health assertion is the one worth keeping: it fails if `transitions.json`
goes missing, if the coach library empties, or if the knowledge base loads
nothing — all of which otherwise surface as a blank panel mid-demo. The runner
has no checkpoint, so it also asserts the documented clean-clone path
(`lexical | no checkpoint exported`).

---

## 🚧 Pending

Ordered by how much they'd improve the product per hour spent.

### P0 — Corpus expansion (attempted; the honest result) + 2 pipeline bugs fixed

**Outcome:** the fine-tuned model still loses to the lexical baseline on a *valid*
benchmark, and AegisAI serves the baseline. But the training pipeline now runs.

What happened this session (full account in
[`docs/IMPLEMENTATION-REPORT.md` §7](docs/IMPLEMENTATION-REPORT.md)):

- Built `ml/synth_seeds.py`, a deterministic **no-LLM** generator (Gemini quota is
  exhausted). Expanding 5× improved class balance but the shared phrase banks
  **leak across the leave-archetypes-out split** — the held-out score inflated to
  a meaningless **0.9986**. So the expansion was **reverted**; the committed
  corpus is the original 338 calls, whose split is valid.
- Fixed **two real latent bugs** so a retrain actually completes: `train.py` was
  missing `save_safetensors=False` (every run crashed at the epoch save on MuRIL's
  non-contiguous tensors), and `classification_report` crashed on a split missing
  a class. Both fixed.
- The real unblock remains **LLM-diverse generation** (genuine per-archetype
  vocabulary), which is offline / quota-blocked.

Standing diagnosis (unchanged — the MuRIL checkpoint trains beautifully and then
*loses to a pile of regexes* on unseen archetypes; 0.368 lexical vs 0.221 MuRIL):

| backend | val macro-F1 | **test macro-F1** (held-out archetypes) |
|---|---:|---:|
| lexical baseline | — | **0.368** |
| fine-tuned MuRIL | 0.983 | **0.221** |

The 0.98 is memorisation — 320 synthetic calls give an 8-way classifier enough
surface detail to recognise the *archetype* rather than the *stage*. Per-class
test F1 shows exactly where it collapses:

| stage | test F1 | test support | diagnosis |
|---|---:|---:|---|
| `GREETING` | 0.79 | 44 | fine |
| `FEAR_INDUCTION` | 0.40 | 51 | precision 0.93, recall **0.25** — too conservative |
| `BENIGN` | 0.18 | 27 | needs far more legitimate-call variety |
| `ISOLATION` | 0.20 | 4 | **starved** — 37 caller-side training examples |
| `AUTHORITY_CLAIM` | 0.13 | 15 | confused with `GREETING` |
| `VERIFICATION_DEMAND` | 0.08 | 24 | precision **1.00**, recall 0.04 — barely ever fires |
| `PAYMENT_SETUP` | 0.00 | 2 | **starved** |
| `PAYMENT_EXECUTION` | 0.00 | 4 | **starved** |

**Task:** regenerate a larger corpus — target ~1,000+ calls with materially more
archetypes, weighted hard toward `ISOLATION`, `VERIFICATION_DEMAND`,
`PAYMENT_SETUP`, `PAYMENT_EXECUTION`, and a wider spread of `BENIGN`.
Then rerun `train.py` + `eval_backends.py`.

**The fix is more data, not more epochs.** Do not tune hyperparameters against
this; the split is telling the truth.

Two invariants must stay in lockstep or the served model silently
underperforms:
1. the speaker-tagged `previous [SEP] current` join — `ml/train.py::render`
   **and** `MuRILStageClassifier.predict`;
2. label ordering, which travels inside the checkpoint config and is asserted
   on export.

> ⚠️ **Do not train on Apple MPS.** On torch 2.2 / transformers 4.44 a full run
> completed every step with loss pinned at exactly `ln(8) = 2.079` — the
> uniform-prior loss — and never left initialisation. CPU is the default for
> this reason.

Promotion is automatic once it wins: `load_classifier()` gates on
`backend_comparison.json`, so a better model promotes itself. Force with
`AEGIS_CLASSIFIER=muril` to test.

### P1 — Live audio / ASR (the biggest functional gap)

Nothing is wired. The **contract already anticipates it** — `partial_text`
fields exist, `schema/models.py:336` says *"Audio rides as binary frames"*, and
the `asr:local_fallback` degradation tag is defined — but:

- `routes/session.py::session_socket` is **`receive_json` only**. It does not
  accept binary frames. This is the concrete gap between contract and
  transport.
- No ASR implementation exists anywhere. `SARVAM_API_KEY` is in `.env.example`
  and referenced by nothing.
- `coercion.py` is written to consume pitch variance and pause ratio from ASR
  word timings, and currently runs on lexical features alone with
  `coercion:text_only` recorded and a lower cap.

**Task:** accept binary audio on the WS, run local `faster-whisper` for dev,
swap in Sarvam for the live run, feed word timings into `CoercionTracker`, and
emit `partial_text` on interim results. The engine side is already shaped for
this — it's transport + an ASR adapter.

### P1 — Guardian notification is in-app only

The state machine is complete and correct (`IDLE → ALERTING → ACKNOWLEDGED`,
with the payment circuit breaker gated on it). But **no message actually leaves
the process** — no SMS, no push, no call. The "alert" is a state field the
`/guardian` screen polls.

**Task:** an outbound adapter (SMS/WhatsApp/push) fired on the
`GUARDIAN_ALERTED` event, with the same explicit-degradation discipline as
everything else — if it can't send, tag it, don't pretend.

### P2 — Payment hold is simulated

`attempt_payment` / `cancel_payment` / `approve_payment` are a faithful
in-session circuit breaker, but there is no UPI/bank integration. For the demo
this is the right call; for anything real it's the hard part (and mostly a
regulatory problem, not a code one). **Document it as simulated — don't imply
otherwise in the pitch.**

### ~~P2 — LLM explainer~~ DONE (22 Jul)

Working end to end: `config.py` now loads `.env` (nothing did before), and the
default Gemini model is the rolling alias `gemini-flash-lite-latest` (the old
pinned `gemini-2.0-flash` default is retired upstream and 429s). Explanations
are real prose, still never touch a score, and degrade to templates with
`llm:unavailable` on failure.

### ~~P2 — Dense retrieval~~ DONE (22 Jul)

`sentence-transformers` installed in the venv, MiniLM warm-cached.
`/api/health` reports `backend: dense`, 31 chunks / 4 docs (new
`scam-variants.md` covers investment/KYC/courier/refund-QR families).
`rag:lexical` cleared. Note: dense **script** matching was measured and
rejected — MiniLM can't separate benign from scam on short Hinglish lines —
so the script matcher stays lexical (see `scripts.py` docstring),
gated behind `AEGIS_DENSE_SCRIPTS=1`.

### P3 — Smaller gaps

- **OCR is optional, not bundled.** The pluggable engine ships, but no OCR
  dependency is installed by default (clean-clone / CI stay light). Enable with
  `brew install tesseract` + uncommenting the deps in `requirements.txt`.
- **No persistence.** Sessions are in-memory and die with the process. Fine for
  a demo; a blocker for anything longitudinal.
- **No frontend tests.** Typecheck only. The backend has 16 regression cases;
  the UI has none. This is now the largest remaining gap in the check suite.
- **Real-world transfer unmeasured.** 100% synthetic training data. This is an
  honest limitation to state out loud, not a bug to hide.

---

## Suggested split

These are independent — minimal merge conflict surface.

| Track | Area | Why it's separable |
|---|---|---|
| **A** | P0 corpus + retraining | Touches `ml/` only. Nothing in `services/` or `apps/` |
| **B** | P1 audio/ASR + coercion prosody | Touches `routes/session.py` + a new adapter + `coercion.py` |

Then whoever finishes first takes P1 guardian notifications and the CI action.

**The one shared file to coordinate on is `schema/`.** If you add a field, add
it to `models.py` *and* `types.ts` in the same commit and run
`check_contract.py`. A commit that changes one and not the other fails the
check for whoever pulls next, and they'll think they broke it.

---

## Before you push, always

```bash
.venv/bin/python -m pytest services/api/tests -q   # 16 passed
.venv/bin/python schema/check_contract.py          # contract consistent
npm run typecheck --prefix apps/web                # silent = clean
```

Note the `.venv/bin/python` on the contract check — bare `python3` fails with
`ModuleNotFoundError: pydantic`.
