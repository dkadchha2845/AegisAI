# AegisAI — Master Task List

> **Status: Phase 0 complete. Phase 1 started — 1.1 done and verified
> end-to-end. Awaiting your go-ahead for 1.2.**
> Last updated 2026-08-24 · `main` @ `99c7277` + uncommitted 1.1 · 154 tests ·
> all four gates green · ruff + mypy clean · coverage 66.70% vs the 65% gate

---

## Working agreement

Set by the project owner on 2026-08-24, and binding on every iteration:

1. **A complete task-list file** (this file) is produced after each iteration.
2. **End-to-end verification** that the thing actually works — the running
   application, not just unit tests.
3. **Only then** is a task ticked.
4. **No further phase or step begins without an explicit instruction.**

### Why 3 is not ceremony

Phase 0 was ticked on 129 passing unit tests. Running the actual application
afterwards found **three defects those tests could not see**:

| Defect | Why tests missed it |
|---|---|
| Every live frame and every analysis falsely tagged `clf:lexical_fallback` — the UI told citizens the system was degraded while the good model was serving | Two call sites compared `backend != "muril"`; the fused backend serves MuRIL under another name. Unit tests asserted verdicts, not degradation tags |
| Evidence packages and police complaints still issued as `KVCH-…` (KAVACH) | No test asserted the brand of a user-facing identifier |
| **Demo login was broken on any existing database** — the screen advertised `admin@aegis.local`, the DB held `admin@kavach.local`, and seeding returned early because the user table was non-empty | Tests seed a *fresh ephemeral* database, where the buggy branch behaves identically |

All three are fixed and pinned by regression tests. The third was a genuine
data-migration bug in the rename that would have hit a real deployment.

---

**Definition of done:** a task is not done because the code exists — it is done
when its acceptance criteria pass, the four gates below are green, **and the
behaviour has been exercised in the running system.**

### The four gates (run before every task is marked ✅)

```bash
make gates
```

Or individually:

```bash
.venv/bin/python -m pytest services/api/tests -q
.venv/bin/python schema/check_contract.py
npm run typecheck --prefix apps/web
npm run build --prefix apps/web
```

`make check` adds lint and types. `make up` starts the dev stack; `make status`
shows what the API can actually reach.

### The end-to-end check (run before every task is ticked)

```bash
colima start && make up     # backing stores
make api                    # :8000
make web                    # :5173
```

Then exercise the real path the task touched — submit an analysis, run a live
session, sign in, open the intel console — and read `/api/health` and the
browser console. A green suite plus an unexercised feature is not a done task.

---

## Phase 0 — verified end-to-end 2026-08-24

Evidence from the running system, not from the test suite:

| Check | Result |
|---|---|
| Dev stack | 4/4 healthy in ~7 s; verified by real Cypher query, `psql` version, `redis-cli PONG`, Qdrant version — not TCP handshakes |
| API boot | lifespan `warm()` runs; `classifier: fused`, `loaded: true`, `retrieval: dense` (31 chunks), twin fitted, 14 coach lines, `degraded: []` |
| Landing + Analyze UI | Renders as AegisAI; **no console errors** |
| Real scam analysis | Score **91**, CRITICAL, stage `verification demand`, known-fraud-infrastructure match; entities auto-extracted (UPI, CBI, narcotics, Aadhaar, RBI, Delhi) |
| **False-positive discipline** | Bank debit **17.2**, delivery **7.5**, KYC reminder **36.6** — all CALM/WATCH, all `LIKELY_LEGITIMATE` |
| Live session arc | `AUTHORITY_CLAIM → FEAR_INDUCTION → ISOLATION → VERIFICATION_DEMAND`, threat 33.9 → 61.8, Digital Twin forecasting time-to-payment |
| Auth + RBAC | All 4 demo roles authenticate; wrong password rejected; browser login lands on intel console as ANALYST |
| Intel console | 9 clusters, 9 campaigns, 114 cases, 47 linked entities, force graph renders |
| Evidence report | `200`, id `AGIS-F0F8F8CB942A` |
| Stack **down** | API still boots and answers; all four stores report unreachable; service still `ok` |
| CI | Green on GitHub (run `32659645342`) |

**Known accuracy gap observed, not a regression:** on the final turn
("RBI supervised account mein 50000 transfer kariye") the classifier returned
`AUTHORITY_CLAIM` rather than `PAYMENT_SETUP` — a miss on the most decisive
turn. Consistent with the known English/short-input weakness and with BENIGN
scoring F1 0.340. Belongs to Phase 4 (calibration) and Phase 8 (corpus).

**Left in the dev database:** the pre-rename `@kavach.local` accounts and a
stale `kavach` org still exist alongside the new ones. Harmless — nothing
references them, no cases are attached — but they are yours to delete if you
want a clean slate:
`rm aegis.db` (it reseeds on next boot; there are 0 case records).

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

### ✅ 0.2 — Python 3.9 → 3.12
**Done 2026-08-23.** Migrated to **Python 3.12.14** (homebrew `python@3.12`).

| | 3.9 (before) | 3.12 (after) |
|---|---|---|
| torch | 2.2.2 | 2.13.0 |
| transformers | 4.44.2 | 4.57.6 |
| sentence-transformers | 5.1.2 | 5.7.0 |
| numpy | 1.26.4 | 2.5.2 |
| networkx | 3.2.1 (capped <3.3 for 3.9) | 3.6.1 (cap removed) |
| scikit-learn | 1.6.1 | 1.9.0 |

**Changes:** `@app.on_event("startup")` → a `lifespan` async context manager in
`services/api/main.py` · `datetime.utcnow()` → a `_utcnow()` helper in
`models_db.py` preserving naive-UTC column semantics exactly, and
`datetime.now(timezone.utc)` in `intel/repository.py` · networkx cap removed ·
CI matrix `3.9, 3.12` → `3.11, 3.12` (floor set by LangGraph) · README,
requirements and INVENTORY updated.

**Verified:** 84 tests pass on 3.12 · deprecation warnings from our own code
went **41 → 0** (the one remaining is third-party: starlette's testclient
wanting httpx2) · contract consistent · frontend typecheck + build clean ·
**the fused MuRIL classifier produces bit-identical predictions on 3.9 and
3.12** across a 6-case Hindi/English probe, so the interpreter and dependency
jump introduced no behavioural drift.

**Note:** the old `.venv39-old` is kept until the next commit lands, then
deleted. Hash-pinning of `requirements.txt` was deferred to task 0.5, which
owns dependency and secrets hygiene.

### ✅ 0.3 — Repo restructure to the target layout
**Done 2026-08-23**, in two commits.

**0.3a — `ml/aegis/` → `packages/aegis_core/`, now an installed package.** It
held the single source of truth for the eight stages and was reached through
four copies of `sys.path.insert(0, ml/)`. Both API import sites wrap it in
`try/except ImportError` with a fallback that defines the *same eight labels*
but an **empty `BY_LABEL`** — so a broken path silently lost every threat weight
while the classifier kept returning plausible labels. Now `-e ./packages/aegis_core`
in requirements; the four aegis-only path hacks are gone.

**0.3b — `ml/` split into `corpus/ training/ evaluation/`.** The hazard was
paths, not imports: every script derived data locations from
`Path(__file__).parent` assuming that was `ml/`. Each now anchors on a named
`ML_DIR` and runs from any working directory.

Also scaffolded `services/api/{agents,orchestration,stores}`, `services/worker`,
`research/`, `infra/` — each with a contract, not a placeholder.

**Verified:** `git log --follow` traces moved files back to their original
commits · every computed data path asserted to resolve to a real file (this
caught `eval_backends.py` still importing `ml.train`) · 11 new tests in
`test_domain_imports.py` assert the real package serves, not the fallback.

### ✅ 0.4 — Docker Compose dev stack
**Done 2026-08-23.** Runtime is **colima + docker CLI** (brew formulae), not
Docker Desktop — it needs no admin rights, which matters because installing the
cask requires a password. `infra/compose/dev.yml` + a root `Makefile`.

| Service | Pinned | Healthcheck |
|---|---|---|
| PostgreSQL | 16.6-alpine | `pg_isready` |
| Neo4j | 5.26.0-community | `cypher-shell 'RETURN 1'` — a TCP probe reports healthy while writes still fail |
| Qdrant | v1.12.5 | its own binary; the image is distroless, so no curl/wget exists |
| Redis | 7.4-alpine | `redis-cli ping` |

`services/api/stores/probe.py` reports each store on `/api/health` under
`infrastructure`, cached (10 s TTL) and bounded (0.35 s timeout) so four dead
stores cannot slow the request path. `reachable` and `in_use` are tracked
**separately**: Postgres being up does not mean the API writes to it yet, and
claiming otherwise would overstate the system.

**Verified — both directions:**
- `make up` → all four healthy in ~7 s; confirmed independently, not by TCP
  handshake alone (real Cypher query, `psql` version, `redis-cli PONG`,
  Qdrant `/`).
- Stack **down** → API boots and answers, `classifier: fused`,
  `retrieval: dense`, `degraded: []`.
- **113 tests pass in both states.** 9 new in `test_stores.py`, written to be
  meaningful whether or not a stack exists, since CI has none.
- Volume persistence proven by writing markers, `make down`, `make up`, reading
  them back.
- `/api/health` measured at 1.1 ms per call with the cache warm.

**Note:** absence of the stack is deliberately **not** a `degraded` tag — until
Phase 3 routes work to these stores, a clean clone with no Docker is the
documented default, and crying wolf there trains people to ignore the field.
`degraded_tags()` grows a case per store as each migrates.

### ✅ 0.5 — Config & secrets hygiene 🛡️
**Done 2026-08-24.** One acceptance criterion was **based on a false premise and
is corrected here**: "repo clone under 200 MB · move `ml/artifacts/` out of the
git tree to DVC". Measured, the clone is **3.4 MiB packed**. The 3.5 GB is
entirely gitignored working-tree data and was never in history. DVC would have
added a remote, a lockfile and a workflow to solve a problem that does not
exist, so it was not adopted.

The real artifact problem turned out to be different, and worse. Investigating
the 3.5 GB surfaced that **`stage-classifier/metrics.json` claims macro-F1
0.269 for a checkpoint that actually measures 0.767** — and it is one of only
two artifact files committed to git. Re-running the promotion gate confirmed
0.7672 reproduces exactly, so the committed file was stale. This is the *second*
time a metric file has drifted from its model here (a stale
`backend_comparison.json` at 0.221 once pinned serving to the lexical fallback
for weeks).

Fixed structurally rather than by editing a number:
- **`ml/evaluation/manifest.py`** — records measured scores bound to a **SHA256
  fingerprint of the exact weights, config and tokenizer**. A metrics file
  cannot go stale unnoticed once it carries the identity of what it measured.
- `eval_backends.py` writes it; `make verify-checkpoint` checks it. Verified it
  detects a **single appended byte** in `config.json`.
- `metrics.json` is now untracked — it is write-only (nothing reads it) and was
  pure stale documentation in git. The manifest is the tracked record.
- A stale claim in `.gitignore`'s own comments ("the lexical classifier scores
  *better* on held-out archetypes") was corrected: it is 0.375 vs 0.767.

**Config migrated to pydantic-settings**, which bought validation
(`AEGIS_PG_PORT=abc` now fails at startup naming the field) and, more usefully,
**declarative `PRESAGE_*` back-compat via `AliasChoices`**. That immediately
exposed a live bug: `engine/ocr.py` read `os.getenv("AEGIS_OCR")` directly,
bypassing the alias, so an un-migrated `.env` using `PRESAGE_OCR` silently fell
back to tesseract. Now routed through `settings`.

`.env.example` completed — 11 undocumented settings added, and a dead
`SARVAM_API_KEY` entry removed (no code has ever read it; documenting a
credential nothing uses only invites someone to paste a real one).

**Verified:** 129 tests pass · 11 new in `test_config.py` assert every setting
has a default, `.env.example` documents all of them and nothing dead, every
`AEGIS_*` alias carries its `PRESAGE_*` fallback, and bad config fails loudly ·
5 new in `test_checkpoint_manifest.py` catch the two-files-disagree case cheaply.

**⚠️ Left for you:** the Gemini key in the local `.env` still wants rotating
before any public demo. It has never been committed (verified again), so this is
prudence, not remediation — and it is not something I can do on your behalf.

**Also noted for later:** `ml/artifacts/_train/checkpoint-330/` is **2.7 GB of
training intermediates** (a 1.9 GB optimiser state), with weights *different*
from the serving checkpoint. It is only needed to resume that training run.
Deleting it reclaims 2.7 GB — your call, not mine:
`rm -rf ml/artifacts/_train`.

### ✅ 0.6 — CI/CD hardening
**Done 2026-08-24.** Four CI jobs: `lint + types` (fails in seconds, before
anything installs torch), `backend` (3.11 + 3.12 matrix), `frontend`, and an
advisory `audit`. `make check` runs the same locally.

**Ruff is curated toward defects, not opinions.** The default set produced 625
findings, of which ~390 were pyupgrade style and **65 were `B008` flagging
FastAPI's own `Depends()` idiom on every route** — enabling that wholesale would
bury the handful that were real. The curated set found 127; auto-fix cleared 76;
the genuinely defective remainder was fixed by hand:
- dead code in `validate_corpus.py` (an unfinished stage-ordering check),
- three more naive-datetime sites (the class of bug 0.2 fixed elsewhere) — one
  of which was left naive **on purpose**, with a `noqa` explaining that EXIF and
  call-log timestamps carry no zone and inventing one would fabricate data,
- two mutable class defaults, annotated `ClassVar` to say they are constants,
- a mid-file import, and a counter-plus-break replaced with `islice`.

Every remaining ignore carries its justification in `pyproject.toml`. The gate
sits at **zero findings**, so a new violation is visible.

**mypy is scoped to `agents/`, `orchestration/`, `stores/`** — strict there, where
every agent implements one protocol and returns one shape. Retrofitting
annotations across the inherited engine is a large change with no defect-finding
payoff today.

**Coverage gate: 65%, and the 70% target was NOT met.** Stating the reason
rather than hiding it: `services/api/engine/features/` is **601 statements at
0%**. It is research-track code imported only by `ml/training/rssie/dataset.py`
and never by the serving path, so the API suite legitimately never touches it.
Omitting it from the report would show ~76% and tell you less, so it stays
visible. The gate is a ratchet — raise it as the real number climbs, never lower
it.

CI also now asserts the **degradation invariant** directly: with no compose
stack on the runner, all four stores must report unreachable *and* the service
must still report `ok`.

**Verified:** ruff clean · mypy clean · 129 tests · coverage 66.32% vs the 65%
gate · `pip-audit`: no known vulnerabilities · the CI health block passes
locally with the stack down.

### ⬜ 0.7 — `CLAUDE.md` + contributor docs
**Why:** the invariants in INVENTORY.md §5 must be enforceable by anyone (human
or agent) touching the repo.
**Accept:** `CLAUDE.md` states the six invariants, the four gates, and the
"what done means" checklist. **Effort:** 2 h.
**Noticed while doing 1.1 — three small drifts, none fixed there, because a
schema commit is not the place to smuggle them:**
1. `CLAUDE.md` still says the gate is "84 tests". It is 154. Harmless (pytest
   does not check counts) but it is the kind of drift this project calls a defect.
2. `pyproject.toml`'s formatter comment points at a `make format-check` target
   that does not exist. Worth adding in 1.2, when `agents/` finally has files
   for it to check — adding it today would pass vacuously.
3. **`.coverage` is a tracked binary** and churns on every test run
   (`git ls-files` confirms it; it is not in `.gitignore`). Belongs with the
   0.5 hygiene pass: `git rm --cached .coverage` and one `.gitignore` line.

---

# PHASE 1 — Agent Architecture & Orchestration
*Goal: the skeleton every later phase plugs into.*
**Exit criterion:** an investigation can be submitted, routed by input type
through a LangGraph graph, executed with parallel fan-out, traced, persisted,
and streamed to the UI — even if only three agents exist.

**Progress: 1 of 9 done** — ✅ 1.1 · next up 1.2 (agent base protocol +
registry), which is blocked on nothing and unblocks 1.3 and 1.4.

> Note on what 1.1 does **not** claim: the contract exists and is enforced by
> the gates, but nothing in the running API imports it yet. The API still emits
> contract-shaped dicts, as it always has. Wiring `InvestigationState` into a
> served path is 1.5 (persistence) and 1.6 (the lifecycle API). The end-to-end
> verification below is therefore "the running system is unharmed and the drift
> guards demonstrably bite", not "an investigation flows through it" — that
> sentence is not available until 1.6, and it will not be written before then.

### ✅ 1.1 — `InvestigationState` + `AgentResult` in `schema/` 🔴⭐
**Done 2026-08-24.** ARCHITECTURE.md §3 implemented in `schema/models.py` and
`schema/types.ts` in one change: 13 models and 6 new enums, appended as a clearly
delimited second section rather than a second file.

**One file, two contracts, two version numbers.** The live-call contract
(`StateFrame` at 4 Hz) and the investigation contract (one submission through the
agent graph) share `models.py` so they share a vocabulary — `InvestigationState`
reuses `ThreatLevel`, `Transcript`, `Stage` and `Verdict` verbatim, because the
band a citizen sees during a live call and the band on their report have to mean
the same thing. But `CONTRACT_VERSION` and `INVESTIGATION_CONTRACT_VERSION` are
separate, so adding an investigation field cannot invalidate a client that only
speaks frames. Both are checked against `types.ts`.

**Decisions worth defending, each pinned by a test:**

| Decision | Why | Alternative rejected |
|---|---|---|
| `risk_score` / `risk_level` / `confidence` are `Optional`, default `None` | An unscored investigation must not render as **0 / CALM** — a false negative wearing a number, on a screen a frightened person is reading. `StateFrame.threat` is Optional for the same reason | `= 0.0`, which reads as "safe" for every queued case |
| `risk_level` is a **field**, not derived in React | Pure-renderer invariant. The live path and the report path must band a 69.6 identically | `threatLevelOf(score)` in the UI, which is how two implementations drift |
| `FraudCategory` has **no** UNKNOWN member | `None` = "not classified yet"; `benign` = "classified, and legitimate". Collapsing them lets an unfinished investigation read as a cleared one | An UNKNOWN member "for safety" |
| Slugs match `DATASETS.md` §3 exactly (`banking_impersonation`, …) | A corpus item and a live classification are then the same string, and the Phase 4 training join needs no mapping table | Prettier `BANKING_IMPERSONATION` values |
| `EntitySet` field names copied from `intel/entities.ExtractedEntities` | The knowledge graph keys nodes off these names; `accounts` vs `bank_accounts` would silently drop an entity class at the Phase 3 boundary — no error, just a fraud link never drawn | Tidier names on the contract |
| `TIRecord.malicious` is **three-valued** | A feed that is down yields `None` + a `degraded` tag, never `False`. "We do not know" has to be representable or the system invents intelligence | `bool`, defaulting False |
| `AgentStatus.SKIPPED` distinct from `OK` | 4.1 must tell "did not run" from "clean", or a skipped APK scan becomes evidence of a safe APK | Folding SKIPPED into OK |
| Timestamps are ISO-8601 `Z` **strings**, not `datetime` | Naive-vs-aware bit this project in 0.2 and again in 0.6. A string ending in `Z` has one representation and survives every round trip identically | `datetime`, and the JSONB/checkpoint round trips that come with it |

**The acceptance criterion "Pydantic → JSON → TypeScript" is now enforced, not
asserted.** `schema/check_contract.py` compares enums; that catches a missing
enum *member* and cannot catch a missing *field*. So `schema/mock_investigation.py`
emits one fully-populated state twice — as `schema/mock-investigation.json`
(validated against Pydantic) and as `apps/web/src/mock/investigation.fixture.ts`,
a literal annotated `: InvestigationState`. Gate three, `npm run typecheck`, then
fails on field-level drift **in both directions**. A JSON fixture cannot do this:
`resolveJsonModule` widens every string to `string`, so the enums would go
unchecked. It has to be emitted as TypeScript.

Verified by breaking it deliberately, three ways:

| Injected fault | Caught by | Message |
|---|---|---|
| `feed_version` added to `TIRecord` in `models.py` only | `npm run typecheck` | `TS2353: Object literal may only specify known properties, and 'feed_version' does not exist in type 'TIRecord'` |
| `feed_version` added to `types.ts` only | `npm run typecheck` | `TS2741: Property 'feed_version' is missing … but required in type 'TIRecord'` |
| Committed fixture edited by hand (`risk_score` 88.4 → 12.0) | `check_contract.py`, exit 1 | `mock-investigation.json is stale — run ./scripts/sync-contract.sh` |

The staleness check exists because this repo has twice been bitten by a metrics
file that outlived the thing it measured. The generator is deterministic — fixed
timestamps, fixed ids — precisely so the comparison is possible.

**What running the application changed about the design.** The false-positive
run was routine; the vocabulary check was not. `RecommendedAction` was drafted as
a closed vocabulary of 11 members. Exercising the real `/api/analyze/text` and
watching the live call showed the shipped system already says things that
vocabulary could not express — most obviously **"Hang up. There is no legal
consequence for ending a call."**, which the UI was printing on screen at
CRITICAL while the enum had no member for it. Three members were added
(`END_THE_CALL`, `DO_NOT_ACT_YET`, `PROVIDE_MORE_EVIDENCE`) and a test now
enumerates every line `engine/analyzer.py::_actions()` can produce and fails if
one has no member — plus a second test failing if the mapping lists a line the
engine no longer produces, so the guard cannot rot into decoration. A closed
vocabulary that cannot say what the product already says is not closed, it is
incomplete, and 1.7 would have found this with a dozen call sites already written
against it.

**Tests:** 22 new in `test_investigation_contract.py` (154 total, was 132).
Round trip · both fixtures current and annotated · generator deterministic ·
`mock-stream.json` and a bare `StateFrame` still validate · out-of-range scores,
negative latency and unknown statuses rejected · each pinned decision above ·
a meta-test asserting **every** enum on the contract is registered in
`check_contract.PAIRS`, so a future enum cannot be added unguarded.

**Verified end-to-end on the running system, not just the suite:**

| Check | Result |
|---|---|
| Four gates | 154 tests · contract consistent (13 enums, 2 versions, 3 fixtures) · typecheck clean · build clean in 1.23 s |
| Also | ruff clean · mypy clean · coverage **66.70%** vs the 65% gate (was 66.32%) |
| Stack | 4/4 healthy; API boot `classifier: fused`, `retrieval: dense` (31 chunks), twin fitted, 14 coach lines, **`degraded: []`** |
| Real scam analysis | **91**, CRITICAL, `LIKELY_SCAM` — identical to the Phase 0 baseline |
| False-positive discipline | bank debit **13.5**, delivery **7.5**, KYC branch reminder **7.5** — all CALM / `LIKELY_LEGITIMATE` |
| Live demo call, in the browser | Full arc to **93 / CRITICAL**, stage `payment execution`; transcript, threat meter, coach banner and report all render from the regenerated `contract.ts` |
| Entities in the report | phone, cbi, crime branch, aadhaar, rbi, Mumbai, parcel, warrant, digital arrest — auto-extracted |
| Analyze page, in the browser | Benign bank debit → "No scam patterns detected", **20**, CALM |
| Auth + console | Signed in as ANALYST (`analyst@aegis.local`); dashboard and intel console render — 9 clusters, 9 campaigns, 114 cases, 47 entities, force graph |
| Browser console | **Zero errors** across landing, live call, report, login, dashboard, intel and analyze |

**Two cosmetic observations, neither a regression, both recorded rather than
fixed here:**
- The threat meter animates its *number* upward while the *band label* renders
  immediately from the contract, so mid-animation it briefly reads e.g. "38"
  above "CRITICAL". Settles correctly. Belongs to 7.2 if it is worth changing.
- `/api/health` and the dashboard report `contract v1` — the frame contract
  only. Once 1.6 serves investigations, health should report both versions.

**Effort:** 6 h estimated, ~6 h actual. **Depends:** 0.2. ✅

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

> **Scope correction from 0.6:** `services/api/engine/features/` (601
> statements — behaviour, callflow, emotion, linguistic, script_templates,
> spoofing, video) is **not on the serving path**. Coverage measurement showed
> it at 0%, and it turns out to be imported only by
> `ml/training/rssie/dataset.py`, for the multi-head research model that is not
> served. So it is *not* part of what 1.7 wraps. It also duplicates concerns
> that the served engine implements separately — `engine/spoofing.py` vs
> `engine/features/spoofing.py`, `engine/scripts.py` vs
> `engine/features/script_templates.py`. Decide deliberately in Phase 1 whether
> these become agents, stay research-only, or are consolidated; do not wrap them
> by reflex.
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
