# AegisAI — Master Task List

**Working agreement:** one task at a time, completed and verified, before the
next. A task is not done because the code exists — it is done when its
acceptance criteria pass and the four gates below are green.

### The four gates (run before every task is marked ✅)

```bash
.venv/bin/python -m pytest services/api/tests -q
.venv/bin/python schema/check_contract.py
npm run typecheck --prefix apps/web
npm run build --prefix apps/web
```

### Legend

| Mark | Meaning |
|---|---|
| ✅ | Done and verified |
| 🔨 | In progress |
| ⬜ | Not started |
| 🔴 | Blocker — nothing downstream can start |
| ⭐ | Research-critical — the paper depends on it |
| 🛡️ | Security-critical |

**Effort** is in focused hours, not calendar time.

---

# PHASE 0 — Foundation
*Goal: a clean, modern, containerised base that the agent layer can be built on.*
**Exit criterion:** `docker compose up` gives Postgres + Neo4j + Qdrant + Redis;
the API runs on Python 3.12; all four gates green; CI enforces them.

### ✅ 0.1 — Rename KAVACH/PRESAGE → AegisAI
**Done 2026-08-23.** 105 files rewritten; `ml/presage/` → `ml/aegis/`,
`ml/kavach/` → `ml/rssie/`; env prefix `PRESAGE_*` → `AEGIS_*` with a
back-compat fallback in `config.py` so existing local `.env` files keep working;
hackathon artefacts archived to `docs/archive/et-hackathon-2026/`.
**Verified:** 84 tests, contract consistent, typecheck + build clean.

### ⬜ 0.2 — Python 3.9 → 3.12 🔴
**Why:** LangGraph, Pydantic v2 features, and current `transformers` need 3.11+.
`.replit` already declares 3.12; the local venv is 3.9. Nothing in Phase 1 can start.
**Do:** new venv on 3.12 · pin `requirements.txt` with hashes · replace deprecated
FastAPI `@app.on_event` with a `lifespan` handler · fix `datetime.utcnow()`
deprecations · re-run the full suite.
**Accept:** all 84 tests pass on 3.12 · CI matrix is 3.11 + 3.12 · no deprecation
warnings from our own code. **Effort:** 4–6 h.

### ⬜ 0.3 — Repo restructure to the target layout
**Why:** the agent layer needs a home; `ml/` needs splitting.
**Do:** `git mv` only (history matters for the defence). Create
`services/api/agents/`, `services/api/orchestration/`, `services/api/stores/`,
`packages/aegis_core/`, `research/`, `infra/`. Split `ml/` into
`corpus/ training/ evaluation/`. One commit per move.
**Accept:** structure matches ARCHITECTURE.md §6 · gates green after **each**
move · `git log --follow` still traces every moved file. **Effort:** 4 h.

### ⬜ 0.4 — Docker Compose dev stack 🔴
**Why:** Postgres, Neo4j, Qdrant and Redis are all Phase-3 dependencies, and
Docker is not installed on this machine yet.
**Do:** install Docker Desktop · `infra/compose/dev.yml` with pinned image tags,
named volumes, healthchecks · `make up` / `make down` / `make reset` · seed script.
**Accept:** one command brings all four up healthy · API connects to each and
reports it on `/api/health` · **with the stack down, the API still boots and
serves** using SQLite + NetworkX + the in-house vector store, tagging `degraded`.
**Effort:** 6–8 h.

### ⬜ 0.5 — Config & secrets hygiene 🛡️
**Do:** migrate `config.py` to `pydantic-settings` · move `ml/artifacts/` (3.5 GB)
out of the git tree to DVC or local object storage · rotate the Gemini key ·
`.env.example` covering every new service · document every variable.
**Accept:** no secret in git (verified: history is already clean) · repo clone
under 200 MB · every setting has a default that boots offline. **Effort:** 4 h.

### ⬜ 0.6 — CI/CD hardening
**Do:** GitHub Actions: lint (`ruff`), format (`black`), types (`mypy` on
`agents/` + `orchestration/`), pytest with coverage gate, contract check,
frontend typecheck + build, `pip-audit`/`npm audit`.
**Accept:** CI green on a clean clone · coverage gate at 70% and rising · a PR
that breaks the contract fails. **Effort:** 4 h.

### ⬜ 0.7 — `CLAUDE.md` + contributor docs
**Why:** the invariants in INVENTORY.md §5 must be enforceable by anyone (human
or agent) touching the repo.
**Accept:** `CLAUDE.md` states the six invariants, the four gates, and the
"what done means" checklist. **Effort:** 2 h.

---

# PHASE 1 — Agent Architecture & Orchestration
*Goal: the skeleton every later phase plugs into.*
**Exit criterion:** an investigation can be submitted, routed by input type
through a LangGraph graph, executed with parallel fan-out, traced, persisted,
and streamed to the UI — even if only three agents exist.

### ⬜ 1.1 — `InvestigationState` + `AgentResult` in `schema/` 🔴⭐
**Why:** the contract every agent reads and writes. Getting this wrong is the
most expensive mistake available.
**Do:** implement ARCHITECTURE.md §3 in `schema/models.py` **and**
`schema/types.ts` in one commit · extend `check_contract.py` to verify the new
enums · new fields `Optional[...] = None` so existing mock frames stay valid.
**Accept:** contract check passes · a round-trip test serialises a full state
through Pydantic → JSON → TypeScript type · old `StateFrame` mocks still validate.
**Effort:** 6 h. **Depends:** 0.2.

### ⬜ 1.2 — Agent base protocol + registry 🔴
**Do:** `agents/base.py` — `Agent` protocol (`name`, `version`, `can_handle`,
`run`), `AgentResult`, `AgentContext` (timeout, cancellation, org, budget) ·
`agents/registry.py` with decorator registration and version pinning.
**Accept:** a toy agent registers, runs, and returns a valid `AgentResult` ·
registry rejects duplicate names and unversioned agents · a raising agent yields
`status="error"` **without** propagating. **Effort:** 5 h. **Depends:** 1.1.

### ⬜ 1.3 — LangGraph orchestrator skeleton 🔴⭐
**Do:** `orchestration/graph.py` — build the graph from the registry ·
conditional routing on `input_types` · parallel fan-out with `asyncio.gather` ·
per-node timeout/retry from `policy.py` · checkpointing so a crashed
investigation resumes · `trace.py` recording a `TraceSpan` per node.
**Accept:** graph compiles and renders to Mermaid via a CLI · a 3-node graph
executes with one node deliberately timing out and the investigation still
completes, `degraded` populated · trace shows per-node latency · **deterministic:
same input + fixed seeds ⇒ same output** (this is what makes ablations valid).
**Effort:** 12–16 h. **Depends:** 1.2.

### ⬜ 1.4 — Input Classification Agent 🔴
**Do:** classify by magic bytes first, extension second, content third — never
by user-supplied MIME. Handle image, screenshot, PDF, email/EML, URL, APK, audio,
video, phone, UPI ID, plain text. Emits `input_types` driving all routing.
**Accept:** ≥98% accuracy on a 200-item fixture covering every type plus 20
adversarial ones (APK renamed `.jpg`, HTML renamed `.pdf`) · ambiguous input
returns multiple types rather than guessing · unknown type routes to the text
agent, never crashes. **Effort:** 8 h. **Depends:** 1.2.

### ⬜ 1.5 — Evidence store (Postgres) 🔴
**Do:** tables `investigations`, `evidence_items`, `agent_results` (JSONB),
`findings`, `entities`, `case_entities` · Alembic migrations · repository layer
with `org_id` isolation enforced **in the repository, not the route** · SQLite
fallback preserved.
**Accept:** every agent result persisted and re-readable · a full state rebuilds
from the DB · a cross-org read is impossible (test proves it) · migrations run
forward and back. **Effort:** 10 h. **Depends:** 0.4, 1.1.

### ⬜ 1.6 — Investigation lifecycle API
**Do:** `POST /api/investigations` (multipart + JSON) · `GET /{id}` ·
`GET /{id}/stream` (SSE progress) · `GET /{id}/report[.pdf]` ·
`GET /{id}/trace` · `DELETE /{id}` (GDPR-style erasure).
**Accept:** submit → live per-node progress → final report, end to end ·
SSE reconnect resumes without duplicate events · 4 MB upload cap enforced ·
OpenAPI documents every route. **Effort:** 8 h. **Depends:** 1.3, 1.5.

### ⬜ 1.7 — Adapt the inherited engine into agents ⭐
**Why:** KAVACH's engine is the crown jewel. It must become agents **without
being rewritten** — a rewrite would lose the 84 tests that make it trustworthy.
**Do:** thin adapters wrapping `engine/classifier.py`, `coercion.py`, `threat.py`,
`twin.py`, `passport.py`, `spoofing.py`, `scripts.py` as registered agents
emitting `AgentResult`. Internals untouched.
**Accept:** all 84 existing tests still pass unmodified · each adapter emits a
valid `AgentResult` · the existing live-call flow works through the new
orchestrator and through the old path. **Effort:** 10 h. **Depends:** 1.3.

### ⬜ 1.8 — Async job system (Redis + Celery)
**Do:** worker service · queues by cost class (`fast`, `slow`, `sandbox`) ·
result backend into the evidence store · dead-letter + retry policy.
**Accept:** a 90-second APK-shaped stub runs off the request path · API returns
in <1 s with a pending investigation that later completes · worker crash loses
no work. **Effort:** 8 h. **Depends:** 0.4, 1.5.

### ⬜ 1.9 — Frontend: investigation launcher + live progress
**Do:** `/investigate` — evidence-type chooser, drag-drop upload, consent
copy · live agent-progress list driven by SSE · result hand-off to the report page.
**Accept:** every input type submittable · progress reflects real node
completion, not a fake timer · degraded agents shown as degraded, not hidden ·
keyboard accessible, works light + dark. **Effort:** 12 h. **Depends:** 1.6.

---

# PHASE 2 — Evidence Agents
*Goal: "upload anything" becomes true. This phase produces the defensible MVP.*
**Exit criterion:** a screenshot containing a phishing URL and a UPI ID produces
a complete, evidence-backed report with no hand-waving.

### ⬜ 2.1 — Text / Message Agent
**Do:** normalise SMS, WhatsApp exports, email bodies, pasted text · language
detect (English/Hindi/Hinglish, reusing `ingest/language.py`) · sender-pattern
analysis (shortcode, alphanumeric header, spoofed sender ID).
**Accept:** WhatsApp export parses into turns with timestamps · Hinglish
detection matches the existing detector · structured output feeds the social-eng
agent. **Effort:** 8 h.

### ⬜ 2.2 — OCR Agent upgrade (PaddleOCR)
**Why:** Tesseract is weak on Devanagari and on screenshot layouts.
**Do:** PaddleOCR primary, Tesseract fallback, both behind the existing pluggable
interface · layout-aware extraction preserving reading order · per-block
confidence · bounding boxes retained for the evidence viewer.
**Accept:** measured CER/WER on a 100-screenshot benchmark (English + Hindi +
Hinglish) beats the current backend · a missing PaddleOCR install degrades to
Tesseract and tags it · boxes render in the UI. **Effort:** 10 h.

### ⬜ 2.3 — URL / Domain Investigation Agent 🛡️⭐
**Why:** the most common phishing evidence type, and the highest-risk component
in the system.
**Do — security first:** SSRF guard (block RFC1918, loopback, link-local,
`169.254.169.254`; re-resolve DNS *after every redirect*; cap redirect depth at 5;
scheme allowlist `http|https` only; request timeout; response size cap; dedicated
egress path). **Then** checks: WHOIS + domain age · DNS records · SSL/TLS issuer,
age, validity · redirect chain · shortener expansion · TLD risk · typosquatting
(Levenshtein + homoglyph + keyboard distance against a curated brand list) ·
HTML features (login form, password field, external POST target, obfuscated JS) ·
brand-impersonation via favicon/logo hashing.
**Accept:** 🛡️ **an SSRF test-suite passes** — every private-range and
metadata-endpoint attempt is refused, including via redirect and DNS rebinding ·
domain age correct on 20 known domains · typosquat detector flags
`sbi-secure-login.xyz` vs `onlinesbi.sbi` and does **not** flag legitimate bank
subdomains · every finding carries a source. **Effort:** 20 h.

### ⬜ 2.4 — Email Header Agent
**Do:** parse `.eml` · SPF/DKIM/DMARC verdicts · `Received` hop analysis ·
display-name vs envelope-from mismatch · reply-to divergence · attachment
inventory (analysed, never opened).
**Accept:** correct verdicts on a fixture of 30 emails (legit, spoofed, forwarded)
· hop chain rendered · malformed MIME does not crash. **Effort:** 10 h.

### ⬜ 2.5 — QR Agent
**Do:** decode (pyzbar/OpenCV, multi-code, rotated, low-contrast) · classify
payload (URL, UPI URI, vCard, text, WiFi) · **route the payload back into the
graph** so a QR containing a URL triggers the URL agent.
**Accept:** decodes a 30-image fixture incl. rotated/partial · a UPI QR reaches
the financial agent · a URL QR reaches the URL agent · recursion depth respected.
**Effort:** 6 h. **Depends:** 2.3.

### ⬜ 2.6 — Financial Fraud Agent
**Do:** extend the inherited UPI logic · VPA structure + handle validation ·
beneficiary-name mismatch · amount and urgency extraction · payment-rail
heuristics · classify the fraud pattern across the 12 categories.
**Accept:** VPA parsing correct on 50 synthetic + real-format IDs · pattern
classification ≥85% on a labelled fixture · **a legitimate merchant VPA is not
flagged** (false-positive test is mandatory). **Effort:** 12 h.

### ⬜ 2.7 — Social Engineering Agent ⭐
**Why:** master §6 — the flagship LLM component.
**Do:** 14-label multi-label classifier over master §6's taxonomy (fear, urgency,
authority impersonation, scarcity, reward, threat, trust-building, financial
pressure, emotional manipulation, isolation, remote-access, OTP, credential,
payment request) · **two independent implementations**: (a) fine-tuned
transformer, (b) LLM with strict structured output (JSON schema, refusal on
uncertainty) · reconcile, and record disagreement.
**Accept:** structured output validates against the schema 100% of the time
(retry-on-invalid, never free prose) · per-label F1 reported on a held-out split ·
the two implementations' agreement rate is measured and logged — **this is
research Experiment 2's data**. **Effort:** 16 h.

### ⬜ 2.8 — APK Static Analysis Agent 🛡️
**Do:** **static only**, in a network-less container with a read-only mount and
resource caps · androguard: permissions (flag SMS, accessibility, overlay,
`REQUEST_INSTALL_PACKAGES`), exported components, dangerous API usage, embedded
URLs/domains/IPs, certificate/signer info, obfuscation indicators · extracted
domains routed to the URL agent.
**Accept:** 🛡️ **no code from the APK is ever executed** (asserted by test and
by container config) · correct permission extraction on 10 sample APKs (benign +
known-malicious-family samples from a research set) · a corrupt APK degrades
cleanly · runs on the `sandbox` queue, never in-request. **Effort:** 16 h.
**Depends:** 1.8.

### ⬜ 2.9 — Image Forensics Agent
**Do:** EXIF + metadata · ELA for splice detection · perceptual hashing for
near-duplicate detection across cases · CLIP embeddings for visual similarity ·
logo/brand matching against a curated reference set.
**Accept:** near-duplicate detection links two cases sharing a template
screenshot · brand match correct on a 50-logo fixture · **no deepfake claim is
made** — that stays out until 5.3 has a model and an evaluation (master §9).
**Effort:** 14 h.

### ⬜ 2.10 — Threat Intelligence Agent ⭐
**Do:** pluggable feed adapters (URLhaus, OpenPhish, PhishTank, abuse.ch,
Google Safe Browsing, CERT-In advisories — final list decided at implementation) ·
**cache-first with TTL in Redis** · every record carries `source`, `timestamp`,
`confidence`, `reference` · offline snapshot bundle so the demo works with no
network.
**Accept:** 🛡️ **no fabricated results, ever** — a feed that is down produces
`status="degraded"`, never a guess · cache hit ratio measured · a full
investigation completes with **all** feeds unreachable · provenance rendered in
the report. **Effort:** 14 h. **Depends:** 1.8.

---

# PHASE 3 — Intelligence Layer
*Goal: AegisAI gets a memory, and cases start informing each other.*
**Exit criterion:** investigating a new screenshot surfaces "this UPI ID appeared
in 3 previous investigations" with links to those cases.

### ⬜ 3.1 — Neo4j migration behind the repository interface ⭐
**Do:** graph schema (nodes: PhoneNumber, UPIID, Email, URL, Domain, IP, APK,
QRPayload, Organisation, ScamType, Investigation, Case; edges: OBSERVED_IN,
RESOLVES_TO, PAYS_TO, LINKED_TO, SIMILAR_TO) · Cypher repository implementing the
**existing** `intel/repository.py` interface · dual-write then cut over ·
NetworkX retained as the offline fallback.
**Accept:** every existing `intel` test passes against **both** backends · a
migration script moves current data with zero loss · `/api/health` reports which
backend is live · Neo4j down ⇒ NetworkX fallback + `degraded` tag.
**Effort:** 16 h. **Depends:** 0.4.

### ⬜ 3.2 — Entity resolution & canonicalisation 🔴
**Why:** `+91 98765 43210`, `9876543210` and `+919876543210` must be one node, or
the graph is worthless.
**Do:** canonical forms per entity type (E.164 phones, lowercase VPA, registrable
domain via public-suffix list, normalised email) · deterministic ID derivation ·
merge policy with an audit trail.
**Accept:** 500-item fixture canonicalises correctly · idempotent (re-ingesting a
case creates no duplicates) · merges are reversible and logged. **Effort:** 10 h.

### ⬜ 3.3 — Cross-case memory ⭐
**Do:** on every entity, compute prior-observation count, first/last seen,
associated scam types, linked case IDs (respecting org boundaries) · surface as
`graph_context` in state and as evidence findings.
**Accept:** "previously observed in N investigations" is correct and links
resolve · **org isolation holds** — org A never sees org B's cases (test proves
it) · a globally shared anonymised layer is opt-in, not default. **Effort:** 10 h.
**Depends:** 3.1, 3.2.

### ⬜ 3.4 — Qdrant migration + hybrid retrieval
**Do:** Qdrant collections for knowledge chunks and case embeddings · hybrid
dense + BM25 with reciprocal-rank fusion · per-org payload filtering · in-house
store retained as fallback.
**Accept:** retrieval quality measured (Recall@5, MRR) against the current store
on a fixed query set — **and it must win**, or we keep the incumbent and say so ·
citations still exact · Qdrant down ⇒ fallback + tag. **Effort:** 12 h.

### ⬜ 3.5 — RAG corpus expansion ⭐
**Why:** 31 chunks over 4 documents is a demo, not a knowledge base.
**Do:** ingest CERT-In advisories, RBI circulars, MHA/I4C material, NPCI UPI
safety docs, curated public scam-pattern write-ups, the project's own scam
taxonomy · chunking with metadata (source, date, jurisdiction, authority) ·
licence review per source.
**Accept:** ≥1,500 chunks from ≥8 sources · every chunk carries a resolvable
citation · **no invented citations** (test: assert every returned citation
resolves to a real chunk) · retrieval evaluated on 50 hand-written questions.
**Effort:** 16 h.

### ⬜ 3.6 — Graph analytics on Neo4j ⭐
**Do:** port community detection, centrality and link prediction from NetworkX to
Neo4j GDS · cluster risk scoring · "kingpin" identification.
**Accept:** results match the NetworkX implementation on the same fixture
(regression guard) · runs on 100k+ nodes within budget · clusters render in the UI.
**Effort:** 12 h. **Depends:** 3.1.

### ⬜ 3.7 — Graph-derived risk features ⭐
**Do:** expose degree, cluster risk, distance-to-known-fraud, prior-observation
count, shared-infrastructure count as numeric features for the ML risk model.
**Accept:** features present in `risk_features` · **leak-free** — features are
computed from data available *before* the case being scored (this is where graph
research quietly cheats; guard it with a temporal split test). **Effort:** 8 h.
**Depends:** 3.3, 3.6.

---

# PHASE 4 — ML Risk Engine & Evidence Fusion
*Goal: the risk number stops being hand-weighted and starts being learned,
calibrated, and explainable.*
**Exit criterion:** a calibrated model produces the score, SHAP produces the
evidence, and the LLM only writes prose around them.

### ⬜ 4.1 — Feature assembly contract 🔴⭐
**Do:** a typed feature registry — every feature declares name, type, range,
producing agent, and a null policy. `FeatureVector` is built deterministically
from `agent_results`, with explicit handling for missing agents (a skipped APK
agent must not read as "clean").
**Accept:** ~80 features registered and documented · missing-agent handling is
explicit and tested · the same state always yields the same vector ·
**feature drift is detectable** (schema hash committed). **Effort:** 10 h.

### ⬜ 4.2 — Labelled training set assembly ⭐
**Do:** join the multimodal dataset (Phase 8) to feature vectors · **temporal
split** (train on earlier, test on later) plus a held-out-family split so
memorising a scam template does not inflate scores · document the exact split.
**Accept:** splits reproducible from a seed · **zero leakage** proven by a test
that asserts no entity appears in both train and test · class balance reported.
**Effort:** 8 h. **Depends:** 4.1, 8.2.

### ⬜ 4.3 — Baseline models ⭐
**Do:** Logistic Regression (interpretable floor), Random Forest, XGBoost,
LightGBM · identical splits, identical features · hyperparameter search logged.
**Accept:** all four trained and evaluated · results committed as JSON in
`research/results/` · a rules-only and an LLM-only baseline included (needed for
Experiment 2). **Effort:** 12 h. **Depends:** 4.2.

### ⬜ 4.4 — Probability calibration 🔴⭐
**Why:** a "92/100" shown to a frightened citizen must mean something. Raw
gradient-boosting outputs are not probabilities.
**Do:** isotonic and Platt calibration on a held-out set · reliability diagrams ·
Expected Calibration Error reported.
**Accept:** ECE < 0.05 · reliability diagram committed · the UI number is the
**calibrated** one. **Effort:** 6 h. **Depends:** 4.3.

### ⬜ 4.5 — Anomaly detection
**Do:** Isolation Forest over the feature space to catch novel patterns the
supervised model has never seen; surfaced as a distinct "unusual pattern" finding,
not folded into the main score.
**Accept:** flags synthetic novel-scam injections · false-positive rate on benign
traffic measured and < 2%. **Effort:** 8 h.

### ⬜ 4.6 — Evidence Fusion / Final Judge ⭐
**Do:** reconcile the four scoring paths (ML, rules, graph, LLM) · narrow,
justified dispositive rules · **record disagreement explicitly** · output final
score, calibrated confidence, and fraud category.
**Accept:** disagreement rate between paths measured and logged · a rule can only
floor/ceiling the score with a written justification in code · **benign
regression suite passes** — legitimate bank calls, real courier notifications and
genuine KYC requests must not exceed the warning threshold. **Effort:** 14 h.
**Depends:** 4.4, 3.7.

### ⬜ 4.7 — Explainability Agent ⭐
**Do:** SHAP values → ranked evidence items in plain language · each item carries
confidence and source · the LLM converts them to prose **from the evidence list
only**, with a grounding check that rejects any claim not backed by a finding.
**Accept:** every sentence in the explanation traces to a finding ID · a
hallucination test (feed contradictory evidence) is refused rather than
rationalised · explanations render in Hindi and English. **Effort:** 14 h.
**Depends:** 4.6.

### ⬜ 4.8 — False-positive discipline harness 🔴⭐
**Why:** inherited invariant. For a citizen-facing safety tool, a false accusation
is worse than a miss.
**Do:** a curated benign corpus (real bank IVRs, genuine delivery SMS, actual
government notices, legitimate KYC flows, real merchant QR codes) · CI gate on FPR.
**Accept:** FPR on the benign corpus is measured, published, and **gated in CI** —
a model that raises it cannot be promoted. **Effort:** 10 h.

### ⬜ 4.9 — Model registry + promotion gate
**Do:** generalise the existing `eval_backends.py` pattern into a registry:
version, training data hash, metrics, calibration, FPR · promotion only on
measured improvement · rollback path.
**Accept:** `/api/health` reports the serving model version and its metrics ·
a worse model is refused promotion by the gate (test proves it) · every served
prediction records the model version. **Effort:** 8 h.

---

# PHASE 5 — Multimodal Depth
*Goal: audio, video and documents reach the same standard as text and images.*

### ⬜ 5.1 — ASR upgrade to faster-whisper
**Do:** replace batch Whisper · benchmark WER on Indian-accented English, Hindi
and Hinglish · retain diarization.
**Accept:** WER measured and reported per language · ≥3× realtime on CPU ·
existing call tests pass. **Effort:** 10 h.

### ⬜ 5.2 — Conversation Dynamics Agent ⭐
**Why:** master §21 — the strongest research angle AegisAI has, and it is already
half-built by the inherited engine.
**Do:** generalise the 7-stage arc beyond phone calls to any conversation
(WhatsApp threads, chat logs, email chains) · three layers: linguistic (what),
behavioural (how it progresses), external evidence (which identifiers appear) ·
keep the Digital Twin forecast.
**Accept:** stage classification works on chat transcripts, evaluated separately
from calls · trajectory forecast measured (does it predict escalation?) ·
**this becomes a paper section**. **Effort:** 16 h.

### ⬜ 5.3 — Voice authenticity (research extension, gated)
**Do:** **only if** a suitable dataset and model are secured — anti-spoofing /
synthetic-voice detection (ASVspoof-style).
**Accept:** ⚠️ **not started, and no claim made, until a dataset exists and the
model is evaluated** (master §36). If it is not done, the report says so.
**Effort:** 20 h if pursued. **Status:** conditional.

### ⬜ 5.4 — Video Agent
**Do:** keyframe extraction → image forensics agent · audio track → ASR agent ·
screen-recording detection.
**Accept:** a screen-recorded scam video produces both visual and audio findings ·
runs async. **Effort:** 10 h. **Depends:** 2.9, 5.1, 1.8.

### ⬜ 5.5 — Document Agent (PDF/DOCX)
**Do:** text + layout extraction · embedded link and JS detection · fake-notice
template matching (fake FIR, fake court summons, fake customs notice).
**Accept:** extracts from scanned and native PDFs · flags embedded JS ·
template matching evaluated on a labelled fixture. **Effort:** 10 h.

---

# PHASE 6 — Real-Time
*Goal: live protection, honestly scoped. Master §19 — no covert interception,
ever.*

### ⬜ 6.1 — WebRTC protected call (Mode A) 🛡️
**Do:** browser mic → WebRTC → backend media pipeline · **explicit consent gate**
before capture · persistent visible recording indicator · configurable retention,
default: transcripts only, no raw audio · one-click deletion.
**Accept:** 🛡️ consent cannot be bypassed (test) · indicator visible whenever
capture is active · retention setting honoured and verified · deletion removes
audio **and** derived transcripts. **Effort:** 20 h.

### ⬜ 6.2 — Streaming STT pipeline
**Do:** chunked streaming with partial + final hypotheses · utterance-boundary
detection · backpressure handling.
**Accept:** partials within 500 ms · finals within 1.5 s of utterance end ·
measured, not asserted. **Effort:** 14 h. **Depends:** 5.1, 6.1.

### ⬜ 6.3 — Real-time agent subgraph ⭐
**Do:** a pruned graph meeting a hard latency budget · slow agents moved
off-path and merged into a later frame · reuse the existing 4 Hz `StateFrame`.
**Accept:** **p95 < 400 ms** from final utterance to updated frame, measured
under load · slow agents never block a warning · degradation visible in the UI.
**Effort:** 16 h. **Depends:** 6.2, 1.3.

### ⬜ 6.4 — Live intervention UI
**Do:** real-time risk meter, indicator list, coach lines (delivered verbatim
from the human-reviewed library — the LLM may rank, never write), payment-hold
prompt, guardian alert.
**Accept:** warnings appear within one frame of detection · coach lines are
verbatim from the library (test asserts no generation) · accessible, high-contrast,
usable one-handed under stress. **Effort:** 14 h.

### ⬜ 6.5 — SMS ingestion channel
**Do:** a forwarding webhook (user-configured) and/or a minimal Android companion
that forwards **only user-selected** messages, with explicit permission copy.
**Accept:** 🛡️ opt-in only, per-message or per-sender · no bulk inbox read ·
messages route into the standard investigation graph. **Effort:** 14 h.

### ⬜ 6.6 — SIP/VoIP integration (Mode C) — stretch
**Do:** provider evaluation (legal + technical) · media bridge.
**Accept:** conditional on legal review; **do not claim it until it exists**.
**Effort:** 24 h. **Status:** stretch.

### ⬜ 6.7 — Privacy & retention controls 🛡️
**Do:** per-org retention policy · scheduled purge · data-export and erasure
endpoints · consent audit trail.
**Accept:** purge job verified to delete across Postgres, Neo4j, Qdrant and
object storage — **all four** · erasure request completes end to end.
**Effort:** 10 h.

---

# PHASE 7 — Frontend, Dashboards & UX
*Runs in parallel from Phase 2 onward.*

### ⬜ 7.1 — Design system consolidation — 8 h
Audit `tokens.css`, unify spacing/typography/colour, document components, verify
light + dark and WCAG AA contrast throughout.

### ⬜ 7.2 — Investigation workspace ⭐ — 16 h
The product's centre: evidence panel, live agent progress, findings list, risk
meter, recommended actions. **Accept:** every number on screen is a contract
field — no maths in React (inherited invariant).

### ⬜ 7.3 — Agent trace view (React Flow) ⭐ — 12 h
The investigation graph rendered live: nodes colour by status, click for inputs/
outputs/latency/provenance. **This is what makes the architecture legible to an
examiner in 30 seconds.**

### ⬜ 7.4 — Knowledge graph explorer (Cytoscape) ⭐ — 14 h
Interactive entity graph, expand-on-click, filter by type/risk/date, path
highlighting between entities, jump to linked cases.

### ⬜ 7.5 — Evidence timeline — 8 h
Chronological view of what was found when, with source attribution.

### ⬜ 7.6 — Analyst / LEA dashboard — 14 h
Case queue, cluster view, hotspot map (existing Leaflet), triage workflow,
bulk export.

### ⬜ 7.7 — Model & evaluation dashboard ⭐ — 12 h
Live metrics, confusion matrix, calibration curve, per-agent success rates,
latency percentiles, ablation results. **Doubles as a paper figure source.**

### ⬜ 7.8 — Admin, RBAC & audit UI — 8 h
Org management, roles, append-only audit log viewer, retention settings.

### ⬜ 7.9 — Accessibility, responsive, i18n — 12 h
WCAG 2.1 AA audit, keyboard paths, screen-reader labels on the map and graph,
mobile layouts, **Hindi UI** (the users who need this most are not
English-first).

### ⬜ 7.10 — Frontend test suite — 10 h
Vitest + Testing Library for logic, Playwright for the three critical flows
(submit → report, live call, graph explore).

---

# PHASE 8 — Datasets & Model Training
*Runs in parallel from Phase 2. See `DATASETS.md` for the full strategy.*

### ⬜ 8.1 — Dataset schema + data card ⭐ — 8 h
Unified record schema, licence, PII policy, provenance per item, a published
data card.

### ⬜ 8.2 — Multimodal fraud corpus ⭐🔴 — 40 h
12 categories × text, screenshots, URLs, QR payloads, synthetic identifiers.
Target ≥10,000 labelled items. **This is the paper's headline contribution.**

### ⬜ 8.3 — Synthetic screenshot pipeline ⭐ — 16 h
Programmatic rendering of scam messages into realistic SMS/WhatsApp/email
screenshots with varied devices, themes, fonts and noise — gives OCR and vision
agents training data at scale, with perfect labels.

### ⬜ 8.4 — URL/domain dataset ⭐ — 12 h
PhishTank/OpenPhish positives, Tranco top-N negatives, feature extraction,
**temporal split** (train on older, test on newer — phishing is non-stationary).

### ⬜ 8.5 — Conversation corpus expansion + full retrain ⭐ — 24 h
Grow from 1,692 to ≥8,000 calls; add chat-shaped conversations; run the
**full-corpus retrain that has never been executed** (~2 h CPU, more on GPU).

### ⬜ 8.6 — Annotation guidelines + inter-annotator agreement ⭐ — 12 h
Written guidelines, ≥2 annotators on a 500-item overlap, Cohen's κ reported.
**A paper without IAA is a paper with an unanswerable reviewer question.**

### ⬜ 8.7 — Fine-tuning runs ⭐ — 30 h
(a) stage classifier retrain, (b) social-engineering multi-label transformer,
(c) optional LoRA on a small open LLM for structured extraction — **only if it
beats prompting**, measured.

### ⬜ 8.8 — Dataset release package — 8 h
Anonymised, licensed, versioned, with a reproduction script.

---

# PHASE 9 — Research Evaluation
*See `RESEARCH.md`. Nothing here can start before Phase 4 completes.*

### ⬜ 9.1 — Evaluation harness ⭐🔴 — 12 h
One command reproduces every number in the paper. Fixed seeds, fixed splits,
results as committed JSON.

### ⬜ 9.2 — Experiments 1–8 ⭐ — 40 h
The eight comparisons from master §28.

### ⬜ 9.3 — Ablation study ⭐ — 20 h
Remove KG / RAG / ML / social-eng / fusion, one at a time.

### ⬜ 9.4 — Latency & cost benchmark ⭐ — 10 h
Per-agent and end-to-end percentiles; token and rupee cost per investigation.
**Master §36: no real-time claim without measured latency.**

### ⬜ 9.5 — Explanation quality human evaluation ⭐ — 14 h
Rubric, ≥3 evaluators, ≥100 explanations, agreement reported.

### ⬜ 9.6 — Robustness & adversarial ⭐ — 16 h
Obfuscated text, homoglyphs, image perturbation, prompt injection **inside the
evidence** (a screenshot containing "ignore previous instructions" must be
treated as data — this is a genuine and demonstrable contribution).

### ⬜ 9.7 — Paper draft, figures, repro package ⭐ — 40 h
Target: IEEE/Springer/Scopus. Figures generated by the harness, never drawn by
hand.

---

# PHASE 10 — Hardening & Deployment

### ⬜ 10.1 — Security review 🛡️🔴 — 16 h
Full pass on SSRF, sandboxing, upload validation, authz on every route, tenant
isolation, secret handling, dependency audit, log sanitisation. **Gate before
any public deployment.**

### ⬜ 10.2 — Observability — 10 h
Structured logs with case correlation IDs, OpenTelemetry traces (the agent graph
maps naturally onto spans), Prometheus metrics, error tracking.

### ⬜ 10.3 — Containerisation & deploy — 12 h
Multi-stage images, compose for prod, one-command deploy, backup/restore
runbook.

### ⬜ 10.4 — Load & resilience testing — 10 h
Concurrent investigations, dependency-failure drills (kill Neo4j mid-run and
assert the investigation still completes).

### ⬜ 10.5 — Demo, seed data & documentation — 14 h
Reproducible seeded demo, scripted walkthrough, API docs, architecture docs,
viva/defence deck.

---

# Timeline

Assumes **~18 focused hours/week**. Adjust to your academic calendar; the
*sequence* matters more than the dates.

| Phase | Weeks | Approx. dates | Hours | Milestone |
|---|---|---|---|---|
| 0 — Foundation | 1–2 | Aug 24 – Sep 6 | ~30 | Modern, containerised base |
| 1 — Agent architecture | 3–5 | Sep 7 – Sep 27 | ~75 | **M1: end-to-end investigation through LangGraph** |
| 2 — Evidence agents | 6–10 | Sep 28 – Nov 1 | ~130 | **M2: defensible MVP — upload anything, get a real report** |
| 3 — Intelligence layer | 11–13 | Nov 2 – Nov 22 | ~85 | **M3: cross-case memory works** |
| 4 — ML risk engine | 14–16 | Nov 23 – Dec 13 | ~90 | **M4: calibrated, explainable scoring** |
| 5 — Multimodal depth | 17–18 | Dec 14 – Dec 27 | ~65 | Audio/video/docs at parity |
| 6 — Real-time | 19–21 | Dec 28 – Jan 17 | ~110 | **M5: live protected call** |
| 7 — Frontend | 6–22 (parallel) | Sep 28 – Jan 24 | ~115 | Investigation workspace + graph + trace |
| 8 — Datasets & training | 6–20 (parallel) | Sep 28 – Jan 10 | ~150 | **M6: released multimodal dataset** |
| 9 — Research evaluation | 20–24 | Jan 4 – Feb 7 | ~150 | **M7: paper draft + repro package** |
| 10 — Hardening & deploy | 22–24 | Jan 18 – Feb 7 | ~60 | **M8: deployed, secured, demoable** |

**Total ≈ 1,060 hours over 24 weeks.** That is a genuine two-person capstone, or
one person working hard. See "Descoping" below — it is a feature, not a failure.

### Critical path

```
0.2 → 1.1 → 1.2 → 1.3 → 1.5 → 2.x → 3.1/3.2 → 4.1 → 4.2 → 4.3 → 4.4 → 4.6 → 9.1 → 9.2 → 9.7
```

Everything else can slip without stopping the paper. **1.1 (`InvestigationState`)
and 4.4 (calibration) are the two tasks where a mistake is most expensive.**

### Descoping ladder — cut from the bottom

If time runs short, drop in this order. Each cut is defensible in a viva
*provided it is stated honestly*:

1. 6.6 SIP/VoIP · 5.3 voice authenticity (already conditional)
2. 5.4 video · 6.5 SMS channel
3. 2.8 APK agent (highest effort-to-marks ratio)
4. 4.5 anomaly detection
5. 3.6 Neo4j GDS analytics (keep NetworkX — it already works)

**Never cut:** 1.1, 1.3, 2.3, 2.7, 4.4, 4.8, 8.6, 9.1, 9.3, 9.4, 10.1.
Those are the difference between a research project and a demo.

---

# Working agreement

1. **One task at a time.** No parallel half-finished work outside the explicitly
   parallel phases (7, 8).
2. **Four gates before ✅.** No exceptions.
3. **Every agent ships with its false-positive test.** Not "later".
4. **No claim without a measurement.** If latency is not measured, the word
   "real-time" is not used. If a model is not evaluated, its capability is not
   advertised. (Master §36.)
5. **Degradation is explicit.** New dependency ⇒ new fallback ⇒ new `degraded` tag.
6. **The contract changes in one commit.** `models.py` + `types.ts` + sync + check.
7. **Update this file as you go.** ⬜ → 🔨 → ✅, with the verification output
   recorded in the commit message.
