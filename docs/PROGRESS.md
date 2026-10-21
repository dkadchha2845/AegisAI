# AegisAI — Progress Log

One entry per finished piece of work, newest last. A new session reads this
after [`TASKS.md`](TASKS.md) to find where things stand.

**Current state (2026-10-21):** Phase 0 and Phase 3 approved. T-04 approved
2026-10-10. **T-05 and T-69 are 🧪 awaiting review**, committed to `main`.
T-69 (landing fixes through section 02) was added on the owner's request ahead
of the recommended order; the owner will continue with the later sections.
Next in the recommended order: T-06.

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

## T-05 — Make the promotion gate refuse a contaminated comparison — 2026-10-10

- What changed: a checkpoint can no longer be promoted on data it was trained
  on. `train.py` now leaves `training_data.json` beside the weights — one short
  hash per training and validation text. `make eval` checks the test split
  against it before loading the checkpoint, and if any test turn is in it, or
  there is no record, it does not score the checkpoint: it writes the refusal
  and exits 2. The API promotes only on a comparison marked valid with a clean
  leak check; a missing, unreadable, refused or old-format comparison leaves
  the lexical model serving and says why. "No comparison on file" used to mean
  "trust the checkpoint"; it now means the opposite.
- **Effect on the product: the lexical classifier now serves, on every
  machine.** Run for real against the served weights, the gate refused:
  311 of 423 test turns are the checkpoint's own training data.
- Files: `ml/evaluation/provenance.py` (new), `ml/evaluation/eval_backends.py`,
  `ml/evaluation/manifest.py`, `ml/training/train.py`,
  `services/api/engine/classifier.py`, `services/api/main.py`,
  `services/api/routes/research.py`, `apps/web/src/pages/ModelCard.tsx`,
  `apps/web/src/lib/api.ts`, `ml/artifacts/backend_comparison.json` and
  `ml/artifacts/checkpoint_manifest.json` (regenerated by the gate),
  `services/api/tests/test_promotion_gate.py` (new),
  `services/api/tests/test_checkpoint_manifest.py`,
  `services/api/tests/test_serving_backend.py`, `CLAUDE.md`, `docs/AUDIT.md`,
  `docs/TASKS.md`
- Tests: 37 new cases in `test_promotion_gate.py`, one of which replays the
  incident from git history. Backend suite 635 passed, 26 skipped, 0 failed, in
  three configurations: no checkpoint; checkpoint present; checkpoint present
  with `AEGIS_REQUIRE_SERVING_BEST=1`. Contract consistent; ruff and mypy
  clean; frontend typecheck and build clean.
- Running application, before and after, same six messages: the Hinglish
  digital-arrest script scores 93 CRITICAL on both; the bank debit, delivery
  and KYC-reminder messages score 7.5 CALM on both; the English KYC phish
  scores 95 CRITICAL on both. The live four-turn arc names the same stages.
  One message moved: an English courier scam, 32 → 25, WATCH both times and
  missed both times (B-08).
- Known limitations: `train.py` and `eval_backends.py` need torch and the
  weights, so their wiring is checked by reading their source, not by running
  them in the suite; the real run above is the evidence that they work. The
  record for the current checkpoint was **backfilled** from git commit
  `85a2aee` and says so — it is an assertion, supported by the 0.221 that
  reproduces from that split, not a proof. The match is on exact text, so it
  does not see a shared archetype (B-07). No valid comparison of real weights
  exists yet, so the "all three backends scored" path has only been exercised
  with a fixture. No mocks.
- One existing test was changed, not just added to:
  `test_checkpoint_present_but_not_loaded_is_never_reported_as_best` assumed a
  present-but-unloaded checkpoint always meant a failed load. It now allows the
  case where the gate declined it and the reason says so.
- Found and not fixed: **B-08** (English courier scam scored legitimate) and
  **D-13** (the same lexical model is labelled a fallback on a clean clone and
  "best available" beside the refused checkpoint).
- How to verify:
  1. Run `make eval` — expect "REFUSED: 311 of the 423 test turns…", exit 2
  2. Run `make serving`, then open `http://localhost:8000/api/health`
  3. Expect: backend `lexical`, a reason naming the overlap, and no
     `clf:lexical_fallback` tag. Open `/model` signed in as Analyst: one
     figure, lexical, marked as currently serving

## Decisions — 2026-10-09

The owner approved both documents and delegated the open questions; the
decisions are tabled in `docs/AUDIT.md` §9. Still open: the SAGE paper (blocks
T-40) and the team and review dates (placeholders in the PRD). All work is
committed to `main`, with no separate branches.

## T-69 — Landing: fix the hero, the problem web and the evidence grid — 2026-10-21

- What changed:
  - **Hero.** The pill label ("● AEGISAI · AGENTIC DIGITAL PUBLIC SAFETY") is
    now a plain kicker: an accent rule and "Agentic digital public safety".
    The primary button is no longer magnetic — it drifted up to 26px sideways
    and 11px down toward the cursor and left its neighbour behind. The two
    buttons share a row, a height and a top; "Explore the system" gained an
    arrow. "Explore the system" and "Scroll" were bare anchors that jumped
    instantly and parked the section under the bar; they now use the same
    smooth, bar-clearing scroll as the nav (`scrollToSection`).
  - **Hero network.** Rebuilt on the structure the owner chose: four analysis
    lanes — Voice (phone call, voice note), Text (message, email), Vision
    (screenshot, QR code), Identity (UPI ID, caller number) — feeding the core.
    It was nine inputs wired to four hubs by angle alone, which produced
    pairings such as a phone call feeding "Risk", one hub with three inputs
    and an edge through every hub label. The owner's choice listed "URL" in
    the last lane; the link scanner is not built, so it is "Caller number",
    and the lane is named Identity. Labels are sized in container units and
    stay legible; packets travel input → lane → core and the core pulses on
    each arrival.
  - **The motion defect behind "misplaced".** The problem chips (and the
    hero's nodes) were centred with `translate(-50%, -50%)` on the same
    element GSAP animated, and the chips also had a CSS `transition` on
    `transform`. GSAP recorded a half-transitioned matrix as the end state:
    measured in the running page, chips settled up to 92px off their line ends
    and three (Email, Website, Screenshot) stayed at half size. Every
    positioned node now sits in a slot that owns the centring and never
    animates. The same transition conflict existed on `.lp-btn` (press) and
    `.lp-card` (hover lift); both now use the individual `scale` /
    `translate` properties, which compose with GSAP instead of fighting it.
  - **Problem web.** Chips land on their lines; after the web forms, one
    signal at a time travels from a channel into "One operation", which
    flashes as it arrives, replacing a flickering line opacity.
  - **Evidence.** The staggered offsets (0/34/0/62px) read as misalignment,
    and because a transform takes no layout space, the note sat beside the
    lowest cards. Now an aligned 4×2 grid of equal cards, each ending in the
    name of what reads it. One entrance per row, left to right; each icon has
    its own small gesture. Four cards described things that are not built —
    a link scanner with an SSRF guard, email-header analysis, video, APK
    analysis — and the footer said uploads are "validated by magic bytes"
    (true of the investigation intake, not of `/api/analyze`). They are
    replaced by Message, UPI ID, Caller number and Document, and every card's
    copy was checked against `routes/analyze.py`, `engine/ocr.py`,
    `engine/upi.py`, `engine/spoofing.py` and `ingest/asr.py`.
- Files: `apps/web/src/components/landing/HeroSection.tsx`,
  `HeroNetwork.tsx`, `ProblemSection.tsx`, `EvidenceSection.tsx`,
  `apps/web/src/lib/landing-motion.ts`, `apps/web/src/styles/landing.css`,
  `docs/TASKS.md`, `docs/PROGRESS.md`
- Tests: no frontend harness exists yet (T-15). Measured in the running page
  at 1470×801: buttons at the same top (527) and height (50); network nodes
  centred within 1px of their computed points; all 11 problem chips 0px from
  their line ends at scale 1; evidence cards all 295×309, reader lines aligned
  per row, note 36px under the grid. No overlap and no horizontal scroll at
  1470, 1024, 768, 430 and 375. Light theme and reduced motion checked
  (everything visible at rest, no stray packets). Both in-page links land
  their section 68px from the top. Four gates green.
- Known limitations: the browser pane used for verification was hidden, so
  it delivered no animation frames; GSAP and ScrollTrigger were stepped by
  hand to reach each settled state. The geometry is measured; the *feel* of
  the motion at 60fps needs the owner's eye. `useMagnetic` is still used by
  the closing section's button, which was out of scope. No mocks.
- How to verify:
  1. `make api` and `make web`, open `http://localhost:5173/`
  2. Hover both hero buttons; click "Explore the system"; scroll through 01–02
  3. Expect: the buttons stay in one row; the network is symmetric with
     packets reaching the core; chips land on their lines; eight even cards

