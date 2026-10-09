# AegisAI — Progress Log

One entry per finished piece of work, newest last. A new session reads this
after [`TASKS.md`](TASKS.md) to find where things stand.

**Current state (2026-10-09):** Phase 0 and Phase 3 approved and committed to
`main`. Execution has started with T-04.

---

## Phase 0 — Deep audit — 2026-10-09

- What changed: no code. Wrote `docs/AUDIT.md`.
- Files: `docs/AUDIT.md`
- Tests: `AEGIS_REQUIRE_SERVING_BEST=1 make gates` in the main checkout —
  exit 0; 603 collected, 577 passed, 26 skipped, 0 failed; contract consistent;
  typecheck and build clean. ruff and mypy clean. The API was booted on an
  ephemeral database and exercised over HTTP and in the browser.
- Known limitations: the dev stack was down, so nothing behind Postgres, Redis,
  Neo4j or Qdrant was verified (the 26 skips). Audio and image analysis, a
  fresh clone, dependency audits and the deployed site were not checked. Each
  is listed in `docs/AUDIT.md` §1.
- Headline finding: **B-01** — the stage classifier's macro-F1 of 0.767 is a
  train/test leak. 311 of the 423 test turns are verbatim in the data the
  served weights were trained on. On the 112 unseen turns MuRIL scores 0.300
  and the lexical baseline 0.431.
- How to verify: read `docs/AUDIT.md`; reproduce B-01 with the steps under it.

## Phase 3 — Phase and task list — 2026-10-09

- What changed: the previous task list was moved, unmodified, to
  `docs/TASKS_HISTORY.md`; a new `docs/TASKS.md` was written in the brief's
  format; `CLAUDE.md` gained the brief's standing rules and command protocol;
  `AEGIS_AGENT_BRIEF.md` was added to the tree.
- Files: `docs/TASKS.md`, `docs/TASKS_HISTORY.md`, `docs/PROGRESS.md`,
  `CLAUDE.md`, `AEGIS_AGENT_BRIEF.md`
- Tests: backend suite run against this tree after the change — 577 passed,
  26 skipped, 0 failed (lexical fallback: this worktree has no weights);
  `test_contributor_docs.py` 21 passed; contract consistent; every Markdown
  link in the four touched documents resolves. Frontend untouched.
- Known limitations: written **before** the PRD and architecture update, at the
  owner's request, so those are its first three tasks rather than its inputs.
  32 of the 68 tasks are work packages, to be split into single-sitting tasks
  when their milestone opens. Three tasks are blocked on open questions (Q4,
  Q5, Q7).
- How to verify: read `docs/TASKS.md`; answer the questions in
  `docs/AUDIT.md` §9.

## Decisions — 2026-10-09

The owner approved both documents and delegated the open questions; the
decisions are tabled in `docs/AUDIT.md` §9. Still open: the SAGE paper (blocks
T-40) and the team and review dates (placeholders in the PRD). All work is
committed to `main`, with no separate branches.
