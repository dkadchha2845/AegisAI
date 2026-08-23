# AegisAI — Working Rules

**AegisAI: An Agentic Digital Public Safety Platform for Autonomous Multi-Modal
Fraud Investigation.** Final-year B.Tech CSE capstone + research project,
evolved from the KAVACH/PRESAGE scam-call engine.

Read [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) before changing structure,
and [`docs/TASKS.md`](docs/TASKS.md) before starting work.

---

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
.venv/bin/python -m pytest services/api/tests -q      # 84 tests must pass
.venv/bin/python schema/check_contract.py             # Pydantic ↔ TypeScript
npm run typecheck --prefix apps/web
npm run build --prefix apps/web
```

Use `.venv/bin/python`, never system python — pydantic isn't installed globally.

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
- **Dense script matching measured *worse* than lexical** on Hinglish
  false-positive discipline. It stays behind `AEGIS_DENSE_SCRIPTS`.
- **English scam scoring is borderline on short inputs**; Hindi/Hinglish is
  strong. The aggregate score rewards accumulated pressure over many turns.
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
- **Secrets:** environment only. Git history is currently clean — keep it that way.
- **Live audio:** explicit consent, visible indicator, configurable retention.
  Never design around covert recording.

---

## Git

Branch before working; `main` stays green. One logical change per commit,
with the gate output in the message. Move files with `git mv` — history matters
for the capstone defence.
