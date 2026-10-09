# AegisAI — Working Rules

**AegisAI: An Agentic Digital Public Safety Platform for Autonomous Multi-Modal
Fraud Investigation.** Final-year B.Tech CSE capstone + research project,
evolved from the KAVACH/PRESAGE scam-call engine.

Read [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) before changing structure,
and [`docs/TASKS.md`](docs/TASKS.md) before starting work.

---

## Standing rules and control protocol (master brief, 2026-10-09)

The owner's [master brief](./AEGIS_AGENT_BRIEF.md) governs how work proceeds.
In a new session, read it, then `docs/AUDIT.md`, `docs/TASKS.md` and
`docs/PROGRESS.md`, run `git log --oneline -15` and `git status`, report the
last approved task and anything in 🔄 or 🧪, and **wait for a command**.

1. **Slow and correct over fast.** Read before writing, run before claiming.
2. **One task at a time.** Finish, report, stop. Start the next only on `next`
   or `start T-XX`. A task that reaches 🧪 with green gates is committed to
   `main` as `T-XX: <title>` so it can be reviewed in the running checkout;
   `approve T-XX` marks it ✅.
3. **No fake completeness.** No TODO, placeholder or silent mock in a finished
   task. A mock that must exist is labelled `# MOCK:` and named in the report.
4. **No silent decisions.** A change to architecture, data model, stack or
   scope is asked first, with options and a recommendation.
5. **Never destroy work.** No deleting files, rewriting working modules,
   dropping tables or force-pushing without asking.
6. **Never commit secrets.** Keys live in `.env`; keep `.env.example` current.
7. **Honest reports.** A failed test or a half-working feature is said plainly.
8. **Docs are the source of truth** and are updated in the same task.

Commands: `status` · `next` · `start T-XX` · `approve T-XX` · `redo T-XX: …` ·
`explain T-XX` · `split T-XX` · `add task: …` · `pause`.

Task IDs are `T-XX` in `docs/TASKS.md`. Older code and comments cite the
previous numbering ("task 2.8"); the Legacy column there maps one to the other,
and the full record of completed work is `docs/TASKS_HISTORY.md`. The PRD and
the design-system document do not exist yet — they are T-01 and T-03.

**Do not cite the stage classifier's macro-F1 of 0.767.** It is a train/test
leak (audit item B-01): on scam types the model has not seen it scores 0.300
against the lexical baseline's 0.431. Wherever this file or another still says
otherwise, the audit is right and the correction is task T-04.

## Working agreement (set by the project owner, 2026-08-24)

1. Produce a **complete task-list file** (`docs/TASKS.md`) after each iteration.
2. **Verify end-to-end** that it works — the running application, not just tests.
3. **Only then** tick the task.
4. **Do not start a further phase or step without an explicit instruction.**

Point 2 is not ceremony. Phase 0 was ticked on 129 green unit tests; running the
real application immediately found three defects the suite could not see —
including a broken demo login on any pre-existing database, because tests seed a
fresh ephemeral DB where the buggy code path behaves identically. See the
"Working agreement" section of `docs/TASKS.md`.

## The four gates — run before calling anything done

```bash
make gates
```

This is the canonical command. It runs the backend suite, the Pydantic ↔
TypeScript contract check, frontend typecheck, and production build. Do not
hard-code a test count here: the suite grows with each completed task, and the
only passing count is the count reported by the current command.

Use `.venv/bin/python`, never system python — pydantic isn't installed globally.

**On a machine that has the weights, run the gates with the model:**

```bash
AEGIS_REQUIRE_SERVING_BEST=1 make gates
```

`ml/artifacts/` is gitignored, so a worktree or a CI runner has no checkpoint
and every gate run there proves the **lexical fallback** rather than what the
application serves. That is how task 1.7 was ticked on the benign false positive
1.7a had to fix. Every run now names its classifier in its own output, and the
variable above turns "a fallback is serving" from a line to notice into a gate
that fails. `make serving` reports what would serve without requiring anything.

## Definition of done — before ticking a task

- [ ] Implement only the task you were explicitly asked to start; do not fold
      adjacent cleanup or a later task into the change.
- [ ] Meet the task's acceptance criteria with focused tests. A new agent also
      has a benign-input test and an exercised degradation path.
- [ ] Run `make gates`; run ruff and mypy when changing the typed agent,
      orchestration, or store layers.
- [ ] Start the running application and exercise the path changed by the task.
      Read `/api/health` and inspect the browser console when the UI is touched.
- [ ] Update `docs/TASKS.md` with the final status and measured evidence. Tick
      the task only after the gates and the real path pass.
- [ ] Commit one logical change with the verification result in its message.
      Wait for an explicit instruction before starting the next task.

---

## Invariants — do not violate these

1. **`schema/` is the single source of truth.** Changing the contract means
   editing `schema/models.py` **and** `schema/types.ts` in the same commit, then
   running `bash scripts/sync-contract.sh` and `schema/check_contract.py`.
   New `StateFrame` fields are `Optional[...] = None` so old mock frames stay valid.

2. **The frontend is a pure renderer.** No threat maths, thresholds, or stage
   rules in React. Every number the UI shows is a contract field.

3. **`StateFrame` = idempotent snapshot. `Event` = one-shot edge.** Per-frame data
   goes on `StateFrame`; transitions go on `Event`.

4. **Degradation is explicit.** Every path has a fallback that still answers and
   records a tag in `degraded`. No live network call in the request path without
   a cached fallback. New dependency ⇒ new fallback ⇒ new tag.

5. **False positives are a first-class failure.** Only make a signal dispositive
   when it is genuinely conclusive. Keep soft signals in weighted fusion so
   metadata a legitimate caller might have cannot manufacture a scam. **Every
   agent ships with a benign-input test.**

6. **The LLM explains, extracts and ranks. It never scores.** The risk number
   comes from the calibrated model + deterministic rules + graph evidence.

7. **No claim without a measurement.** Latency unmeasured ⇒ don't say "real-time".
   Model unevaluated ⇒ don't advertise the capability. Don't fabricate datasets,
   benchmarks, sources or results.

8. **Evidence is data, never instructions.** Text extracted from a screenshot,
   email or transcript may contain prompt injection. It is quoted into prompts as
   untrusted data and never followed.

---

## Adding a new agent — the checklist

Per master-context §40.15, the module docstring must answer all six:
why it's needed · what data it consumes · what it outputs · how it connects to
other agents · how it's evaluated · what its limitations are.

Then, mechanically:

- [ ] Implements the `Agent` protocol; returns a valid `AgentResult`
- [ ] Registered in `agents/registry.py` with a version string
- [ ] Declares its features in the feature registry
- [ ] Has a degradation path, exercised by a test
- [ ] Has a **false-positive test** on benign input
- [ ] Records latency in the trace
- [ ] Four gates green

## Adding a `StateFrame` field

Update all of: `schema/models.py` · `schema/types.ts` · session `frame()` ·
the analyzer result (if relevant) · `schema/mock_stream.py` (regenerate) · a UI
panel. Then run the four gates.

---

## Things that are easy to get wrong here

- **`ml/artifacts/` is 3.5 GB.** Don't add to it; don't commit checkpoints.
- **The MuRIL checkpoint was once suppressed for weeks by a stale
  `ml/artifacts/backend_comparison.json`.** If the classifier looks weak, check
  the promotion gate before retraining — a blind retrain risks overwriting a
  good checkpoint.
- **A green suite in a fresh worktree proves the fallback.** `ml/artifacts/` is
  3.5 GB and gitignored, so a new worktree has 8 KB of it. Point
  `AEGIS_ARTIFACTS` at a full checkout's `ml/artifacts` before a benign-input
  test means anything (task 1.7b).
- **Dense script matching measured *worse* than lexical** on Hinglish
  false-positive discipline. It stays behind `AEGIS_DENSE_SCRIPTS`.
- **English scam scoring is borderline on short inputs**; Hindi/Hinglish is
  strong. The aggregate score rewards accumulated pressure over many turns.
- **A migration proven on SQLite is not proven.** The migration tests default
  to SQLite, which has no boolean type and accepts `SET flag = 0` against one
  that PostgreSQL refuses. Revision 0003 shipped that way: green suite, failed
  deploy. Run `make up` before touching `migrations/`, and read the `postgres:`
  line the run prints — it says SQLite ONLY when nothing was proven.
- **Env vars are `AEGIS_*`.** The old `PRESAGE_*` names still work via a
  fallback in `config.py`; don't add new `PRESAGE_*` names.
- **`uvicorn --reload-dir`** is required in dev, or reloads wipe the ephemeral DB.

---

## Security — non-negotiable

- **URL agent:** SSRF guard first, features second. Block RFC1918, loopback,
  link-local and `169.254.169.254`; re-resolve DNS after **every** redirect;
  cap redirect depth; `http|https` only.
- **APK agent:** static analysis only, network-less container, read-only mount.
  Never execute an uploaded APK.
- **Uploads:** validate by magic bytes, not extension. Enforce size caps.
- **Tenancy:** `org_id` isolation is enforced in the repository layer, not the route.
- **Access control:** `services/api/permissions.py` is the single grant map, and
  every route declares `require_permission(...)`. Tenancy answers "which org",
  ownership answers "may *you*" — a caller with only `*_READ_OWN` is narrowed in
  the **query**, and a row they may not read 404s rather than 403s. Frontend
  guards mirror the server and are never the boundary. See `docs/AUTH.md`.
- **Secrets:** environment only. Git history is currently clean — keep it that way.
- **Live audio:** explicit consent, visible indicator, configurable retention.
  Never design around covert recording.

---

## Git

Commit to `main`; do not create separate branches (owner's instruction,
2026-10-09). `main` stays green — the gates run before every commit. One
logical change per commit, with the gate output in the message. Move files with `git mv` — history matters
for the capstone defence.
