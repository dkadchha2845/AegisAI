# AegisAI — Progress Log

One entry per finished piece of work, newest last. A new session reads this
after [`TASKS.md`](TASKS.md) to find where things stand.

**Current state (2026-10-10):** Phase 0 and Phase 3 approved. T-04 approved
2026-10-10. **T-05 is 🔄 in progress.**

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

## T-04 — Correct the stage-classifier claim everywhere it is stated — 2026-10-09

- What changed: the leaked macro-F1 of 0.767 is no longer stated as a result
  anywhere. Nine documents now give the measured figures (0.300 MuRIL against
  0.431 lexical on the 112 unseen turns) and say what happened. Four code
  comments that told the story backwards — "a stale 0.221 suppressed a 0.767
  checkpoint" — are corrected. The sentence the API serves beside the
  comparison no longer says "held-out"; it is one constant,
  `classifier.EVALUATION_PROTOCOL`, used by the model card and the research
  overview. The Model card heading "Measured, not assumed" is now
  "Promotion-gate comparison".
- Files: `README.md`, `CLAUDE.md`, `docs/RESEARCH.md`, `docs/INVENTORY.md`,
  `docs/DATASETS.md`, `docs/DEPLOYMENT.md`, `docs/TASKS_HISTORY.md` (one dated
  correction at its head), `docs/adr/0003-adapt-not-rewrite-the-engine.md`,
  `docs/ROADMAP.html`, `docs/build-dossier.html`, `docs/AUDIT.md`,
  `ml/evaluation/manifest.py`, `ml/evaluation/eval_backends.py`,
  `schema/check_contract.py`, `services/api/engine/classifier.py`,
  `services/api/main.py`, `services/api/routes/research.py`,
  `apps/web/src/pages/ModelCard.tsx`,
  `services/api/tests/test_checkpoint_manifest.py`,
  `services/api/tests/test_contributor_docs.py`
- Tests: 21 new cases in `test_contributor_docs.py`. Backend suite 598 passed,
  26 skipped, 0 failed — run twice, on the lexical fallback and with
  `AEGIS_REQUIRE_SERVING_BEST=1` against the real checkpoint. Contract
  consistent; ruff and mypy clean; frontend typecheck and build clean.
  Running app: `/api/model/card` and `/api/research/overview` serve the new
  sentence; `/model` renders it under the new heading.
- New measurement: on the original 171-turn test split, the one these weights
  were held out from, MuRIL scores 0.221 and lexical 0.372. 0.221 is the figure
  committed with the weights. It was never stale.
- Known limitations: **the gate still promotes the checkpoint.** `/api/health`
  still gives the leaked comparison as its reason ("measured better (0.767 vs
  0.375)"), and the Model card still draws that leaked 0.767 large and green as
  "currently serving" — both come from the gate, which is T-05. One test fixture still contains the string. No mocks.
- Found and not fixed: **B-07** (three archetypes sit on both sides of the
  current split) and **D-12** (stale hand-written Model card limitations), both
  recorded in `docs/AUDIT.md`.
- How to verify:
  1. Run `grep -rn "0\.767" README.md docs CLAUDE.md`
  2. Run `make api` and `make web`, sign in as Analyst, open `/model`
  3. Expect: every hit is qualified, and the page says the comparison includes
     data the model was trained on

## Decisions — 2026-10-09

The owner approved both documents and delegated the open questions; the
decisions are tabled in `docs/AUDIT.md` §9. Still open: the SAGE paper (blocks
T-40) and the team and review dates (placeholders in the PRD). All work is
committed to `main`, with no separate branches.
