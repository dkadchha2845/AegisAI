# ml/ — corpus, training, evaluation

Split by lifecycle stage so it is obvious which step a file belongs to:

| Directory | What it does | Entry points |
|---|---|---|
| `corpus/` | Generate, augment, validate and split the training corpus | `generate_calls.py` -> `paraphrase.py` -> `build_dataset.py`, `validate_corpus.py`, `synth_seeds.py` |
| `training/` | Fine-tuning | `train.py` (served stage classifier), `rssie/` (multi-head research model) |
| `evaluation/` | Measurement and the promotion gate | `eval_backends.py` |
| `data/` | Corpus: `seed/` -> `raw/` -> `processed/` | committed |
| `artifacts/` | Checkpoints + `backend_comparison.json` | mostly gitignored |
| `notebooks/` | Colab training notebook | |

The shared domain vocabulary (taxonomy, victim-state schema, entity
substitution, Hinglish) is **not** here — it moved to `packages/aegis_core`,
because the API imports it too. Import it as `aegis_core.taxonomy`.

Scripts derive their paths from a named `ML_DIR` anchor rather than
`Path(__file__).parent`, so they run correctly from any working directory and
survive being moved again.

---

# AegisAI — dataset pipeline

Builds the synthetic corpus that trains the stage classifier and fits the
Digital Twin. Runs **once, offline, before the hackathon**. Nothing here runs
or bills during the event.

## Setup — costs nothing

```bash
cd ml
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

Then pick a backend. **Gemini is the default and the recommendation** — better
Hinglish than any 7B model that fits on a laptop, and the free tier covers the
whole corpus several times over.

```bash
# Option A — Gemini free tier (recommended). Google account, no card.
#   key from https://aistudio.google.com/apikey
export AEGIS_LLM=gemini
export GEMINI_API_KEY=...

# Option B — fully offline, no signup, no quota, unlimited
brew install ollama && ollama serve &
ollama pull qwen2.5:7b-instruct
export AEGIS_LLM=ollama
```

## Run

```bash
.venv/bin/python generate_calls.py --check       # verify backend reachable
.venv/bin/python generate_calls.py --dry-run     # inspect prompts, no calls
.venv/bin/python generate_calls.py --limit 5     # smoke test
.venv/bin/python generate_calls.py               # full corpus, ~330 calls
.venv/bin/python build_dataset.py                # splits + transitions + report
```

`generate_calls.py` is resumable — it appends as it goes and skips any
`call_id` already in `data/raw/calls.jsonl`. Free tiers have daily quotas, so
expect to run this across more than one sitting: hit the wall, stop, re-run
tomorrow, it picks up exactly where it left off.

Switching backend mid-corpus is fine and even useful — generate what Gemini's
quota allows, then top up with Ollama. Each call records which backend produced
it, so you can audit quality per source afterwards.

## What comes out

| File | Used by |
|---|---|
| `data/raw/calls.jsonl` | source of truth; one full labelled call per line |
| `data/processed/{train,val,test}.jsonl` | MuRIL stage classifier |
| `data/processed/transitions.json` | Digital Twin forecast + ETA |
| `data/processed/report.md` | class balance, corpus stats, deck numbers |

## Three decisions worth knowing

**Every generation is validated client-side.** Backends differ in how (and
whether) they enforce a schema, so `aegis/llm.py` parses and validates every
response itself: enum casing is normalised, markdown fences and prose wrappers
are recovered from, but an invalid stage label, an empty utterance, or a
one-sided transcript is rejected outright. A dropped generation costs one retry;
a mislabelled one costs accuracy you can never explain to a judge.


**Splits are by call, never by utterance.** Utterances within one call share
names, case IDs, and phrasing tics, so an utterance-level split leaks test into
train and inflates macro-F1 substantially. If a judge asks how you split, this
is the answer that holds up.

**The transition matrix is fitted on collapsed stage runs.** A scammer spends
several turns inside one stage, so a raw turn-to-turn matrix is ~85%
self-transitions and the forecast would read "NEXT: ISOLATION" while already in
ISOLATION. Collapsing makes it answer what comes *after* the current stage;
`dwell_turns` supplies the "how long until then" half of the ETA.

## Files

- `aegis/taxonomy.py` — the 8 stages, their linguistic markers, threat weights
- `aegis/seeds.py` — the diversity grid (archetype × victim × style × language × outcome)
- `aegis/schema.py` — server-enforced JSON output schema
- `generate_calls.py` — async generator, resumable, cost-reporting
- `build_dataset.py` — splits, de-duplication, twin fitting, corpus report
