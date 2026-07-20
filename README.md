# PRESAGE

[![CI](https://github.com/dkadchha2845/presage/actions/workflows/ci.yml/badge.svg)](https://github.com/dkadchha2845/presage/actions/workflows/ci.yml)

**Real-time scam-call defence for Hinglish calls.** It names the manipulation
stage in progress, forecasts how long until money moves, and then does
something about it — coaching the person on the line, alerting a trusted
contact, and holding the payment.

> Not a substitute for reporting fraud on **1930** or at **cybercrime.gov.in**.

---

## Table of contents

- [The problem](#the-problem)
- [How it works](#how-it-works)
- [Architecture](#architecture)
- [Quick start](#quick-start)
- [Verify your setup](#verify-your-setup)
- [What each screen does](#what-each-screen-does)
- [API reference](#api-reference)
- [Project layout](#project-layout)
- [Design decisions worth knowing](#design-decisions-worth-knowing)
- [Training](#training)
- [Tests](#tests)
- [Working together on this repo](#working-together-on-this-repo)
- [Troubleshooting](#troubleshooting)
- [Not in this build](#not-in-this-build)

---

## The problem

A "digital arrest" scam call is not a single lie you can catch with a keyword.
It's a **seven-step arc** run by a practised operator over 20–90 minutes, and
each step exists to set up the next:

| # | Stage | What the caller is doing |
|---|---|---|
| 1 | `GREETING` | Establishing a normal, calm frame |
| 2 | `AUTHORITY_CLAIM` | "I'm Inspector Sharma, CBI, badge 4471" |
| 3 | `FEAR_INDUCTION` | "A parcel in your name contained narcotics. Non-bailable." |
| 4 | `ISOLATION` | "Do not disconnect. Do not tell your family. This is confidential." |
| 5 | `VERIFICATION_DEMAND` | "Confirm your Aadhaar, your account balance, the OTP" |
| 6 | `PAYMENT_SETUP` | "Transfer to this supervised account. It's fully refundable." |
| 7 | `PAYMENT_EXECUTION` | The money moves |

Plus `BENIGN` — a real bank calling about a real transaction, using **the same
vocabulary**. That eighth class is the hard one, and it is the broadest class
in the taxonomy on purpose (see [false positives](#design-decisions-worth-knowing)).

By the time a human notices something is wrong, they are usually at step 5 or
6 — well past the point where the fear is doing the work. **The value of naming
the stage is that it buys back the minutes between step 3 and step 7.**

---

## How it works

One utterance arrives (typed, or from ASR). Here is the whole path:

```
utterance
    │
    ├─► classifier.py ──── 8-way stage distribution (never a bare argmax)
    │                      MuRIL checkpoint, or lexical fallback
    │
    ├─► coercion.py ────── victim stress, read from the VICTIM's side only
    │                      (independent of the classifier — see below)
    │
    ├─► passport.py ────── mechanical identity checks vs. what institutions
    │                      actually do. PASS / FAIL / UNKNOWN + citation
    │
    └─► threat.py ──────── fuse() weights the four signals into one score
                             0.40  stage now
                             0.25  cumulative manipulation pressure
                             0.20  coercion index
                             0.15  failed trust checks
                           …and returns the DRIVERS that produced it.
                           Score ratchets: rises fast, decays slowly.
                             │
                             ▼
                    twin.py ── fitted transition matrix + dwell times
                               ⇒ "≈4m20s until PAYMENT_EXECUTION"
                             │
                             ▼
                    session.py ── emits a complete StateFrame snapshot,
                                  plus discrete Events at the edges
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
        threat ≥ 70     threat ≥ 55    coach line pulled verbatim
        alert guardian  hold payment   from coach_library.json
```

Three thresholds carry the product, and all three are in `engine/session.py`
where you can read them in one screen:

- **`GUARDIAN_THRESHOLD = 70`** — bottom of HIGH. Alerting inside ELEVATED
  trains people to ignore the alert; waiting for CRITICAL alerts after the
  money has gone.
- **`PAYMENT_HOLD_THRESHOLD = 55`** — the hold is reversible and short. The
  transfer is not.
- **Contract version 1** — asserted on both sides, see below.

---

## Architecture

```
┌─ apps/web ──────────┐   WebSocket + REST   ┌─ services/api ──────────────┐
│ React · GSAP · three│◄────────────────────►│ FastAPI                     │
│ home · dashboard    │                      │ engine/  classifier, threat,│
│ console · analyzer  │                      │          twin, coercion,    │
│ guardian · knowledge│                      │          passport, upi      │
└─────────────────────┘                      │ rag/     BM25 / dense + KB  │
          ▲                                  └─────────────────────────────┘
          │ contract                                    ▲
   schema/types.ts ◄──── check_contract.py ────► schema/models.py
                                                        │
                                       ml/  corpus → train.py → artifacts/
```

`schema/` is the single source of truth. `check_contract.py` fails the build if
the Python enums and the TypeScript unions drift apart — that check is why the
frontend can treat every number it renders as a given rather than something to
recompute.

---

## Quick start

**Prerequisites:** Python 3.9+, Node 18+. Nothing else. No GPU, no API key, no
network at runtime.

```bash
git clone https://github.com/dkadchha2845/presage.git
cd presage
```

Two processes. **Neither needs the other to start** — the web app renders from
a mock stream if the API is down, and the API answers without the web app.

### 1. API — port 8000

```bash
python3 -m venv .venv
.venv/bin/pip install -r services/api/requirements.txt
.venv/bin/uvicorn services.api.main:app --reload --port 8000
```

### 2. Web — port 5173

```bash
npm install --prefix apps/web
npm run dev --prefix apps/web        # http://localhost:5173
```

### 3. Environment (optional)

```bash
cp .env.example .env
```

**You do not need to fill this in to run the project.** Every key in `.env` is
for *offline corpus generation* (`ml/`), not for the running app. The API's
request path makes zero network calls by design — conference wifi that may not
resolve DNS is an assumption, not an edge case.

---

## Verify your setup

Run these four. All four should pass on a clean clone:

```bash
.venv/bin/python -m pytest services/api/tests -q   # → 16 passed
.venv/bin/python schema/check_contract.py          # → contract consistent
npm run typecheck --prefix apps/web                # → no output = clean
curl -s localhost:8000/api/health                  # → see below
```

> ⚠️ Use `.venv/bin/python schema/check_contract.py`, **not** bare `python3` —
> the contract check imports pydantic, which only exists inside the venv.

`GET /api/health` reports exactly which components are live and which are
degraded, and the web app shows the same thing in its top bar on every screen.
On a fresh clone you should see:

```jsonc
{
  "ok": true,
  "contract_version": 1,
  "classifier": { "backend": "lexical", "loaded": false,
                  "reason": "no checkpoint exported" },
  "retrieval":  { "backend": "bm25", "chunks": 26 },
  "twin":       { "fitted": true, "stages": [ /* 8 */ ] },
  "coach":      { "lines": 14 },
  "llm":        { "backend": "none", "configured": false },
  "degraded":   ["rag:lexical", "clf:lexical_fallback"]
}
```

**`degraded` being non-empty on a fresh clone is correct, not broken.** Those
two tags are the honest state of a default install: the lexical classifier is
serving (and currently outperforms the checkpoint — see
[Training](#training)), and retrieval is BM25 rather than dense. Both are
optional upgrades, and both are reported rather than hidden.

---

## What each screen does

| Route | Purpose |
|---|---|
| `/` | The argument: the seven-step arc every one of these calls follows |
| `/dashboard` | System state, honest degradation reporting, links to everything |
| `/console` | Live call — transcript, threat meter, twin forecast, narration, coach |
| `/guardian` | Intervention — alert acknowledgement and the payment circuit breaker |
| `/analyzer` | Paste or upload an SMS, transcript, UPI ID or QR payload → scored verdict |
| `/knowledge` | The cited advisory corpus behind every verdict |
| `/model` | Model card, served live so it cannot drift from what is loaded |

`⌘K` jumps between them.

**To see it work in 30 seconds:** open `/console`, click Start, and type caller
lines into the box — try `"main CBI se inspector bol raha hoon"`, then
`"aapke naam par parcel mein drugs mila hai, non-bailable case hai"`, then
`"kisi ko mat bataiye, call disconnect mat kijiye"`. Watch the meter ratchet
and the twin forecast appear.

---

## API reference

Interactive docs at **http://localhost:8000/docs** once the API is running.

### Analysis (stateless)

| Method | Path | Body / params |
|---|---|---|
| `POST` | `/api/analyze/text` | `{ text, claimed_org?, explain? }` |
| `POST` | `/api/analyze/upi` | `{ vpa \| qr_payload, amount? }` |
| `POST` | `/api/analyze/file` | multipart upload, ≤4 MB, `.txt/.json/.csv` |
| `GET` | `/api/knowledge/search` | `?q=…&k=5` |
| `GET` | `/api/knowledge/docs` | — |

### Live session (stateful)

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/session` | Start a call |
| `GET` | `/api/session` | List active sessions |
| `GET` | `/api/session/{id}` | Current `StateFrame` |
| `POST` | `/api/session/{id}/utterance` | Inject an utterance |
| `POST` | `/api/session/{id}/guardian/ack` | Guardian acknowledges the alert |
| `POST` | `/api/session/{id}/payment/attempt` | Attempt a payment (may be held) |
| `POST` | `/api/session/{id}/payment/cancel` | Cancel a held payment |
| `POST` | `/api/session/{id}/payment/approve` | Override the hold |
| `DELETE` | `/api/session/{id}` | End the call |
| `WS` | `/api/session/ws/{id}` | `StateFrame` snapshots @ 4 Hz + `Event` edges |

### Meta

| Method | Path |
|---|---|
| `GET` | `/api/health` |

---

## Project layout

```
presage/
├── apps/web/                    React + Vite frontend (pure renderer)
│   └── src/
│       ├── pages/               one file per route
│       ├── components/          ThreatMeter, TranscriptPane, ForecastChip…
│       │   ├── layout/          AppShell, CommandPalette, RouteBoundary
│       │   └── three/           ThreatField — the WebGL backdrop
│       ├── hooks/               useLiveSession (WS), useHealth, useStreamPlayer
│       ├── types/contract.ts    ← generated-adjacent; mirrors schema/types.ts
│       └── mock/stream.json     lets the UI run with the API down
│
├── services/api/                FastAPI backend
│   ├── main.py                  app + /api/health + startup warm
│   ├── config.py                every optional capability, one dataclass
│   ├── routes/                  analyze.py, session.py
│   ├── engine/                  ← all the logic lives here
│   │   ├── classifier.py        MuRIL + lexical fallback + promotion gate
│   │   ├── threat.py            fuse() — the meter, with drivers
│   │   ├── twin.py              transition matrix ⇒ time-to-payment
│   │   ├── coercion.py          victim-side stress, independent signal
│   │   ├── passport.py          identity checks, PASS/FAIL/UNKNOWN
│   │   ├── upi.py               VPA / QR structural checks
│   │   ├── analyzer.py          the stateless "is this a scam?" path
│   │   └── session.py           state machine → StateFrame + Event
│   ├── rag/                     store.py (BM25/dense), coach.py
│   ├── knowledge/               RBI advisories, playbooks, coach_library.json
│   └── tests/test_verdicts.py   16 regression cases
│
├── schema/                      THE CONTRACT — edit here first, always
│   ├── models.py                Pydantic (Python side)
│   ├── types.ts                 TypeScript unions (web side)
│   ├── check_contract.py        fails if the two drift
│   └── mock-stream.json         24 frames + 24 events
│
├── ml/                          offline corpus + training (see ml/README.md)
│   ├── presage/                 taxonomy, seeds, entities, Hinglish helpers
│   ├── generate_calls.py        LLM → raw calls          ─┐
│   ├── paraphrase.py            diversity pass            │ offline,
│   ├── build_dataset.py         splits + transitions.json │ one-time
│   ├── train.py                 fine-tunes MuRIL          │
│   ├── eval_backends.py         muril vs. lexical        ─┘
│   └── data/                    the corpus (committed)
│
└── scripts/                     ollama-up.sh, sync-contract.sh
```

### What is *not* in the repo

- **`ml/artifacts/stage-classifier/` weights** — ~950 MB of `pytorch_model.bin`
  plus ~2.6 GB of optimiser state. Regenerate with `ml/train.py`; the corpus
  that produces it *is* committed, so nothing is lost. Without it the API
  reports `"no checkpoint exported"` and serves lexical, which is the better
  backend today anyway.
- **`.env`** — copy `.env.example`. Not needed to run.
- **`.venv/`, `node_modules/`** — the usual.

`ml/artifacts/backend_comparison.json` **is** committed, because it is
load-bearing: it is the file that gates checkpoint promotion.

---

## Design decisions worth knowing

**State snapshot vs discrete event.** `StateFrame` is a complete, idempotent
picture of the call — a client that missed ten frames is fully correct after
the next one, which is what makes the demo survive a dropped socket on stage.
`Event` is a one-shot edge, because animations need edges, not levels.
Deriving "did it just cross 70?" by diffing snapshots breaks the moment a
frame drops, repeats, or arrives out of order.

**The frontend is a pure renderer.** No threat maths, no thresholds, no stage
rules in React. Every number the UI shows is a contract field. That includes
the plain-language narration — two implementations of "what's happening" drift
apart exactly like two implementations of the scoring would, except the
disagreement is in prose and nobody notices until someone reads the panel and
the meter in the same glance.

**Every score carries its provenance.** `ThreatState.drivers` and
`TrustPassport.checks` exist so the UI can always answer "why?". A meter
reading 91 with no explanation is a demo; 91 *because* of three named signals
with citations is a product.

**The coercion index is independent of the classifier.** It reads the
*victim's* side — timing, rate, hesitation, compliance language — while the
stage classifier reads the *caller's*. If it were derived from the stage
labels it would be a restatement of the classifier wearing a different hat,
and fusing the two would be double-counting. The ablation is only meaningful
because the two signals can disagree.

**`UNKNOWN` is a real answer.** A Trust Passport check that hasn't had the
evidence to run is not a pass and not a fail. The trust percentage is computed
over *resolved* checks only, so one FAIL out of one resolved check reads 0%
rather than being diluted by six checks that never ran.

**The coach never improvises.** Lines a frightened person is told to say come
from `knowledge/coach_library.json`, are human-reviewed, and are delivered
verbatim. An LLM may rank or reword the *explanation*; it never writes the
line and it never touches a score.

**Degradation is explicit.** Every path has a fallback that still answers —
lexical classifier, BM25 retrieval, prior-only twin, templated explanations —
and each one records a tag in `degraded` rather than quietly returning a worse
answer. A confident number built on nothing is worse than an honest gap.

**False positives are a first-class failure.** Crying wolf on a genuine bank
call is how someone learns to dismiss the alert, and a system people dismiss
protects nobody. The corpus is 40% legitimate calls using the same vocabulary,
BENIGN is the broadest class in the taxonomy, and the regression suite tests
both directions.

---

## Training

```bash
.venv/bin/pip install torch transformers scikit-learn accelerate 'numpy<2'
.venv/bin/python ml/train.py           # exports to ml/artifacts/stage-classifier
.venv/bin/python ml/eval_backends.py   # scores it against the lexical baseline
```

`ml/notebooks/train_stage_classifier.ipynb` is the same pipeline with the
confusion matrix and commentary — read that one, run the script.

### The checkpoint is trained but not promoted

Run those two commands today and you get this:

| backend | val macro-F1 | **test macro-F1** (held-out archetypes) |
|---|---:|---:|
| lexical baseline | — | **0.368** |
| fine-tuned MuRIL | 0.983 | **0.221** |

The model converges beautifully and then loses to a pile of regexes on call
archetypes it has never seen. The 0.98 is memorisation: 320 synthetic calls
from a seeded diversity grid give an 8-way classifier enough surface detail to
recognise the archetype rather than the stage, and the leave-archetypes-out
split is what exposes it. Anything less strict would have reported ~0.9 and
been wrong.

So `load_classifier()` gates promotion on `backend_comparison.json` rather
than on the checkpoint existing, and `/api/health` reports which backend won
and why. Loading a model because its files are on disk is how a system quietly
gets worse after a "successful" training run.

To override once the corpus is bigger: `PRESAGE_CLASSIFIER=muril`.

The fix is more data, not more epochs — more calls, more varied archetypes,
and specifically more `ISOLATION` and `VERIFICATION_DEMAND` (37 and 6
caller-side training examples respectively).

Two things must stay in lockstep or the served model silently underperforms:
the speaker-tagged `previous [SEP] current` context join
(`ml/train.py::render` and `MuRILStageClassifier.predict`), and the label
ordering, which travels inside the checkpoint config and is asserted on export.

> **Do not train on Apple MPS.** On torch 2.2 / transformers 4.44 a full run
> completed every step with the loss pinned at exactly ln(8) — the
> uniform-prior loss — and never left initialisation. CPU is the default for
> that reason.

Regenerating the corpus is separate and offline; see [`ml/README.md`](ml/README.md).

---

## Tests

```bash
.venv/bin/python -m pytest services/api/tests -q   # verdict regressions
.venv/bin/python schema/check_contract.py          # Python/TS contract drift
npm run typecheck --prefix apps/web
```

Every case in the verdict suite is one the engine got wrong at some point —
including the benign ones, which all read CRITICAL until the credential check
learned the difference between asking for an OTP and warning about one.

**If you change anything in `schema/`, run `check_contract.py` before you
commit.** It is the one check that catches a whole class of bug that otherwise
shows up as a blank panel in the UI three days later.

### CI

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs all three on every
push and PR to `main`, so you find out from a red badge rather than from the
other person. It goes slightly further than the local three:

- **Backend on Python 3.9 *and* 3.12** — the two ends of the range this README
  claims. Claiming 3.9+ and only ever running 3.12 is how the floor rots.
- **Boots the API and asserts `/api/health`** — a missing `transitions.json` or
  an empty coach library fails in CI rather than as a blank panel mid-demo.
  The runner has no checkpoint, which makes this an assertion about the
  documented clean-clone path.
- **`vite build`, not just `tsc`** — typecheck passing doesn't mean it bundles;
  the `@/` alias and the `three`/GSAP imports resolve at build time.

Full run is ~1 minute. Pushing twice cancels the older run.

---

## Working together on this repo

Two people, alternating turns. The rules that keep that from hurting:

### Before you start a session

```bash
git pull --rebase origin main
```

`--rebase` keeps the history linear, which matters a lot when two people are
pushing to `main`.

### While you work

1. **Branch for anything non-trivial.**
   ```bash
   git checkout -b smruthi/coercion-audio
   ```
   Small fixes straight on `main` are fine. Anything that touches `schema/` or
   `engine/threat.py` should be a branch and a PR, because those two files are
   where a silent conflict becomes a wrong number rather than a merge marker.

2. **`schema/` is edited in one place, both sides, same commit.** If you add a
   field to `schema/models.py`, add it to `schema/types.ts` in the same commit
   and run `check_contract.py`. A commit that changes one and not the other
   will fail the check for whoever pulls next, and they will think they broke
   it.

3. **Never commit `.env`.** It's gitignored. If you add a new key, add it to
   `.env.example` (with an empty value) so the other person knows it exists.

4. **Don't commit `ml/artifacts/` weights.** Also gitignored. If you retrain
   and get a better model, commit the updated
   `ml/artifacts/backend_comparison.json` and `metrics.json` and tell the other
   person to retrain locally.

### Before you push

```bash
.venv/bin/python -m pytest services/api/tests -q
.venv/bin/python schema/check_contract.py
npm run typecheck --prefix apps/web
git push origin main          # or: git push -u origin your-branch
```

### Handing over

At the end of your turn, push and say what you changed and what you were
in the middle of. [`STATUS.md`](STATUS.md) is the running record of what's done
and what's left — **update it when you finish something**, so the person
picking up next doesn't have to reverse-engineer the state from the diff.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'pydantic'` running `check_contract.py` | Used system `python3` | Use `.venv/bin/python schema/check_contract.py` |
| `ModuleNotFoundError: No module named 'services'` | Ran uvicorn from a subdirectory | Run from the repo root |
| Web loads but the top bar says API offline | API not running, or CORS | Start the API on **8000** — `cors_origins` in `config.py` allows 5173 only |
| `degraded: ["rag:lexical", "clf:lexical_fallback"]` | Nothing. This is the correct default. | Optional: install the extras in `services/api/requirements.txt` |
| `Address already in use` on 8000 | An older uvicorn is still up | `lsof -ti:8000 \| xargs kill` |
| Training loss stuck at exactly 2.079 (`ln 8`) | Apple MPS backend | Train on CPU — it's the default for this reason |
| `npm run dev` — Vite can't resolve `@/…` | Ran npm from the repo root | Use `--prefix apps/web`, or `cd apps/web` first |

---

## Not in this build

- **No OCR.** Screenshots must be typed out; returning a confident verdict on
  an empty string would be worse than declining.
- **No live audio.** The coercion index runs text-only and is capped lower to
  say so.
- **Synthetic training data only.** Real-world transfer is unmeasured.
- **No persistence.** Sessions live in memory and die with the process.
- **Not a substitute for reporting fraud on 1930 or at cybercrime.gov.in.**

See [`STATUS.md`](STATUS.md) for the full done/pending breakdown.
