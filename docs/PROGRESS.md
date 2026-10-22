# AegisAI — Progress Log

One entry per finished piece of work, newest last. A new session reads this
after [`TASKS.md`](TASKS.md) to find where things stand.

**Current state (2026-10-22):** Phase 0 and Phase 3 approved. T-04 approved
2026-10-10; T-05, T-69, T-70, T-01, T-02 and T-03 approved 2026-10-22; T-71
and with it T-06, T-09, T-10, T-11, T-12, T-13, T-14, T-15, T-18 and T-20
approved 2026-10-22. Open for the owner: S-08 (reset tokens in the log) and
S-06 (rotate the Gemini key). The remaining landing sections (05, 07, 08,
10–12) await the owner's feedback. Next in the recommended order: T-07.

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

## T-70 — Landing: the investigation rail, the agent diagram, the intelligence graph, the research sidebar — 2026-10-22

- What changed:
  - **03 — the investigation rail.** GSAP scrubbed each step's opacity while
    the stylesheet also transitioned it, so the highlight trailed its panel
    (measured: stage 04 current, its step still at 0.34); the fill grew
    linearly while the icons are unevenly spaced, so it reached the last icon
    only as the pin released. The timeline now reports the current stage, each
    step carries `data-state` (done / active / upcoming) and CSS owns the look;
    the fill is driven stage by stage to each icon's measured centre. Steps are
    buttons that scroll to their stage. The panels are unchanged.
  - **04 — the agent diagram.** It claimed "thirteen specialists" in tiers
    ("Correlate", "Geospatial") that are not registered agents; the registry
    has eight in four stages. It now shows the registry — read live from
    `/api/health` with versions, or from a dated snapshot of
    `agents/registry.py` when the API does not answer — each agent with a
    one-line job taken from its module docstring. The layout is ordinary grid;
    the connectors are measured from the boxes (with `offsetTop`, so a card
    mid-entrance does not skew them) and drawn with `pathLength`. The build
    plays once as it comes into view instead of a scrub that finished only
    after its top had left the screen, and a packet now runs core → stage →
    verdict, lighting the stage it passes — the comment had promised that
    while the code faded line opacity.
  - **06 — the intelligence graph.** It was a hand-drawn example including a
    domain and an APK the product cannot analyse; its nodes rendered at
    opacity 0 (a CSS opacity transition against GSAP's) and off their points
    (the centring transform rewritten by GSAP). It now loads campaign FC-001
    from `/api/intel/clusters/FC-001` — 7 shared identifiers, 26 cases, 74
    links, the store's risk factors — with a snapshot of that response
    (`landing/cluster.ts`) when the API fails or needs sign-in. The cases come
    from `seed_cases()`, which the store calls synthetic, and the section says
    so. Added: a summary strip, a legend, per-identifier detail (cases it
    appears in, identifiers it shares cases with, mean threat), per-case
    detail, the top risk factors, and a self-running tour with a pulsing ring
    that stops when the reader hovers. Nodes sit in slots; pill sizes follow
    the stage (`cqw`); below 740px the drawing becomes a row of chips.
  - **09 — research.** A hover selector became eight stacked panels with a
    sticky sidebar that marks the panel being read, fills a progress line and
    jumps on click; on a phone it is a sticky chip strip. Panels show live
    figures from `/api/health`: agent count, LLM backend, retrieval passages,
    store size, the classifier serving and its measured macro-F1, coaching
    lines. The copy no longer says a fine-tuned transformer serves, that
    fusion is calibrated, that intelligence reads registrar and certificate
    data, or that there are thirteen agents.
  - **Nav.** Its section triggers were refreshed before the investigation pin
    added its spacer, so it lit "Research" in Intelligence. They now refresh
    last (`refreshPriority: -1`).
- Files: `apps/web/src/components/landing/InvestigationSection.tsx`,
  `AgentsSection.tsx`, `GraphSection.tsx`, `ResearchSection.tsx`,
  `LandingNav.tsx`, `live.ts` (new), `cluster.ts` (new),
  `apps/web/src/lib/api.ts`, `apps/web/src/styles/landing.css`,
  `docs/TASKS.md`, `docs/PROGRESS.md`
- Tests: no frontend harness yet (T-15). Measured in the running page at
  1470×923: rail fill on the active icon at all seven stages (0px), states
  correct, step clicks land on their stage; agent connectors 0px off their
  boxes, diagram 716px tall with live registry data; graph — no pill overlaps,
  nothing outside the stage, nodes on their computed points, 26 cases and 74
  links, live data; research — active item correct at every panel, in a gap
  and after jumps, clicks mark the chosen item, active chip kept in view on a
  phone; nav correct in five sections. No overlap or horizontal scroll at
  1470, 1024, 768 and 375; light theme and reduced motion checked. `make
  gates`: 635 passed, 26 skipped, 0 failed; contract consistent; typecheck,
  landing session check and build clean.
- Known limitations: the verification pane was hidden and ran no animation
  frames, so GSAP and ScrollTrigger were stepped by hand; the motion at 60fps
  needs the owner's eye. The graph's snapshot will drift if the store's seed
  changes — it is dated on screen. No mocks.
- How to verify:
  1. `make api` and `make web`, open `http://localhost:5173/`
  2. Scroll 03 and click a step; let 04 build; hover 06; scroll 09 and click
     its sidebar
  3. Expect: rail in step with the panels; a whole diagram with a packet
     running; a graph that answers; a sidebar that follows

## T-01 — Write the PRD — 2026-10-22

- What changed: new `docs/PRD.md`, all 13 sections of brief §4 — overview,
  goals and non-goals, four personas, 17 user stories in Given/When/Then, 73
  functional requirements in the brief's groups and 20 non-functional ones,
  the A1–A7 agent table (with how A7 challenges each), the data model, all 73
  API routes, 22 screens plus the new ones, the evaluation plan, risks, and
  milestones. Every requirement says whether it is built, partial or new, and
  names the task that builds it.
- Found while writing it, recorded rather than fixed: **S-07** — 25 routes
  (all of `/api/analyze/*` and `/api/shield/*`, 10 of 13 `/api/session/*`)
  declare no permission and do not identify the caller, although `CLAUDE.md`
  says every route does and `ANALYZE_USE` exists unused; owned by T-59.
  **D-15** — `DATASETS.md` says 1,692 calls, the generated report 338.
  The audit's route count (61) was an undercount; it is 73, corrected.
- Files: `docs/PRD.md` (new), `docs/AUDIT.md`, `docs/TASKS.md`,
  `docs/PROGRESS.md`
- Tests: a document. Every route, column, request field, error code and enum
  value it states was checked against the source before commit; ten were
  wrong in the first draft and corrected (e.g. `AgentStatus` is
  OK/DEGRADED/SKIPPED/ERROR; the 409 belongs to `/stream`, not `/report`).
  `test_contributor_docs.py` 43 passed; every PRD table has a consistent
  column count.
- Known limitations: six `[ASSUMPTION]`s await the owner (team, review dates,
  a sourced FIR-conversion figure, SAGE, the names of the six agents, a
  single-LLM baseline). Request and response shapes are summarised, not full
  schemas — `schema/` remains the source of truth. No mocks.
- How to verify: open `docs/PRD.md`; search `[ASSUMPTION]` and confirm or
  correct each; spot-check three API rows against `services/api/routes/`.

## T-02 — Bring the architecture document to the brief's shape — 2026-10-22

- What changed: `docs/ARCHITECTURE.md` gained, without rewriting what was
  right: a reading guide with status marks (✅ built · 🟡 partial · 🎯 target ·
  🅿️ parked); **§0** the brief's five layers mapped onto the six code layers,
  with a diagram; **§2.1** A7 placed in the target graph between the evidence
  join and feature assembly, with uphold / downgrade / reject edges;
  **§2.2** the graph as it actually runs today (`begin → classify → extract →
  investigate → reason → judge → finish`); **§2.3** A7's position, inputs,
  outputs, deterministic and LLM challengers, effect on the score, failure
  behaviour, tests and evaluation; **§4.1** today's scoring formula, read from
  `engine/threat.py` (weights 0.40 / 0.25 / 0.20 / 0.15, escalators 0.18 and
  0.15 gated at 0.45, a 2.5-point-per-second ratchet, the five bands);
  **§4.2** the calibrated late-fusion target — per-modality scores from
  A7-weighted findings, isotonic or Platt calibration, log-odds fusion fit by
  logistic regression, ECE over 15 bins — and the files it will live in;
  **§10** sequence diagrams for evidence → case file and for live
  intervention; **§11** two pipelines today, one tomorrow; **§12**
  operations — errors, timeouts, retries, degradation tags, logging,
  observability, configuration, secrets.
- Status marks added to existing sections, because they described the target
  as if built: the layered view gained a "today" table (Neo4j, Qdrant and the
  XGBoost risk model are not in use; MuRIL is refused by the gate), the
  real-time section says live intervention runs on text utterances and the
  400 ms budget is unmeasured, and the technology table gained a "Today"
  column (PaddleOCR is not used; Tesseract is the default).
- Files: `docs/ARCHITECTURE.md`, `docs/TASKS.md`, `docs/PROGRESS.md`
- Tests: a document. All 8 Mermaid diagrams were parsed and rendered by
  Mermaid 10.9.1 in a browser (a temporary page, removed). Every number and
  name in §2.2, §4.1 and §12 was read from source: `orchestration/graph.py`,
  `orchestration/policy.py`, `agents/base.py`, `engine/threat.py`,
  `config.py`, `.env.example` (every variable cited is listed there).
- Known limitations: §4.2 and §2.3 are designs; their tasks may refine the
  numbers (bin count, the A7 rule list) and will update this document when
  they do. No mocks.
- How to verify: open `docs/ARCHITECTURE.md` in a Markdown preview; read the
  two sequence diagrams in §10 against the product; check A7 sits where a
  finding can be stopped.

## T-03 — Write the design-system document from the shipped tokens — 2026-10-22

- What changed: new `docs/DESIGN_SYSTEM.md` — visual direction; every token
  from `tokens.css` with its value in both themes (type, spacing, radius,
  shadow, motion, containers, focus, layers, neutrals, inks, accent, the
  threat ramp's fill / dim / ink); the risk levels as colour + label + number
  with their score bands and the brief's names mapped onto them; measured
  contrast; the primitives that exist; the brief's 16 components as have (9),
  partial (5) or missing (2) with paths; layout, navigation and accessibility
  rules; the landing's scoped tokens; and a 14-item gap table that is T-16's
  input.
- Found and recorded, not changed (this task touches no stylesheet):
  **U-08** — the landing's `--lp-ink-3` measures 4.46:1, under AA, where its
  comment claims 4.6:1; `--font-mono` is DM Sans although the comment above
  it says JetBrains Mono (gap G-13); about a dozen ad-hoc breakpoints and no
  breakpoint tokens (G-12).
- Files: `docs/DESIGN_SYSTEM.md` (new), `docs/AUDIT.md`, `docs/TASKS.md`,
  `docs/PROGRESS.md`
- Tests: a document. Token values verified by script against `tokens.css`
  and `landing.css` — no mismatch. Contrast computed with the WCAG 2.1
  relative-luminance formula, translucent tints composited over the surface
  they sit on: every text token clears 4.5:1 in both themes (lowest:
  dark-theme HIGH on its own tint over a hovered panel, 4.73); `--ink-ghost`
  fails, and is non-text only by design; every ratio claimed in
  `tokens.css`'s comments re-measured and holds.
- Known limitations: the proposed breakpoints and the component APIs in §9
  are proposals for T-16, not decisions. No mocks.
- How to verify: open `docs/DESIGN_SYSTEM.md`; pick three tokens and find
  them in `apps/web/src/styles/tokens.css`; values match.

## T-71 — Close the audit's open issues — 2026-10-22 (✅ approved 2026-10-22)

On the owner's instruction ("fix all the bugs, errors, security issues, UI/UX
issues, code quality and tech debt from the audit"), with T-01, T-02 and T-03
approved first. Scoping answers: auth enforced by default (S-01); sessions
public by design with per-session tokens (S-07); the deletions in T-10; make
Analyze and Investigate agree now via T-18 and T-20 (D-01, U-04), without the
full pipeline merge (T-47). One commit per change, each with its gates.

- **Security.** S-01 auth enforced unless `AEGIS_AUTH=0`. S-07 every one of
  73 routes declares its guard, enforced by a test; live sessions need their
  token. S-03 evidence quoted as data in every prompt, tested with a recording
  backend. S-04 per-organisation upload quota. S-09 React Router advisory.
- **Bugs.** B-02/B-03 (via T-18, T-20) investigations extract entities and
  give the same score as Analyze, tagged `score:uncalibrated`. B-04, B-05,
  B-06. B-07 and B-09 the split is archetype-disjoint with five benign calls
  in validation and test. B-08 English scams now floored — and measuring it
  found 9 of 106 genuine calls floored at 87–95 by single words, fixed.
  Found and fixed on the way: B-10 (VPA before a full stop), B-11 (foreign
  caller number typed TEXT), B-12 (fused classifier non-deterministic).
- **Code quality and debt.** D-04 (T-06 experiment 0), D-05 (T-14 prompts),
  D-06 (T-15 frontend tests), D-08 (T-12 logs), D-09 (T-13 error envelope),
  D-12, D-13, D-14, D-15; D-07 changed (CI proves what serves); audit rows for
  T-09/T-10 work (S-05, D-02, D-03) and D-10 brought up to date.
- **UI/UX.** U-02, U-03, U-07, U-08 (T-11); U-04 partly (same score on both
  pages).
- **Found and left open, with reasons:** S-08 — password-reset tokens are
  logged; the email is gone, the token kept because removing it would make
  reset impossible with auth enforced; needs the owner's choice (admin-issued
  reset link recommended). D-16 — the lexical score is not a clean held-out
  figure; needs fresh calls (T-37). The single-split swing (lexical 0.240 vs
  0.397 on two archetype-disjoint splits) means comparisons need folds (T-45).
- **Not code, not done:** S-02 (agents not built), S-06 (rotate the key —
  the owner's), U-05 components (T-16), U-06 Hindi UI (parked), D-11 (the
  schedule), D-02's four remaining modules (used by RSSIE training).
- Tests: 767 passed, 26 skipped (the queue and Postgres suites need the stack);
  ruff and mypy clean; contract consistent; typecheck and build clean;
  `make webtest` 3 passed; Playwright smoke 2 passed. classifier: lexical (best
  available). postgres: SQLite only — no migration was touched.
- Verified in the running app: per change, recorded in each commit — the
  model card, Analyze vs Investigate parity (93.0 and 91.0 on both), the
  Investigate page's caption, the JSON log trail for one case id, the error
  envelope, `/api/health`'s prompt versions.
- How to verify: `make gates`, `make webtest`, `make e2e`; read each 🧪
  task's Evidence line in `docs/TASKS.md`.

## T-07 — Re-verify the infrastructure path with the stack up — 2026-10-22 (🧪)

- What changed: no code. Results appended to `docs/AUDIT.md` §1.
- Ran: `colima start && make up` (all four stores healthy);
  `AEGIS_REQUIRE_SERVING_BEST=1 make gates` — 793 passed, 0 skipped, queue
  and PostgreSQL lines both "answered"; `make migrate` on a fresh Postgres
  database (0001 → 0003); an API and a Celery worker on that database; a
  worker-executed investigation whose pool process was SIGKILLed 8 s into a
  15 s harness delay — requeued, completed, persisted, one timeline; image
  analysis on a real PNG (91 CRITICAL); audio on a real WAV (degraded,
  `asr:unavailable`).
- Found, not fixed (verification only, per the task's scope): **B-13** the
  passport loses its conclusive checks when a citation lookup fails — on the
  worker the digital-arrest text scored 31.3 instead of ~95; **B-14** the
  worker never warms agents and dense retrieval fails after fork on macOS;
  **B-15** unreadable input reports 0 / CALM beside INSUFFICIENT; **D-17**
  no declared speech-to-text dependency. Tasks T-72 to T-75.
- Harness, stated: the 15 s delay came from a throwaway Celery module in a
  temp directory, never committed. The verification database was dropped.
- How to verify: the commands above; the table in `docs/AUDIT.md` §1.
