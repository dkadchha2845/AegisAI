# AegisAI — Master Task List

> **Status: Phase 0 complete — all seven tasks. Phase 1 complete — all nine,
> verified end-to-end; 1.7b is in progress and the rest of it belongs to
> 4.8/4.9. An investigation is submitted from the product, routed through the
> graph, executed on a Celery worker rather than on the event loop that answered
> the request, streamed back node by node to a page that renders only what the
> server reported, and handed off as a report. A 90-second job no longer
> occupies a worker slot and a `kill -9` mid-job loses nothing. 1.7a fixed a
> benign false positive that 1.7's tests could not see because they ran without
> the served checkpoint; 1.7b is why a run now says which model it proved.
> Awaiting your go-ahead for Phase 2.**
> Last updated 2026-08-26 · branch `main`
> · 518 tests · 76.1% backend coverage · all four gates green · ruff + mypy clean

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

---

## Out of band — UI/UX audit and redesign, 2026-08-26

Not a numbered task: a full-product interface audit requested directly, run
against the running application on every route, in both themes, at desktop and
phone widths. Findings, measurements and the redesign are written up in
[`docs/UI_AUDIT.md`](UI_AUDIT.md).

The two that would have shown up in a demo:

- **The landing page and the login screen could not scroll.** `body` was
  `overflow: hidden` for the console's benefit, and the opt-out attribute was
  set by `AppShell` — which neither of those two routes renders inside. Every
  section below the hero was unreachable in any browser, and on a 720px
  viewport the login card's bottom 59px — nearly the Sign in button — was cut
  off. The layout switch moved to the router and the default inverted, so a
  route that forgets to declare itself is merely ordinary rather than broken.
- **The live console was unreachable on a phone.** 90 elements past the right
  edge of a 375px viewport, clipped rather than scrollable. Root cause was
  grid tracks that cannot shrink (`1fr` is `minmax(auto, 1fr)`); 25 of those
  across the stylesheets are now `minmax(0, 1fr)`, and below 900px the console
  becomes a scrolling document instead of a fixed instrument viewport.

Also: `--ink-faint` measured 3.22:1 and the entire light-theme ramp measured
under 4.5:1, so WCAG AA was failing on every screen at once; form controls
were rendering in Arial because nothing in the reset said `font: inherit`;
tenant administration was rendering on the citizen "My Reports" page *and*
duplicated on `/admin`; and the citizen education page was listing our own
repository filenames. One design-system layer (`styles/primitives.css`) now
owns one implementation per component, replacing five button systems, three
segmented controls, two table styles and four brand marks.

**Verified:** instrumented sweep over 15 routes × 2 themes × 2 widths — zero
unreachable overflow, zero AA contrast failures, zero unlabelled fields, one
`<h1>` per route, two font families. Analysis and investigation flows
exercised against the real API. Four gates green: 495 passed / 23 skipped,
contract consistent, typecheck clean, build succeeds.

**Not verified here:** scroll-driven behaviour on the landing page — the
browser pane used for the audit does not composite frames while hidden, so
`scroll` events and `IntersectionObserver` callbacks never fire. The
scroll-triggered reveals, the pipeline rail and the header's settle transition
typecheck and are written correctly, but want one pass by hand.

---

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

### ✅ 0.7 — `CLAUDE.md` + contributor docs
**Done 2026-08-24.** All eight invariants, the gates and a "definition of done"
checklist in `CLAUDE.md`; `README.md` points contributors at it; `AGENTS.md`
added as a **pointer**; and 15 tests in `test_contributor_docs.py` that keep the
document true.

**The three drifts recorded against this task during 1.1 are all closed:**

| # | Drift | Resolution |
|---|---|---|
| 1 | `CLAUDE.md` said the gate was "84 tests". It was 285. | Replaced with `make gates`, which is now the canonical command. A test forbids any hard-coded count in the contributor docs |
| 2 | `pyproject.toml` pointed at a `make format-check` target that never existed | The comment no longer names any target, and explains why: an earlier version named one that was never written, and a reader who skims a comment types the command in it |
| 3 | **`.coverage` was a tracked binary**, rewritten by every test run | `git rm --cached`, plus a `.gitignore` block. A test asserts the ignore rule is present, because untracking alone lets the next `git add -A` put it back |

**The tests do not check that the docs *say* the right thing.** String-matching
a document catches a stale sentence and misses the two failures that actually
happened here. So they check that the **commands the docs tell you to run
exist** and that the **files they send you to are there** — a doc instructing a
new contributor to run something absent is a broken door, and the only way it
stays fixed is if the build refuses it. Verified by breaking each guard on
purpose:

| Injected fault | Caught with |
|---|---|
| `make format-check` added to a doc's bash block | `CLAUDE.md tells contributors to run make targets that do not exist: ['format-check']` |
| A link to `docs/CONTRIBUTING.md` | `points at paths that do not exist: ['docs/CONTRIBUTING.md']` |
| `# 285 tests must pass` added back | `hard-codes a test count: ['285 tests must pass']` |
| An invariant copied into `AGENTS.md` | `restates invariants that belong in CLAUDE.md` |

**`AGENTS.md` is a pointer, not a copy — and that was learned the hard way in
this very task.** It was first created as a verbatim copy of `CLAUDE.md`, and
within the hour the two disagreed: `CLAUDE.md` had been corrected to stop naming
a fixed test count and the copy still named one, off by more than two hundred.
It now sends the reader to `CLAUDE.md` and carries only the command list, and a
test fails if anyone starts copying the invariants back into it.

**Two findings from actually running what the docs tell you to run:**

1. **The README's MIT badge linked to a `LICENSE` file that did not exist.** The
   badge is a claim and the link 404s on GitHub. It was recorded rather than
   invented — choosing a licence is the owner's call — and **resolved the same
   day on their instruction**. The `KNOWN_MISSING` exemption held it for exactly
   one task before `test_the_known_missing_list_stays_honest` demanded its
   removal, which is the intended lifecycle: an exemption is a note with an
   expiry, not a permanent excuse. See 0.7a below.
2. **The 1.4 commit claimed "ruff clean" and the committed tree had one ruff
   finding** — an unsorted import block in `test_input_classifier.py`. Confirmed
   by stashing and re-running ruff against HEAD. Fixed here. Worth noting the
   class of error: the claim was made from a run that happened *before* the last
   file was written.

**Verified end-to-end.** For a documentation task the real path is the
documentation, so every `make` target the docs name was run rather than read:
`make gates` (green), `make help`, `make graph-summary`, `make status` (4/4
stores reachable). Then the checklist's own instruction — start the app and read
`/api/health`: `ok: true`, classifier `fused`, retrieval dense/31 chunks, 114
intel cases, `degraded: []`. Scam **87.0 HIGH**, bank debit **21.1 CALM**,
delivery **7.5 CALM** — unchanged, as a docs task should leave them.

| Check | Result |
|---|---|
| Four gates | **298 tests** · contract consistent · typecheck clean · build clean |
| Also | ruff clean · mypy clean |
| Docs guards | 15 tests, all four negative controls fire |

**Effort:** 2 h estimated, ~2 h actual. ✅

### ✅ 0.7a — `LICENSE`, with the code/data split written down
**Done 2026-08-24**, on the owner's instruction, immediately after 0.7 recorded
the gap.

MIT, `Copyright (c) 2026 Dhrumil Kadchha` — which implements the claim the
README badge was already making rather than choosing anything new.

**One licence for the whole project, by the owner's decision.** The first draft
carved the corpus out to CC-BY-4.0 to match `docs/DATASETS.md` §9. Asked, the
owner chose MIT throughout, so `DATASETS.md` was corrected in the same change —
two files naming different licences is precisely the drift 0.7 exists to prevent,
and leaving the old promise in place would have been worse than the missing file
it replaced.

**What MIT does not reach, because it cannot.** A licence grants only what the
grantor holds, so the file states two facts rather than reserving anything:
real-world artefacts ingested under `DATASETS.md` §6 keep their own terms and
are excluded from release when those terms forbid it, and checkpoints under
`ml/artifacts/` inherit their base model's obligations — MuRIL is Apache-2.0 and
requires attribution.

**Named in five places, now checked in all five.** `LICENSE`, the README badge,
`DATASETS.md` §9, `apps/web/package.json` and `packages/aegis_core/pyproject.toml`.
The last two were added so npm and GitHub's detection agree with the root file;
both manifests were re-validated (`npm pkg get license`, a clean editable
reinstall of `aegis-core`).

**Verified, each guard fired on purpose:**

| Injected fault | Caught with |
|---|---|
| `LICENSE` added while still exempted | `these are no longer missing and should leave KNOWN_MISSING: ['LICENSE']` |
| `LICENSE` moved away after the exemption was removed | `README.md points at paths that do not exist: ['LICENSE']` |
| CC-BY-4.0 restored in `DATASETS.md` | `these no longer say MIT while LICENSE does: ['docs/DATASETS.md']` |

`KNOWN_MISSING` is now empty — the exemption held for exactly one task, which is
the intended lifecycle: a note with an expiry, not a permanent excuse.
300 tests, four gates green, ruff + mypy clean.

**Copyright holders: Dhrumil Kadchha and Smruthi Chandrashekar.** The line was
written with one holder and corrected once the owner supplied the co-author's
name. A test now asserts both names are present — a name is the easiest thing in
a licence to lose to a careless rewrite, and a licence that understates who owns
the work is a defect in the licence rather than a formality.

---

# PHASE 1 — Agent Architecture & Orchestration
*Goal: the skeleton every later phase plugs into.*
**Exit criterion:** an investigation can be submitted, routed by input type
through a LangGraph graph, executed with parallel fan-out, traced, persisted,
and streamed to the UI — even if only three agents exist.

**Progress: 9 of 9 done** — ✅ 1.1 · ✅ 1.2 · ✅ 1.3 · ✅ 1.4 · ✅ 1.5 · ✅ 1.6 ·
✅ 1.7 · ✅ 1.7a · 🔨 1.7b · ✅ 1.8 · ✅ 1.9. **Phase 1 is closed.** The input
classification agent is the first real agent rather than a
harness; its accuracy bar was ≥98% on a 200-item fixture including 20
adversarial items, and it measured **100%**. 1.5 makes an investigation durable:
six tables, Alembic migrations, and a repository in which an unscoped query is
not expressible. 1.6 joins them to a served path. 1.7 puts the inherited engine
inside it — and 1.7a fixes the false positive that going through it with the
real checkpoint exposed, in `engine/` where it had lived since KAVACH.

> **The phase exit criterion, read against what exists.** An investigation is
> submitted over HTTP, routed by input type, executed with a parallel fan-out
> over **eight agents in four tiers**, traced, persisted, streamed to a client
> node by node, reported, and erased — verified against a running uvicorn and
> from a real browser page, not only in tests. "Even if only three agents exist"
> is satisfied and then some.
>
> The one qualification that remained was 1.8's, and 1.8 has closed it: the
> graph runs on a Celery worker when a broker is reachable, so a restart no
> longer loses an in-flight run and a slow agent no longer occupies a worker
> slot. With no broker it runs in the API process exactly as before, which is
> the documented zero-setup path and is reported as `execution.mode: in-process`
> rather than assumed. The older `engine/analyzer.py` path is untouched and
> still serves `/api/analyze/*`; the two provably agree, signal for signal, on
> the same input — which is what 1.7 was for.

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
  *Done in 1.6: `investigation_contract_version` sits beside it.*

**Effort:** 6 h estimated, ~6 h actual. **Depends:** 0.2. ✅

### ✅ 1.2 — Agent base protocol + registry 🔴
**Done 2026-08-24.** `agents/base.py` (the `Agent` protocol, `AgentContext`,
`run_agent`) and `agents/registry.py` (decorator registration, version pinning,
`eligible()`, `warm_all()`). 43 new tests; 217 total.

**`Agent` is a `Protocol`, not a base class.** Task 1.7 wraps the inherited
engine in thin adapters, and those adapters should not have to inherit from
anything to be agents. Structural typing keeps the crown-jewel engine free of
any dependency on this layer — an adapter is an agent because it has the right
shape, and `isinstance()` still works because the protocol is
`@runtime_checkable`.

**`run_agent()` is the whole point, and it never raises.** Four outcomes, all of
them a valid `AgentResult`:

| Situation | status | tag appended to `degraded` |
|---|---|---|
| `can_handle()` false | SKIPPED | none — not applying is not a shortfall, and a field that cries wolf gets ignored |
| Returned normally | whatever the agent said | `agent:<name>:degraded` if it declared DEGRADED |
| Raised | ERROR | `agent:<name>:error` |
| Hung past its timeout, or cancelled | ERROR | `agent:<name>:timeout` / `:cancelled` |

`CancelledError` is the single exception allowed past. If the harness swallowed
it, a cancelled task would report completion, `asyncio.gather` could never shut
a fan-out down, and cancelling an investigation would hang until every agent's
timeout expired. Containing agent failures must not mean containing the event
loop's own control flow — there is a test for exactly this.

**A deliberate refinement of ARCHITECTURE.md §2.** The table there says a failing
node "emits `AgentResult(status=DEGRADED)`". This returns **ERROR** and a
`degraded` tag instead. The property §2 is protecting — the investigation still
completes and the shortfall is visible — holds either way, and the finer
distinction is load-bearing: only the agent itself can know it fell back.
DEGRADED means "I answered, from a cached snapshot"; an agent that raised
produced no answer at all. Collapsing them leaves 4.1 unable to tell how much
weight a result deserves.

**Two findings from running it, not from the suite.** A scratch harness fanned
out three agents over one state — one wrapping the real MuRIL classifier, one
wrapping the real entity extractor, one standing in for a dead threat-intel
feed:

| # | What surfaced | What changed |
|---|---|---|
| 1 | **The classifier costs 7.66 s on its first call and 22–34 ms after** — a 300× cold-start difference, all checkpoint loading. ARCHITECTURE.md §2 gives an agent 8 s, so an agent that loads lazily on first `run()` times out or nearly does on the first investigation after every restart | `registry.warm_all()` added, with an optional `async def warmup()` hook kept **off** the protocol so 1.7's adapters stay four lines. A failing warm-up is reported per agent and never blocks boot. My own docstring had advised lazy-loading on first `run()`; running it proved that advice wrong, and it is corrected in place |
| 2 | **A UPI ID at the end of a message was silently discarded** — see the separate commit below. Found because the fan-out reported `upi_count 0.0` on text that plainly contained `UPI: cbi.verify@okaxis` | Fixed, with 14 regression tests |

**Verified end-to-end:**

| Check | Result |
|---|---|
| Four gates | 217 tests · contract consistent · typecheck clean · build clean |
| Also | ruff clean · mypy clean (pydantic plugin enabled — see below) · coverage **67.88%** vs the 65% gate |
| `base.py` / `registry.py` coverage | 97% / 100% — the only uncovered lines are the Protocol's `...` bodies |
| Real fan-out, real engine | scam → `threat_score 91.0` + `upi_id cbi.verify@okaxis`; benign → `21.1`, no UPI. Dead agent timed out at 3 s, `degraded: ['agent:flaky_feed:timeout']`, both working agents' evidence intact |
| Concurrency actually concurrent | wall clock **3001 ms** with a 60-second agent in the fan-out |
| API after the change | boots, `degraded: []`, classifier `fused`/loaded, 4/4 stores reachable, intel 114 cases |
| False positives | bank debit **21.1** CALM, delivery **7.5** CALM — unchanged |
| Browser | Analyze page renders, session still authenticated, **zero console errors** |

**Also in this task:** mypy now follows imports into `schema/`, because the
agent layer's entire value is that every agent returns one typed shape. That
surfaced `Field(default_factory=Model)` as an error — a known false positive
from pydantic's `Field()` overloads, not a defect — so `pydantic.mypy` is
enabled in `pyproject.toml`.

**Effort:** 5 h estimated, ~5 h actual. **Depends:** 1.1. ✅

### ✅ 1.2a — Fix: a UPI ID at the end of a message was silently discarded
**Done 2026-08-24, committed separately** (`3377a72`) because a schema/agent
commit is not the place to smuggle an engine fix.

The fragment guard in `intel/entities.py::extract_from_text()` read:

```python
if _in_email(s, e) or text[e : e + 1] in "-.":
    continue
```

At the end of a string that slice is `""`, and **`"" in "-."` is `True`** — the
empty string is a substring of everything. So a VPA with nothing after it was
thrown away as a fragment. Adding one trailing space made it reappear, which is
what made the bug findable at all.

That is the most common shape a payment demand takes. All three of these lost
their payment address:

```
"Aapka KYC block ho gaya hai. Rs 10 bhejiye: sbi.kyc@okhdfcbank"
"Court fees ke liye payment kariye abhi. UPI ID: legal.dept@paytm"
"Refund ke liye confirm kijiye - refund.rbi@ybl"
```

**Blast radius, stated precisely.** `/api/analyze/text` was *not* affected — it
uses `engine/analyzer.py::extract_upi_ids`, which never had the bug. The buggy
extractor feeds `shield/verify.py`, `shield/complaint.py` and
`intel/repository.py`. So what was actually losing the payment address was **the
police complaint, the evidence vault, and the fraud graph** — no error, no log,
just the single most important entity missing and the edge to every other case
paying the same mule account never drawn.

**Verified end-to-end through the citizen path:** `POST /api/shield/preserve`
with that KYC message, then `GET /api/shield/vault/{token}/complaint` — the
generated complaint now carries `sbi.kyc@okhdfcbank` in three places and lists
it under `entities.upi_ids`.

14 tests in `test_entity_extraction.py` cover the fix and the neighbours it must
not break: a genuine `@gov` fragment is still rejected, an email at the end is
still an email, a consumer-mail handle is still an email, a domain and a phone
at the end still parse, and a benign bank alert still yields **no** payment
entities at all.

### ✅ 1.2b — One module identity for the contract
**Done 2026-08-24, committed separately** (`d7619ef`). Prerequisite for 1.2.

`services/api/` reaches the contract as `schema.models`; the four existing
importers reached the same file as bare `models`, via a `sys.path` insert.
Python treats those as different modules, so `models.AgentResult` and
`schema.models.AgentResult` are **different classes** — `A1 is A2` is `False`.

Nothing was broken, because nothing imported both. The moment `agents/base.py`
landed, a test building a result through the agent layer and validating it
inside a fixture built by `mock_investigation.py` would have failed with a type
error naming two identically-spelled classes. The three scripts now insert the
repo root and import `schema.models`; they still run standalone, and the 1.1
test needed no path insert at all once the names matched.

### ✅ 1.3 — LangGraph orchestrator skeleton 🔴⭐
**Done 2026-08-24.** Four modules — `graph.py`, `policy.py`, `trace.py`,
`determinism.py` — plus a CLI. 57 new tests; 274 total. LangGraph 0.6 added to
requirements per ADR-0004; measured cost **+18 packages** including
`langchain-core`, which is the consequence that ADR already recorded.

**All four acceptance criteria, demonstrated on the real graph:**

| # | Criterion | Evidence |
|---|---|---|
| 1 | Compiles and renders to Mermaid **via a CLI** | `make graph` / `python -m services.api.orchestration`; `--summary` lists the live agents by tier |
| 2 | A node times out and the investigation still completes | Five agents, one a feed that never answers: **COMPLETE**, `degraded: ['agent:dead_feed:timeout', …]`, and the other four agents' evidence intact |
| 3 | Trace shows per-node latency | A span per *attempt* — `investigate/upi_reputation#1@0` error, `#2@0` degraded — with real milliseconds |
| 4 | **Same input ⇒ same output** | Two runs: `a237a8ee41a2526d…` twice. Ablating one agent changes it, so the hash is not vacuous |

**LangGraph owns the graph; it does not own the fan-out.** Concurrency inside a
tier is `asyncio.gather` — which is what the task specifies — for two reasons
that beat symmetry. Parallel LangGraph branches writing one state key need a
reducer declared as `Annotated[list, add]` **on the state schema**, and that
schema is `InvestigationState`, which lives in `schema/` and is mirrored into
TypeScript; putting orchestration metadata into the shared contract to satisfy
one library is precisely the leak the contract exists to prevent. And the merge
order would then be the library's business, when determinism is ours.

**Determinism had to be defined before it could be claimed.** Two runs are never
byte-identical — an investigation records how long it took. So
`determinism.fingerprint()` hashes everything *except* the timings, and the
exclusion list is short, explicit and justified per entry (`latency_ms`,
`t_start`, `t_end`, `created_at`, `completed_at`, `received_at`, `retrieved_at`,
`case_id`, `TIRecord.cached`). Everything else is in — including list *order*,
which is deliberately not sorted at hash time, because the orchestrator sorting
the fan-out before merging is the property under test.

Three places nondeterminism was designed out rather than discovered:
`registry.all_agents()` sorts by name, so the plan does not depend on import
order · results are re-sorted by agent name after `gather`, so the merged list
does not depend on which agent finished first · span ids come from the plan
(`investigate/url_agent#2@1`) rather than a completion-order counter. The
determinism test uses agents with *randomised* sleeps precisely so that removing
any of the three would fail it.

**A defect the end-to-end run caught, and the unit test that could not.**
`graph.py` computed `policy_for(agent)` and used it for attempts and backoff —
but never put its timeout on the `AgentContext`, which is what `run_agent`
actually reads. **Every per-agent budget in `policy.py` was a silent no-op:**
threat intel's 3 s and the APK agent's 120 s both quietly became the 8 s default.
Nothing failed. The investigation completed, on the wrong clock.

The existing test passed because it asserted only that a hanging agent produced
an `agent:x:timeout` tag — which it did, eight seconds later. It took a real run
showing a feed with a 2 s policy timing out at **8002 ms** to see it. Fixed with
`dataclasses.replace(ctx, timeout_s=policy.timeout_s)`, and three new tests now
assert the *duration*, the context the agent actually receives, and that the
copy still shares the cancel event. Wall clock on the e2e run went 8072 ms →
**2070 ms**.

**A third-party warning that cannot be filtered by configuration.** LangGraph's
import trips a `LangChainPendingDeprecationWarning`, and `langchain_core`'s own
`__init__` calls `surface_langchain_deprecation_warnings()`, which *prepends* a
`"default"` filter for its categories. Filters match front-first, so anything
set beforehand loses — `-W ignore:…` on the command line does not suppress it
either, which is how the cause was found. It is silenced at our import site in
`graph.py` by importing `langchain_core` first, installing our filter in front
of its, then importing langgraph; `catch_warnings` then restores the filter list,
which also undoes langchain's mutation of this process's global warning state.
`pyproject.toml` carries a note saying why the filter is *not* there.

**Also decided here: agents declare a tier.** `agents/base.Stage`
(EXTRACT · INVESTIGATE · REASON · JUDGE) is what gives the graph its shape —
tiers run in order, agents within a tier run concurrently, and a later tier can
read what an earlier one wrote. It is **optional**, defaulting to INVESTIGATE, so
1.7's adapters stay four lines. `STAGE_ORDER` is an explicit tuple rather than
`list(Stage)`, so reordering the enum is not a silent change to what runs when.

**Verified end-to-end:**

| Check | Result |
|---|---|
| Four gates | 274 tests · contract consistent · typecheck clean · build clean |
| Also | ruff clean · mypy clean · coverage **69.27%** vs the 65% gate |
| Module coverage | `graph.py` 99% · `policy.py` 100% · `trace.py` 100% · `determinism.py` 100% |
| Real graph, real engine | 5 agents / 3 tiers: scam → `threat_score 91.0` + `cbi.verify@okaxis`; benign → `21.1`. Retry visible as two spans, dead feed timed out at its own 2 s budget |
| Crash and resume | Killed mid-investigation, resumed to COMPLETE, and **the classifier ran once, not twice** — the checkpoint held |
| API after the change | boots, `degraded: []`, 4/4 stores reachable, 114 intel cases |
| False positives | bank debit **21.1** CALM, delivery **7.5** CALM — unchanged |
| Browser | Live Protection renders, session authenticated, **zero console errors** |

**Not implemented, and stated rather than implied:** the
`FAN -.new entity discovered.-> FAN` recursion in ARCHITECTURE.md §2.
`AgentContext.max_depth` is carried and enforced so the *bound* exists, but
nothing yet discovers an entity worth recursing on — that needs the Phase 2
agents, and building the loop now would mean testing it against a toy that
pretends. The REASON tier is a real node with no agents in it. Nothing persists;
1.5 writes it down.

**Effort:** 12–16 h estimated, ~11 h actual. **Depends:** 1.2. ✅

### ✅ 1.4 — Input Classification Agent 🔴
**Done 2026-08-24.** `input_classifier` v1.0.0 is the graph's dedicated first
node — it runs before the EXTRACT tier, writes `inputs[].kind` and
`input_types`, and cannot run a second time in the generic fan-out. Its
`AgentResult` carries one detected type per evidence item, the actual media
type, and an explicit finding for every concrete metadata conflict.

**Magic bytes first, filename second, content third; never user MIME.** The
sniffer detects images (and conservative screenshots), PDFs, EML, URLs, APKs
from their ZIP central directory, audio and video containers, phones, UPI IDs,
and ordinary text. A filename or claimed MIME can never override bytes; it can
only add a `type_conflict` finding. `application/octet-stream` is deliberately
not a conflict because it is an absence of a claim, not evidence of deception.
The sniffer lists ZIP members but never extracts or executes them.

**Ambiguity stays explicit.** An SMS containing a URL and UPI ID emits all four
routes (`SMS`, `TEXT`, `URL`, `UPI_ID`). An unrecognised binary — including a
generic ZIP — keeps `UNKNOWN` as its primary type *and* adds `TEXT`, so the safe
text path still runs instead of the graph stopping with no eligible agent. If
the classifier itself errors, the graph makes the same UNKNOWN + TEXT fallback
and records its normal degradation tag rather than trusting caller metadata.

**Measured acceptance fixture:** 200 items, 180 ordinary and 20 adversarial,
measured **100.0%** exact type-vector accuracy. The adversarial members include
APK renamed `.jpg`, HTML renamed `.pdf`, PDF renamed `.jpg`, PNG renamed `.apk`,
EML masquerading as an image, MIME-only APK claims, and a generic ZIP named as a
PDF. The test prints every miss if accuracy falls below the required 98%.

**Verified end-to-end:**

| Check | Result |
|---|---|
| Classifier graph | CLI summary shows `input_classifier` v1.0.0 in EXTRACT; graph test proves a URL-only agent sees the detected `URL` only after classification |
| Focused agent checks | 30 tests, including the full 200-case corpus, ambiguity, type-conflict findings, UNKNOWN→TEXT fallback, benign generic-MIME discipline, and duplicate-run prevention |
| Four gates | **282 tests** · contract consistent · frontend typecheck + production build clean |
| Also | ruff clean · mypy clean |
| Running API | `/api/health` returned `ok: true`, fused classifier loaded, dense retrieval and all four stores healthy, `degraded: []` |
| Regression / false positives | Real scam text: **91 / CRITICAL / LIKELY_SCAM**; legitimate SBI debit alert: **17.6 / CALM / LIKELY_LEGITIMATE** |

The lifecycle API intentionally does not expose this graph yet — that is task
1.6, and the existing `/api/analyze/text` path remains unchanged. **Effort:**
8 h estimated. **Depends:** 1.2. ✅

### ✅ 1.5 — Evidence store (Postgres) 🔴
**Done 2026-08-25.** An investigation is now a durable record rather than an
object the graph handed back. Six tables (`investigations`, `evidence_items`,
`agent_results`, `findings`, `entities`, `case_entities`), two Alembic
revisions, and `stores/evidence.EvidenceStore` — the only module that touches
them.

**Tenant isolation is a shape, not a discipline.** `EvidenceStore` takes one
`org_id` at construction; no method accepts an organisation, there is no
`load_any()`, and there is no cross-org escape hatch for a platform owner.
*A route that forgets to scope a query is a bug; a repository that cannot
express an unscoped query is a design.* Every one of the six tables carries a
non-nullable `org_id` with no exceptions, which is what lets the claim be
checked in one assertion instead of argued in a paragraph — and a seventh table
added without one fails
`test_every_table_in_this_store_carries_a_non_nullable_org_id`. A separate test
asserts no module outside the repository imports those tables, because the
isolation *is* the repository: there is no row-level security underneath it.

**The rebuild comes from rows, not from a blob.** `load()` reassembles the state
from `evidence_items`, `agent_results`, `findings` and `case_entities`. Storing
the whole state as one JSON document would have passed the same acceptance test
while making the six tables decoration. What genuinely has no queryable home —
`trace`, `rag_context`, `graph_context`, `risk_features` and eight more — lives
in one `rest` column, computed as *the contract minus everything a column or a
table already holds*. Nothing is stored twice, so nothing can disagree, and a
field added to `InvestigationState` tomorrow round trips without a migration.
`test_residual_covers_every_contract_field` fails when the contract changes —
deliberately, so that "column, table, or residual" is a decision someone makes.

**Three judgement calls worth defending.**
`case_id` is unique **per organisation**: two tenants minting the same id are two
unrelated cases, and a global constraint would let one org's write fail because
of a case it may not know exists. Entity values are stored **exactly as
extracted** — deciding two identifiers are the same identifier is the graph's
job, and a store that rewrites evidence is not an evidence store. And every
entity row records `linkable`, copied from the ten fields the contract names:
`banks`, `locations`, `scam_keywords`, `amounts` and `authorities` are stored
unlinkable, so Phase 3 cannot build a fraud edge out of two cases both saying
"SBI".

**Erasure does not depend on a database setting.** The foreign keys declare
`ON DELETE CASCADE` and PostgreSQL honours them; SQLite ignores cascades unless
`PRAGMA foreign_keys=ON` is issued per connection. Since deleting a case is the
right 1.6 exposes to a citizen, `delete_case()` deletes children explicitly and
prunes entities no surviving case references. The cascade stays declared as a
backstop, not as the mechanism.

**Two revisions, not one.** `0001` baselines the five tables that predate
Alembic; `0002` adds the evidence store. Rolling back 1.5 therefore takes six
tables and leaves the users and saved cases alone — verified, with rows in them.
An existing `create_all` database is stamped (`alembic stamp 0001`) rather than
upgraded; running `upgrade` on it instead fails loudly on the first
`CREATE TABLE`, which is correct, and is asserted.

**A drift check instead of a convention.** `create_all` builds the schema for
the zero-setup database and Alembic builds it for a durable one. Two code paths
to one schema become two schemas the day a model is edited and a migration is
not — and the symptom is a `column does not exist` weeks later, not a red test.
`test_head_matches_the_models` upgrades an empty database to head and asserts
`compare_metadata` finds nothing to change.

**One thing this task fixed that it did not set out to.** `services/api/db.py`
used `declarative_base()`, whose return value mypy cannot follow. The moment the
typed store layer imported it, the gate that is kept at zero reported **23**
"invalid base class" errors across `models_db.py` and `stores/models.py`. It is
now `class Base(DeclarativeBase)` — SQLAlchemy 2.0's typing-aware form, identical
mapping behaviour, both the annotated and legacy column styles unchanged. Since
that touches every persisted path, the verification below deliberately runs
against a **pre-existing** database as well as a fresh one; that is the Phase 0
lesson, and it is the reason `get_db()`'s return annotation was wrong too
(`Session` for a generator) and is now `Iterator[Session]`.

**`/api/health` stopped hedging about Postgres.** `in_use` was hard-coded false
for all four stores with "until Phase 3" in the detail line. For Postgres that is
now a real question, so it is answered from the configured engine:
`database.backend` names the dialect instead of filing everything non-SQLite
under "external", and `store:postgres:unreachable` is emitted **only** when an
operator asked for Postgres and cannot reach it. Neo4j, Qdrant and Redis are
untouched and still say Phase 3.

**Verified end-to-end:**

| Check | Result |
|---|---|
| Four gates | **340 tests** · contract consistent · frontend typecheck + production build clean |
| Also | ruff clean · mypy clean (23 → 0) · coverage **72.30%** vs the 65% gate |
| Module coverage | `evidence.py` **100%** · `models.py` **100%** · `probe.py` 95% |
| Migrations, SQLite | `upgrade head` → `compare_metadata` **[]** → `downgrade base` → 0 tables → `upgrade head` again |
| Migrations, **real PostgreSQL 16.6** | Same revisions on the compose stack: **diff []**, and `rest`/`payload` land as genuine `JSONB(astext_type=Text())`, not text |
| JSONB is real, not a label | `payload->'provenance' @> '["whois"]'` and `jsonb_array_length(rest->'trace')` both answered from the index, without loading a state |
| Existing database, migrated | A copy of the real `aegis.db` (12 users, 3 orgs, 38 audit rows): un-stamped `upgrade` **failed loudly**; `stamp 0001` + `upgrade head` added the six tables with **every row intact** and no drift |
| Real graph → real Postgres | Three investigations through `orchestration.investigate` with the inherited entity extractor attached: `round-trip identical=True` for all three, 4 investigations / 4 agent results / 12 findings / 9 entities / 10 case_entities |
| Cross-tenant, on the live DB | A second store on the same session: `list_cases() == []`, `load() is None`, `cases_for_entity() == []`; writing another org's state raised `OrgMismatch` |
| Shared-identifier query | `cases_for_entity("upi_ids", "refund@okaxis")` → `['AEG-E2E-1', 'AEG-E2E-2']`; `sbi` and `cbi` stored `linkable=False` |
| Erasure | `delete_case` removed the case and its children, kept the UPI two cases share, pruned what only it referenced |
| Running API, pre-existing SQLite | `/api/health` `ok:true`, `degraded: []`; **demo login worked** (`admin@aegis.local`, owner); report saved as `AGIS-0056DBB965EC` (78.0 HIGH); orgs listed |
| Running API, fresh Postgres | Boots on an Alembic-built schema, seeds, logs in; `database.backend: "postgres"`, `postgres.in_use: true`, `degraded: []`; case record `AGIS-C195F2353912` written to `case_records` |
| Degradation, live | `docker stop aegis-postgres` → `degraded: ["store:postgres:unreachable"]` and the API still answered `ok:true`; restarting cleared it |
| Browser | Login → Dashboard → Live Protection demo call → investigation report (**93 · CRITICAL · isolation**), **zero console errors** |
| False positives | SBI debit alert **16.1 CALM**, delivery notice **7.5 CALM**, real scam **91.0 CRITICAL** — unchanged |

**Not implemented, and stated rather than implied:** `EvidenceItem.uri` points at
an object store that does not exist, so today an uploaded screenshot's *bytes*
are not durable — only its hash, metadata and any inline text. Uploads are 1.6.
Nothing here is encrypted at rest; that is volume encryption at deploy time, not
a column type, and claiming it in a docstring would be an unmeasured security
claim. Entity upsert is one `SELECT` per identifier rather than a dialect
`INSERT … ON CONFLICT` — fine at a few dozen per case, and the first thing to
change if a backfill gets slow. The graph does not yet write through this store:
that is 1.6, and no route touches it today.

**Effort:** 10 h estimated. **Depends:** 0.4, 1.1. ✅

### ✅ 1.6 — Investigation lifecycle API
**Done 2026-08-25.** The graph from 1.3 and the store from 1.5 were built to be
wired together and nothing was calling either of them. Six routes now do:
`POST /api/investigations` (JSON **or** multipart) · `GET /{id}` ·
`GET /{id}/stream` (SSE) · `GET /{id}/report[.pdf]` · `GET /{id}/trace` ·
`DELETE /{id}`. Behind them, `services/api/investigations/` — `intake.py`,
`runner.py`, `report.py` — plus `stores/blobs.py` for the bytes.

**Progress is observed, not estimated.** `orchestration.graph` gained
`investigate_stream()`, which runs the compiled graph with LangGraph's
`updates` and `values` stream modes together and yields one `NodeUpdate` as
each node actually completes. There is deliberately **no `node_started`
event**: the graph reports completions, so a "started" event would be inferred
from the plan rather than observed — a fake timer wearing a node name, which is
exactly what 1.9's acceptance criterion forbids. The client is instead handed
the whole node plan on `accepted` and told about each completion, so "3 of 7"
is built from two facts it was given. `investigate()` is now implemented *on
top of* `investigate_stream()` rather than beside it, because two entry points
into one graph is two execution paths that have to be kept identical by hand.

**Reconnect is arithmetic, not a promise about timing.** Each run keeps a
journal — a list of `InvestigationEvent`, `seq` assigned from the list's own
length — and every follower holds an index into it. `Last-Event-ID: 4` means
"resume from index 4". The usual per-subscriber queue makes the requirement
*unsatisfiable*: once an event is taken off a queue it is gone, so a client
that dropped between two events has no way to ask for what it missed. Keepalives
are SSE comment lines, which carry no id by definition and therefore cannot be
replayed — if the idle signal were ever a real event, "no duplicates" would
quietly start meaning "no duplicates unless the connection was idle".

**`agent_results` on an event is the delta, not the running total.** The graph's
nodes return whole lists (`[*state.agent_results, *new]`), so an event that
forwarded the update verbatim would re-send every earlier tier and a
reconnecting client would count them twice. A client that appends every event's
results reconstructs the state's own list exactly, and a test fails if that
regresses.

**Uploads got somewhere to live.** 1.5 stated the hole it left — "an uploaded
screenshot's *bytes* are not durable; uploads are 1.6" — and `stores/blobs.py`
fills it: `<root>/<org>/<case>/<sha256>`, write-then-rename, org-scoped with no
cross-org accessor, exactly like `EvidenceStore`. **Case-scoped rather than
globally content-addressed**, and that is the erasure requirement talking:
under global content addressing "may I delete these bytes" becomes "is any
other case still referencing them", and a right to erasure that depends on a
reference count being correct is one that fails quietly, in the direction of
keeping data. Deleting a case is now deleting a directory. `_blob_of()` in the
input classifier — a hook that returned `None` since 1.4 — resolves `uri`
through this store, so **magic-byte routing became real for uploads at this
moment** rather than in 1.4.

**Intake does not reject on magic bytes, and that is the control working.**
`CLAUDE.md` requires uploads validated by bytes, not extension. There is no
allowlist to reject against — the promise is "upload anything" — and what
matters is the *disagreement*. Rejecting at the door would turn the most
interesting fact about a hostile upload into a 415 with nothing recorded. So
the declared type and filename are written down verbatim, the classifier
decides from the bytes, and the mismatch becomes a `type_conflict` finding. A
zip with `AndroidManifest.xml` uploaded as `holiday.jpg`, declared
`image/jpeg`, comes back `kind=APK` with both conflicts recorded, on the live
server.

**The cap is enforced while reading.** `await file.read()` followed by a length
check — what the older `/api/analyze/*` routes do — has already buffered the
whole body by the time it decides to refuse it, so a 500 MB upload costs 500 MB
to say no to. `read_capped()` refuses one 64 KB chunk past the limit, and a
test asserts the read count rather than just the status code.

**Four judgement calls worth defending.** (1) **There is no cross-organisation
view, not even for an `owner`** — a visible difference from `routes/reports.py`,
which uses `scope_query` and does let an owner read across tenants. 1.5 chose
"no `load_any()`, no escape hatch for a platform superadmin", and matching the
older route here would have undone it. (2) The **stream authenticates with a
header, never `?token=`**: `EventSource` cannot set headers, which is why so
many SSE endpoints end up accepting a token in the URL, and a token in a URL is
in every access log it passes. A browser reaches this with `fetch()` plus a
`ReadableStream` reader — verified from a real page below. (3) The evidence
scope is derived from the organisation's **primary key**, never its slug: a
renamed slug would orphan every case and every blob under the old one, silently,
because the new scope simply reads as an empty tenant. (4) `GET /{id}` serves
the runner's state while a run is in flight, because the durable row is written
when the graph finishes and serving it mid-run would report QUEUED to a client
being streamed the third node's results.

**The report says what it does not know.** The judgement tier has no agents
until 4.6/4.7, so every investigation completes with `risk_score` None. The
report's assessment block says so in a sentence — *"Absence of a score is not a
finding of safety"* — rather than rendering 0.0/CALM, which is a false negative
wearing a number. A test pins both halves: unscored says unscored, and a state
that *has* a score has it rendered verbatim rather than re-banded.

**One thing 1.1 parked that this task could finally answer.** `/api/health`
reported `contract_version: 1` — the *frame* contract — while the API had begun
serving the investigation contract too. 1.1 recorded that and deferred it in
those words: "once 1.6 serves investigations, health should report both
versions." It does now; both numbers are read from `schema/`, so neither can
drift from the contract it names.

**Two things this task fixed that it did not set out to.** Adding
`investigations/` to mypy's scope made the inherited engine reachable from the
typed layer for the first time (the report reuses the evidence package's
disclaimer rather than re-wording it), surfacing 10 pre-existing errors in a
gate kept at zero; `follow_imports = "silent"` on `services.api.engine.*` and
`services.api.rag.*` keeps their types available while leaving their errors
where `files` had been leaving them implicitly. And the first PDF render put
long finding values on top of the column beside them — reportlab lays a bare
string on one line and lets it overflow — so free-text cells are `Paragraph`s
now. Both were found by looking at the output, not by a test.

**Verified end-to-end:**

| Check | Result |
|---|---|
| Four gates | **392 tests** · contract consistent · frontend typecheck + production build clean |
| Also | ruff clean · mypy clean (10 → 0) · coverage **73.5%** vs the 65% gate |
| Module coverage | `runner.py` **97%** · `intake.py` **95%** · `routes/investigations.py` **94%** · `report.py` 91% · `blobs.py` 86% |
| Running API, live stream | uvicorn + `curl -N`: 9 events for a 7-node graph, `text/event-stream`, ids 1–9 contiguous |
| Progress is real, measured | With a deliberate 2 s agent in the tier: events 1–3 at **0 ms**, then a **1983 ms** gap, then 4–9. Not a timer |
| Reconnect, mid-run, real HTTP | Hung up after `id: 3` while the graph was still running; reconnected with `Last-Event-ID: 3` → resumed at **4**, no duplicate, no gap |
| Multipart + magic bytes | APK-shaped zip named `holiday.jpg`, declared `image/jpeg` → `kind=APK`, `media_type=application/vnd.android.package-archive`, **both** conflicts recorded, blob at `org-1/AEG-…/<sha256>` |
| Upload cap | 4 MB + 1 → **413** ("at most 4 MB"); exactly 4 MB → **202**; 9 artefacts → **413** |
| Durability across a restart | Killed and restarted uvicorn: case rebuilt from rows (2 items, 1 agent result, 1 trace span), blob uri still resolves; the stream returns **409** naming `GET /api/investigations/{id}`, not a 404 |
| Report + PDF | `scored: false` with the full note; 8 findings attributed to `input_classifier`; PDF **4.3 KB**, `%PDF-1.4`, `Content-Disposition` names the case — read back and inspected page by page |
| Cross-tenant, live | Second org via `POST /api/orgs` + a real login: state / report / trace / stream / delete all **404** (not 403 — a case id must not be probeable), and its own POST still **202** |
| Erasure, live | `DELETE` → `{erased: true, blobs_removed: 1}`; case 404s; **its** blob gone from disk, the other case's untouched; `investigation.delete` audit row survives naming actor and case |
| Browser, real page | `fetch()` + `ReadableStream` from `localhost:5174` against the API: 202, `text/event-stream`, plan of 7, 9 ordered events, report unscored — **zero console errors**, app renders "2 degraded" |
| `blobs:ephemeral` discipline | All-ephemeral install reports `db:ephemeral` only — confirmed live. The tag is raised for a **durable DB with an ephemeral evidence dir**, the case that outlives its own screenshots |
| False positives | Benign SBI debit alert: no `type_conflict`, `degraded: []`, `classification: null`, `evidence: []`. It contains a real VPA, so `UPI_ID` is detected — extraction is not judgement, and a system that read "a UPI ID is present" as a signal would flag every bank alert in India |

**Not implemented, and stated rather than implied.** Execution is **in the API
process**, on the event loop that serves requests — that is 1.8, and until then
a restart loses every in-flight run and the durable row says QUEUED forever,
the journal is in memory so a post-restart reconnect gets a 409 (the case and
its report still read fine), and a slow agent occupies a worker slot. There is
**no collection `GET /api/investigations`**: `EvidenceStore.list_cases()` was
built for one, but the task names six routes and a seventh is a decision for
1.9's launcher, not a freebie here. There is **no per-org storage quota** —
ARCHITECTURE.md §8 names one; eight 4 MB artefacts per submission is the only
bound on disk growth today. Blob storage is a local directory, so two API
replicas do not share it, and nothing is encrypted at rest (volume encryption at
deploy time, not a column type). `TestClient` buffers a streaming response in
full, measured — so no test in the suite can assert that events arrive *as they
happen*; that claim belongs to the running server and is the row above, and the
live-resume path is covered directly against `Run.follow` instead.

**Effort:** 8 h estimated. **Depends:** 1.3, 1.5. ✅

### ✅ 1.7 — Adapt the inherited engine into agents ⭐
**Done 2026-08-25.** Seven adapters in `services/api/agents/inherited/`, and
**zero lines changed under `services/api/engine/`** — provable with
`git diff HEAD -- services/api/engine/`, which is the form the constraint should
take. `stage_classifier`, `coercion_tracker`, `trust_passport` and
`script_match` run concurrently in REASON; `number_spoofing` runs earlier in
INVESTIGATE because it works on metadata rather than conversation;
`threat_fusion` and `digital_twin` run last in JUDGE, which 1.3 built empty.

**"Adapt without rewriting" is only checkable if something proves nothing was
quietly reimplemented.** A green suite does not: an adapter that recomputed the
coercion index with slightly different constants would pass every test that
existed. So the bar in `test_inherited_agents.py` is **equality with the old
path** — for the same input the graph must produce the same stage labels, the
same peak, the same manipulation map, the same coercion index, the same trust
percentage, the same script similarity and the same fused drivers as
`engine/analyzer.analyze_text`. Driver-for-driver rather than by total, because
two different weightings can reach the same score and the same drivers with the
same contributions in the same order cannot happen twice by coincidence.

**One shared parser, not six.** `inherited/conversation.py` decides what "the
conversation" is for an investigation, and delegates the parsing to
`analyzer.normalise` — the old path's own function. That is what makes the
equality claim mean something: it is one implementation reached two ways rather
than two that happen to agree today. It also resolves the shape mismatch, since
the batch path scores a string and an investigation carries `inputs`,
`extracted_text` and a `transcript`; the first non-empty source wins rather than
all three concatenating, because `extracted_text` is *derived from* the inputs
and reading both would score the same words twice through every cumulative
signal the engine has.

**The manipulation accumulator is replayed, not passed.** `threat.fuse` wants a
`ManipulationAccumulator` charged by the caller's stages *and* the victim's
states, interleaved. Two concurrent agents produce those halves and neither can
hold the object — only an `AgentResult` crosses between agents. So the fusion
agent rebuilds it by calling the accumulator's own public methods over the
published findings, which keeps the charge constants in `threat.py` where a
copy of `0.34` would eventually drift from. Replay order is faithful because
every charge is `min(1.0, current + delta)` with non-negative deltas, so the
result depends on the multiset and not the order — and the test asserts the map
equals the interleaved one rather than resting on that argument.

**Two things this task deliberately did not do, and both are the architecture
talking rather than a shortcut.** `threat_fusion` does **not** write
`state.risk_score`: the contract's score belongs to 4.6, which reconciles a
calibrated model, deterministic rules and graph evidence, and filling it from a
heuristic weighted sum would put an unearned number in the field the report
reads first. And it does not apply the dispositive floor `analyze_text` uses on
top of `fuse()`: ARCHITECTURE.md §4 puts "deterministic rules — dispositive
signals only" inside the fusion box that 4.6 builds, and a second copy of
`55 + 40 × weight` is how two paths start disagreeing about a 69.6. The fused
score travels as a *feature* instead — available to 4.1, visible in the trace,
and not yet a claim.

**Where the paths differ, the difference has a name.** On the sample scam SMS
`analyze_text` reaches **91.0** and the graph's fusion reaches **30.3**. All of
that gap is one finding — "Impersonates an institution", weight 0.9, produced by
`engine/upi.py` against `refund@okaxis` and floored in by the dispositive rule.
`upi.py` is task **2.6**'s Financial Fraud Agent and is not one of the seven
modules 1.7 wraps; no passport check failed on that input at all. So the graph
is not disagreeing with the engine, it is missing an agent and a rule, both
named — and `test_the_gap_to_the_old_paths_final_score_is_attributable` pins it
so the day either lands the difference must be re-explained rather than quietly
absorbed.

**`engine/features/` — the 0.6 scope correction, decided rather than deferred
again.** It **stays research-only and is not wrapped.** Three reasons, in order
of weight. (1) It duplicates two things the served engine already implements —
`features/spoofing.py` against `engine/spoofing.py`, `features/script_templates.py`
against `engine/scripts.py` — and registering both would put two views of the
same evidence into one weighted sum, which the package's own docstring warns
produces "confidence rather than corroboration". (2) It is measured at 0% on the
serving path; an agent whose code has never run in a request is a capability
claim without a measurement. (3) Its only importer is `ml/training/rssie/dataset.py`,
the multi-head research model, so the four modules with *no* served counterpart —
`behaviour`, `callflow`, `emotion`, `linguistic` — are genuinely new signal
rather than duplicates, and their natural homes are 2.7 (Social Engineering) and
5.2 (Conversation Dynamics), with 4.1's feature registry deciding what the model
actually consumes. Consolidating now would be guessing at that answer.
*Noted while checking:* `ml/training/rssie/model.py` says these are "the same
features the rule-based fallback uses", and they are not — nothing under
`services/` imports the package. Left as found, because the right wording
depends on the decision 4.1 makes.

**Three things running it found that the tests could not.**

*A seven-second agent.* The Trust Passport adapter took **7 224 ms** on its
first run in a cold process, against a default node budget of 8 000 — every FAIL
it publishes carries a citation, and fetching one builds the retrieval index.
`registry.warm_all()` existed for exactly this and nothing called it; the
lifespan now awaits it and `/api/health` reports the per-agent result, which is
where the registry's own docstring says the report belongs. Second run: 77 ms.

*A green suite that was green for the wrong reason.* The 1.6 API tests kept
passing in a full run while failing when run alone, because `test_input_classifier`
comes earlier in the alphabet and calls `registry.clear()` — so the lifecycle
tests had been exercising an agent set of one. The registry's docstring names
the hazard ("the suite passes or fails depending on file order") and it was
live. `conftest.py` now restores the built-in agent set before every test, and
every module was re-run in isolation to prove it.

*A `degraded` field on its way to being ignored.* The fusion agent's first rule
marked itself DEGRADED whenever a contributing agent had not answered — which
made **every** SMS investigation degraded, because a forwarded message has no
victim side and the coercion tracker correctly does not apply. A signal that
does not apply is not a shortfall. DEGRADED is now reserved for a contributing
agent that ran and *failed*; how much the fusion had is said precisely twice
already, by `provenance` and by `confidence` as a fraction of five.

**One defect surfaced and deliberately not fixed here.** `_run_stage` filters
each tier through `registry.eligible()`, so an agent whose `can_handle` returns
False produces **no result at all** rather than a SKIPPED one — making
`base.skipped()`'s stated purpose ("the trace should show that the APK agent was
considered and did not apply") and `AgentStatus.SKIPPED`'s contract note ("must
never be read as clean by the feature assembly in 4.1") unreachable from the
graph. 1.7 surfaced it rather than introduced it: this is the first task whose
`can_handle` gates are routinely false. It is left for **4.1**, the task whose
stated need it serves, because the fix changes `agent_results` for every
investigation — what the store persists, what the report's agent table shows,
what the SSE events carry — and that shape is 4.1's decision, not a change to
fold into this one.

**One rename, for the same reason 1.3 was bitten.** `policy.py` had reserved an
8 s / one-attempt budget under the placeholder name `scam_classifier`. A policy
key that matches no agent is a silent no-op — exactly the defect 1.3's
end-to-end run caught — so the reservation was renamed to `stage_classifier`
rather than the agent bent to the reservation, and a test pins that the budget
still applies.

**Verified end-to-end:**

| Check | Result |
|---|---|
| Four gates | **435 tests** · contract consistent · frontend typecheck + production build clean |
| Also | ruff clean · mypy clean · coverage **75.34%** vs the 65% gate |
| Module coverage | every file in `agents/inherited/` at **100%** |
| Engine untouched | `git diff HEAD -- services/api/engine/` is empty; no existing test file was modified except the three 1.6 assertions the richer agent set invalidated |
| No private coupling | `test_no_adapter_reaches_into_a_private_name_in_the_engine` scans the package — the adapters use nothing the engine did not choose to expose (`analyze_text` itself reaches `coercion._victim_state`; this package may not) |
| Equality, per signal | stage labels · peak stage · manipulation map · coercion index · trust % · passport FAILs · script similarity · fused drivers — **all equal** to `analyze_text` on the same call |
| Equality, end to end | Three benign messages score **identically** through both paths — 7.5 / CALM each, not "close" |
| Running API, real call | Digital-arrest transcript through `POST /api/investigations`: 7 agents, fused **81.4 HIGH**, drivers *Stage: Isolation 0.353 · Identity unverified 0.15 · Script match 0.15 · Victim stress 0.101*, twin forecasting VERIFICATION_DEMAND "~144 s to a payment demand" |
| The eighth agent, live | Same call plus an Indian mobile as its own evidence item: `number_spoofing` fires, FAILs *Caller-ID vs claimed authority*, and the fused score moves **81.4 → 89.5** — a personal handset claiming to be the CBI |
| Live-call path, unchanged | `POST /api/session` + 7 utterances: threat **89.5 HIGH**, peak 89.6, passport 0%, number risk 45 FAIL, forecast, evidence package `AGIS-…`, `/investigate` **LIKELY_SCAM 95.0 CRITICAL**, report saved 201, live PDF 5 112 bytes |
| The three paths agree | The live session's `manipulation_map` is `{authority 0.339, fear 0.372, isolation 0.373, urgency 0.108, compliance 0.0}` — **byte-identical** to the graph's fusion agent and to `analyze_text` on the same conversation |
| Browser | Live Protection → demo call → threat meter rising 5 → 31 → report **93 CRITICAL** with extracted entities. **Zero console errors** |
| False positives | Benign SBI debit alert through the API: **7.5 CALM**, no type conflict, no classification, and the only driver is *"Identity unverified"* — a statement about what was not checked, not about the message |
| Degradation, each exercised | text-only coercion (capped at 72, tagged) · twin falling back to the canonical prior · classifier reporting a genuine fallback · a raising script matcher leaving the investigation COMPLETE and the fusion running over four signals |
| Determinism | `fingerprint()` identical across runs with seven more agents contributing |

**Not implemented, and stated rather than implied.** `number_spoofing` reads
`state.entities.phones` and `PHONE`-typed evidence items only — nothing
populates `entities` yet, so a number merely *mentioned* inside a message does
not reach it, and a **foreign** number submitted as its own item is typed `TEXT`
by the 1.4 classifier (whose phone pattern is India-specific) and misses too.
Both close in 2.1/3.2; scraping identifiers with a regex in the adapter would be
a second, unowned implementation of extraction. The coercion index is always
text-only here and capped at 72, because the prosodic half comes from live ASR
word timings that a batch investigation does not have — 6.2 supplies it. And
`coercion_index` is passed to `fuse` as `0.0` rather than `None` when the agent
skipped: faithful, because `fuse` types it as a plain float and the engine has
no unrun value for it, unlike `trust_pct` and `spoofing_risk`, which are passed
as `None` so an absent number is never scored as a clean one.

**Effort:** 10 h estimated. **Depends:** 1.3. ✅

### ✅ 1.7a — Fix: a benign message named a scam stage it never reached

**Why this exists as its own task.** 1.7 was ticked on 435 green tests. They
were green for an environmental reason: `ml/artifacts/` is gitignored except two
JSON files, and the worktree 1.7 was verified in held no `stage-classifier/`
checkpoint — 8 KB against the 3.5 GB in a full checkout. So the suite exercised
the **lexical fallback**, not what the application serves. With the promoted
checkpoint loaded (`/api/health`: `backend: fused`, `serving_best: true`,
macro-F1 0.767 vs lexical 0.375), `test_a_benign_message_is_scored_only_by_what_was_not_checked`
fails. This is the working-agreement lesson in a new shape: not a fresh DB this
time, but a fresh *model directory*.

**The defect.** `threat_weight("BENIGN")` is `0.0`, and the peak turn was chosen
by `threat_weight(stage) × confidence`. A BENIGN turn therefore scores 0 no
matter how sure the classifier is, so **any** non-benign label at **any**
confidence outranked it. On an Amazon delivery notice, `normalise` splits two
sentences into two turns and the second draws VERIFICATION_DEMAND at 0.242 —
which beat BENIGN at 0.553, became the peak, and put "Stage: Verification
Demand" on the report. Two of the three benign fixtures did this; only one was
asserted against, which is why one test caught what two messages were doing.
It was never a graph defect: `analyze_text` — the inherited served path, and
the live call with it — produced the identical driver, so the adapter was
faithfully reproducing a defect that shipped with KAVACH.

**The fix.** One function, `classifier.stage_rank(label, confidence)`, with
`MIN_STAGE_CONFIDENCE = 0.40` under it. Below the floor a label ranks 0, so it
can neither become the peak nor contribute points. All four ranking sites route
through it — `analyzer` for the served path, the `stage_classifier` adapter for
the graph, `threat.fuse` for the score, and the test that acts as the equality
oracle — so the two paths cannot drift apart. `ManipulationAccumulator.observe`
takes the same floor: without it a benign notice still charged 0.011 urgency,
too small to name a driver and large enough that `pressure` was not 0.

**Why 0.40, measured rather than picked.** Chance over eight stages is 0.125.
The non-benign labels the *benign* fixtures produce top out at 0.340; the turns
that carry a scam verdict run 0.601–0.911. 0.40 sits in the empty band between
them, at 3.2× chance. This is calibrated on five fixtures, which is not the same
as evaluated — 4.4 owns calibration and 4.8 the false-positive harness, and this
number should come from a corpus once they exist.

| Fixture | Before | After |
|---|---|---|
| digital-arrest call | 95.0 LIKELY_SCAM, 4 drivers | **unchanged** |
| scam KYC SMS | 91.0 LIKELY_SCAM, 3 drivers | **unchanged** (graph 32.5 → 32.2) |
| benign delivery notice | 15.5, "Stage: Verification Demand" | **7.5, `['Identity unverified']`** |
| benign SBI debit alert | 16.3, "Stage: Verification Demand" | **7.5, `['Identity unverified']`** |
| benign HDFC OTP reminder | 7.5, clean | unchanged |

**Verified:** four gates green — **439 tests** (435 → 439: two new, one
parametrised over all three benign fixtures), contract consistent, frontend
typecheck and production build clean; ruff and mypy clean. Against a running
uvicorn with the checkpoint actually loaded: both benign messages return 7.5
CALM with one driver and all five manipulation bars at 0.0; the digital-arrest
call still returns 95.0 LIKELY_SCAM CRITICAL with its four drivers and the scam
SMS 91.0. Through the 1.6 graph API, the benign case reports `peak_stage=BENIGN`
and 7.5 CALM, the scam case `peak_stage=ISOLATION` at 91% and 78.7 HIGH over
four drivers. On the live-call path, benign holds 7.5 CALM with no stage driver
while the digital-arrest call reaches 77.7 HIGH.

**Two things left alone, deliberately.** `frame.stage.current` still displays
the raw per-turn label — a benign notice shows `VERIFICATION_DEMAND 0.242` in
the live console's stage panel. It no longer reaches any score, but it is a
contract field the UI renders, and whether a sub-threshold stage should be
*shown* is a rendering decision that belongs with 1.9/7.2 rather than to a
scoring fix. And the gate gap itself is recorded, not closed: see below.

**Effort:** 3 h. **Depends:** 1.7. ✅

### 🔨 1.7b — The gates cannot see a checkpoint-dependent defect

**The gap.** `ml/artifacts/*` is gitignored and `ci.yml` has no checkpoint step,
so CI runs the lexical fallback for every test, for ever. Every benign-input
test the contributor rules mandate per agent therefore proves something about
the fallback and nothing about what is served — which is exactly how 1.7a
reached a tick. Closing it needs a promoted checkpoint reachable from a gate
run, which is **4.9**'s model registry, and a false-positive harness worth
pointing at one, which is **4.8**'s.

**What was closed now (2026-08-25) — the third criterion.** The gap is not that
the fallback runs; on a clean clone it is the correct thing to run. The gap is
that **a green run did not say which model it proved**, so "439 passed" read
identically either way. `services/api/serving.py` turns the three facts
`/api/health` already publishes into something a gate asserts:

| Mechanism | What it does |
|---|---|
| `pytest_report_header` + `pytest_terminal_summary` | every run states its classifier. `addopts = "-q"` plus `make test`'s own `-q` is verbosity −2, at which pytest prints neither a header nor its own "N passed" — so this line is the one thing a gate run always says about itself |
| `AEGIS_REQUIRE_SERVING_BEST=1` | makes a genuine fallback **fail the backend suite**. `AEGIS_REQUIRE_SERVING_BEST=1 make gates` is the checkpoint-backed gate run, and it fails rather than quietly proving the stand-in |
| `python -m services.api.serving --require fallback` | a CI step that *pins* the runner's permanent state. The day 4.9 puts a promoted checkpoint there it fails, and someone has to decide what the gates require |
| health-step assertions in `ci.yml` | `serving_best is False` and `clf:lexical_fallback` present, on the served endpoint rather than in-process |
| `make serving` | reports what would serve, requiring nothing |

The report is read from `classifier.py`'s own globals, not recomputed:
`test_report_matches_health_field_for_field` pins the gate and the dashboard to
one derivation, because `loaded` was already reported wrongly twice by a second
one. `checkpoint_present` is tracked apart from `loaded`, so the checkout that
has 3.5 GB of weights and no torch — a legitimate configuration, and the exact
shape of a silent substitution — can never read as "the best model is serving".

**Verified 2026-08-25.** Four gates green — **451 tests** (439 → 451, twelve new
in `test_serving_backend.py`), contract consistent, frontend typecheck and
production build clean; ruff and mypy clean. The suite was run in all four
combinations of `AEGIS_REQUIRE_SERVING_BEST` × checkpoint present: green in
three, and in the fourth exactly one test fails, the one that should. Against a
running uvicorn: without a checkpoint `backend: lexical`, `serving_best: false`,
`degraded` carries `clf:lexical_fallback`; with `AEGIS_ARTIFACTS` pointed at a
full checkout, `backend: fused`, `loaded: true`, `serving_best: true`, and the
tag is gone.

**Still open, and why it is not ticked.** Two of the three acceptance criteria
are not this task's to close. 4.9 owns how a promoted checkpoint is obtained in
CI — or the statement that it is not, and what compensates. 4.8 owns the
false-positive suite that should be running against a served model. Until both
land, the honest description of a green CI run is "the fallback passed" — a
sentence the run now prints for itself.

**Accept:** ~~`/api/health`'s `serving_best` is what a gate asserts rather than
something only a human reads~~ ✅ · 4.9 defines how a promoted checkpoint is
obtained in CI (or states that it is not, and what compensates) · the
false-positive suite from 4.8 runs against a served model, not a fallback.
**Effort:** 2 h spent; the remainder folded into 4.8/4.9. **Depends:** 4.8, 4.9.

### ✅ 1.8 — Async job system (Redis + Celery)

**Done 2026-08-25.** The graph no longer runs on the event loop that serves
requests. `services/worker/` is a Celery app with three queues by cost class;
`services/api/jobs/` is the API's half — a cached broker probe, the progress
journal behind an interface, and cost-class routing. `routes/investigations.py`
was not edited: 1.6 wrote that "the shape here — start, journal, follow, persist
— is deliberately the shape a queue backend would keep, so 1.8 changes where
`_drive` runs and not what a route calls", and that turned out to be true.

**The journal was the hard part, not the queue.** 1.6's journal is a Python list
on the object running the graph, and its reconnect contract rests on a follower
holding an *index* into that list. Once the worker is a different process, the
list is invisible to the API serving the stream. So it became an interface with
two implementations — `MemoryJournal` (1.6, unchanged) and `RedisJournal` (a
list, a pub/sub channel in place of the `asyncio.Event`, a TTL in place of the
eviction sweep) — and `test_jobs_journal.py` runs **the same conformance tests
against both**, so a behaviour that holds in memory and not in Redis is a
failure rather than a discovery in 1.9. That parametrisation caught the one real
journal defect: a follower resuming from an index at or past the end of a
*finished* Redis journal yielded nothing and then waited forever on a channel
that would never carry another message, because "done" was being decided from
the events that call happened to emit rather than from the journal.

The state snapshot is stored beside the events rather than derived from them.
`GET /{id}` must not disagree with the stream, and an event carries only what a
node *added* — accumulating them would rebuild a state one fragment-merge away
from the real one, which is the same hazard `investigate_stream` documents about
reconstructing from `updates`.

**Where a queue tag goes, and where it does not.** `queue:in_process` is
reported on the 202 and on `/api/health`, and deliberately **not** written onto
`InvestigationState.degraded`. Where an investigation executed is a property of
the deployment, not of the case: the analysis is identical either way, and
`stores/probe.degraded_tags()` had already settled the same question for
Postgres — an absent stack is the documented zero-setup default, not a
degradation. 1.7's own notes record what happens otherwise: a tag raised on
every case is a field people stop reading. Two tags do go up: `queue:unavailable`
on the *case*, when the broker answered PING and then would not take the job —
a real, per-case failure — and `queue:no_workers` on *health*, for the one
unambiguously broken state, a reachable broker nobody is consuming.

**Crash safety is four settings, not code.** `task_acks_late`,
`task_reject_on_worker_lost`, `worker_prefetch_multiplier = 1`, and the
visibility timeout. They are one decision, and `test_jobs_worker.py` asserts
each by name with the reason attached, because a silent default change would
otherwise only surface as work disappearing in production. The fourth is the one
that is easy to miss: Celery's Redis default is **3600 s**, so a SIGKILLed
worker's job is redelivered an hour later — the guarantee holds and nobody waits
for it. `AEGIS_QUEUE_VISIBILITY_TIMEOUT` defaults to 1800 s, which must stay
*longer* than the slowest task or a merely-slow job is handed to a second worker.

**Verified end to end 2026-08-25**, against a real Redis, a real Celery worker
and a durable SQLite store, with the MuRIL checkpoint loaded:

| Acceptance criterion | Measured |
|---|---|
| a 90-second APK-shaped stub runs off the request path | `aegis.sandbox.probe(90)` on the `sandbox` queue; `POST /api/investigations` answered **202 in 52 ms** while it ran, and the investigation completed with 6 agent results before the probe was a third done |
| API returns in <1 s with a pending investigation that later completes | 202 in **20–66 ms** across runs, `status: QUEUED`, `GET /{id}` immediately readable as QUEUED, **COMPLETE after 2.1 s** with a report and a 6-span trace |
| worker crash loses no work | a 120-second job, worker **`kill -9`** mid-task. Redis then held it in `unacked` (1) with the queue list empty — not lost, not acked. A restarted worker was redelivered **the same task id** `3817d741-…` ~30 s later and ran it to completion. Separately: a case submitted with **no worker running at all** stayed QUEUED, raised `queue:no_workers` on health, and completed with 5 agent results the moment a worker started |

Also verified on the running pair: the SSE stream **crosses processes** — the
worker wrote the journal into Redis and the API served it, nine events, seq 1–9
contiguous, `Last-Event-ID: 3` resuming as exactly 4–9 with no duplicate. And
the degradation path in the live app: `docker stop aegis-redis` →
`execution.mode: in-process`, submission answered in **19 ms** with
`queue:in_process` on the 202, graph completed in-process with 5 agents.

Fixing that last path found a second real defect. The broker probe is cached for
ten seconds, so "reachable" is a fact about the recent past; a broker that went
away inside that window raised out of the journal's first write and turned a
submission into a **500** — invariant 4's failure arriving through the machinery
built to honour it. Every Redis touch on the submission path is now inside one
try, with the in-process fallback under it.

**Four gates green — 518 tests** (451 → 518: 67 new across
`test_jobs_journal.py`, `test_jobs_dispatch.py` and `test_jobs_worker.py`),
contract consistent, frontend typecheck and production build clean; ruff clean
and mypy clean over 37 files, the gate now covering `services/api/jobs` and
`services/worker`. Run three ways: with a broker (518 passed), with
`AEGIS_REDIS_URL` at a closed port (495 passed, 23 skipped — the CI shape), and
with `AEGIS_REQUIRE_SERVING_BEST=1` against the real checkpoint (518 passed).
CI now runs a Redis service container so those 23 stop being skipped there,
which is 1.7b's lesson applied to the code this task added.

**Limitations, stated.** The `sandbox` queue is a **cost class, not yet a
security boundary**. Which queue a job takes is decided at dispatch from the
filename and declared MIME type — the only things known before the graph's
classifier node sniffs the bytes — so an APK renamed `photo.jpg` runs on `fast`.
That is sound for scheduling and costs a worker slot; 2.8 brings the
network-less container, and must enforce isolation where the sniffed type is
known rather than trusting that guess. There is no worker container in
`infra/compose/dev.yml`: the stack is infrastructure-only and the API already
runs on the host, so the worker does too (`make worker`). And `acks_late` means
a job can run twice — everything a run writes is keyed on the case id so a
redelivery overwrites, but an agent that ever acquires a side effect outside
those keys needs its own idempotency key.

**Effort:** 8 h estimated. **Depends:** 0.4, 1.5. ✅

### ✅ 1.9 — Frontend: investigation launcher + live progress

**Done 2026-08-25.** `/investigate` is the first reader the per-node event
stream has ever had. Everything an investigation needs has existed on the server
since 1.6; until now submitting one was a `curl` command. `pages/Investigate.tsx`
plus the lifecycle half of `lib/api.ts` closes that, behind the same deliberate
sign-in the other analyst surfaces sit behind — the POST route requires the
`analyst` role, so the page is listed on Profile rather than in the citizen nav.

**The SSE client is `fetch()` and a `ReadableStream`, not `EventSource`.** That
is a cost 1.6 chose deliberately and this task pays: `EventSource` cannot set
request headers, which is why so many SSE endpoints end up accepting `?token=…`,
and a bearer token in a URL is written to every access log, proxy log and
browser history entry it passes through. So the client does its own framing —
about forty lines — and reconnects with `Last-Event-ID`, which makes resume
arithmetic rather than a promise. Retries are bounded at five with backoff; a
stream that cannot be re-established falls back to `GET /{id}`, because the
durable record is a better answer than an invisible loop.

**Progress is arithmetic over two contract fields and nothing else.** The
denominator is `plan`, sent on `accepted` before any node has run; the numerator
is `nodes_done`, sent when a node has actually finished. Nothing interpolates or
estimates. Both facts are already pinned by the backend suite — 
`test_investigations_api.py` asserts `accepted` carries the full plan with
`nodes_done == 0`, and that the completions are exactly 1..N — so the claim the
UI rests on is tested underneath it.

**Verified against the running application 2026-08-25**, with a real API, a real
Celery worker and a real Redis, driven from a real browser:

| Acceptance criterion | Measured |
|---|---|
| every input type submittable | pasted message → `TEXT, URL, UPI_ID` detected from one artefact, 6 agents. A two-file multipart drop (`notice.png` + `headers.eml`) → 2 evidence items, `TEXT, EMAIL, UNKNOWN`, 7 agents. Both through the same route |
| progress reflects real node completion, not a fake timer | the worker was **stopped** and a case submitted. Nine seconds later: `0 of 7 steps`, bar at **0%**, plan rendered, zero agents — the bar had not moved a pixel. The worker was started; the run went to `7 of 7 · COMPLETE` with its agents. A timer cannot produce that, and neither can this page |
| degraded agents shown as degraded, not hidden | the API and worker were restarted with `AEGIS_ARTIFACTS` pointing at nothing, which makes `stage_classifier` report DEGRADED for real. It rendered with an amber rail, a `degraded` chip and its own error — *"serving the lexical fallback; no promoted checkpoint"* — next to the run-level `agent:stage_classifier:degraded`. The file submission produced two degraded agents and showed both |
| keyboard accessible, works light + dark | the evidence chooser is a real radiogroup with roving tabindex and Arrow/Home/End, wrap verified in both directions; the dropzone is a `<button>`, not a div with a click handler; focus moves to the `aria-live` region on submit. Rendered in both themes from tokens only, and no horizontal overflow at 375 px |

An unscored investigation says so. The judgement tier has no agents until 4.6
and 4.7, so the result panel prints *"Not scored"* and the reason — never a risk
of zero, which is the one lie the whole contract is arranged to prevent. The
`queue:in_process` note from 1.8 renders too, in the honest form: the run is not
durable, the case file already is.

**Four gates green — 518 tests** (unchanged: this task adds no backend
behaviour), contract consistent, frontend typecheck and production build clean;
ruff and mypy clean. No console errors in the browser across the whole flow.

**Limitations, stated.** There is **no frontend test runner in this repository**,
so nothing above is held by a frontend test — the criteria were verified in the
running application, which the working agreement ranks above a green suite, and
the contract underneath them is covered by the backend suite. Adding vitest and
Testing Library is a new gate and a new dependency set; it belongs to 7.x with
the rest of the frontend work rather than folded in here. Two other things this
page does not do: there is no in-app view of the report JSON — the hand-off is
the PDF and `/reports` — and the trace endpoint 1.6 serves is not rendered at
all, which is **7.3**'s React Flow view rather than a gap here.

**Effort:** 12 h. **Depends:** 1.6. ✅

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
