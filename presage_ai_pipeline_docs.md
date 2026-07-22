# PRESAGE: Complete AI, ML, and RAG Pipeline Reverse Engineering

This document contains a complete trace of every AI, ML, and rule-based heuristic component in the Presage repository. It maps the training pipelines, the artifact generation, the real-time inference loop, the retrieval augmented generation (RAG) system, and provides a deep code walkthrough.

---

## PART 1 — Identify Every AI Component

| Component | Type | Purpose | Used During Training | Used During Runtime | Entry File |
|-----------|------|---------|----------------------|---------------------|------------|
| **MuRIL Stage Classifier** | PyTorch / HuggingFace Model | Predicts the 8-way scam stage of a caller's utterance. | Yes (Fine-tuned) | Yes | `engine/classifier.py` |
| **Lexical Stage Classifier** | Rule-based (Regex/Softmax) | Fallback classifier when MuRIL is unavailable or unpromoted. | No | Yes (Fallback) | `engine/classifier.py` |
| **Digital Twin** | Markov Chain / Statistical | Predicts the next stage and time to payment execution. | Yes (Fitted) | Yes | `engine/twin.py` |
| **Threat Fusion Engine** | Mathematical Heuristic | Fuses 4 independent signals into a 0-100 threat score. | No | Yes | `engine/threat.py` |
| **Manipulation Engine** | Rule-based Accumulator | Tracks cumulative tactic pressure (fear, isolation, etc.). | No | Yes | `engine/threat.py` |
| **Trust Passport** | Rule-based (Regex) | Validates caller claims against institutional reality. | No | Yes | `engine/passport.py` |
| **Coercion Detector** | Lexical & Prosodic Heuristic | Measures victim stress (0-100) via compliance/resistance cues. | No | Yes | `engine/coercion.py` |
| **Dense Retriever** | `sentence-transformers` Index | Computes cosine similarity over embeddings for citations. | No | Yes | `rag/store.py` |
| **BM25 Retriever** | Statistical TF-IDF Index | Fallback retrieval when Dense index cannot load. | No | Yes (Fallback) | `rag/store.py` |
| **Coach** | RAG / Rule-based | Recommends verbatim anti-fraud lines for the victim to say. | No | Yes | `rag/coach.py` |
| **Knowledge Base** | RAG Document Store | Parses markdown advisories into chunks for the retrievers. | No | Yes | `rag/store.py` |
| **Narration Generator** | Rule-based Templating | Translates the fusion state into human-readable text. | No | Yes | `engine/session.py` |

---

## PART 2 — Training Pipeline

The ML pipeline is entirely self-contained inside the `ml/` directory.

### Trainable Models
1. **MuRIL Stage Classifier** (`ml/train.py`)
2. **Digital Twin Transition Matrix** (`ml/build_dataset.py`)

### Dataset Generation (`ml/generate_calls.py` -> `ml/paraphrase.py`)
1. **Generation:** `generate_calls.py` queries an LLM (Gemini/Ollama/Anthropic) using a highly constrained prompt to generate synthetic Hinglish scam and benign calls based on seeds.
2. **Paraphrasing:** `paraphrase.py` takes hand-labelled "gold" seeds and uses deterministic entity substitution (names, cities, amounts), followed by local-LLM rewording (enforcing exact line counts and language constraints) to multiply the data.

### Preprocessing & Splitting (`ml/build_dataset.py`)
* **Transformations:** Texts are kept exactly as-is (digits are explicitly kept because numbers differentiate "pin daaliye" from "refund of 400").
* **Splitting Strategy:** Splits are created **by call skeleton (archetype), not by utterance**. Splitting utterances from the same call would leak data. 
* **Leave-Archetypes-Out:** The test set consists entirely of scam types the model has never trained on, ensuring it learns to detect coercion rather than memorizing scripts.

### Model Fine-Tuning (`ml/train.py`)
* **Features:** A string in the format `previous_speaker: previous_text [SEP] current_speaker: current_text`.
* **Labels:** One of the 8 stages: `GREETING`, `AUTHORITY_CLAIM`, `FEAR_INDUCTION`, `ISOLATION`, `VERIFICATION_DEMAND`, `PAYMENT_SETUP`, `PAYMENT_EXECUTION`, `BENIGN`.
* **Tokenizer & Pretrained Model:** `google/muril-base-cased` loaded via HuggingFace `AutoTokenizer` and `AutoModelForSequenceClassification`.
* **Loss Function:** `CrossEntropyLoss` with inverse-frequency class weights (rare classes are weighted higher so the model doesn't ignore `PAYMENT_EXECUTION`).
* **Optimizer:** AdamW (standard HuggingFace Trainer default), plus a manual `LBFGS` optimizer at the end to fit a temperature scalar for calibration.
* **Metrics:** Macro-F1 score is used to pick the best model (not loss).
* **Saved Checkpoint:** The highest Macro-F1 model is exported using `.save_pretrained(safe_serialization=False)` (due to MuRIL non-contiguous tensor bugs).

### The Digital Twin Fitting (`ml/build_dataset.py :: fit_transitions`)
The Twin is fitted on the training split only. It calculates:
1. `matrix`: A first-order Markov transition matrix based on **collapsed** stage runs (ignoring self-transitions) with Laplace smoothing.
2. `dwell_turns`: Median utterances spent in each stage.
3. `eta_to_payment`: Median turns from a given stage to `PAYMENT_EXECUTION`.

---

## PART 3 — Artifact Storage

```text
ml/
 ├── artifacts/
 │   ├── stage-classifier/            # Generated by ml/train.py
 │   │   ├── config.json              # Model config + id2label mapping
 │   │   ├── metrics.json             # F1 scores, false alarms, temperature
 │   │   ├── pytorch_model.bin        # The weights (unsafe serialization)
 │   │   ├── tokenizer.json           # MuRIL tokenizer
 │   │   └── ...
 │   ├── backend_comparison.json      # Generated by ml/eval_backends.py
 │
 ├── data/
 │   ├── processed/
 │   │   ├── train.jsonl / val.jsonl / test.jsonl 
 │   │   └── transitions.json         # Generated by build_dataset.py
```

* **`pytorch_model.bin`**: Loaded by `engine/classifier.py`. If missing, the app falls back to `LexicalStageClassifier`.
* **`backend_comparison.json`**: Evaluates Lexical vs MuRIL on held-out test data. If MuRIL's macro-F1 is lower than Lexical's, the backend explicitly refuses to promote MuRIL, even if the file exists on disk.
* **`transitions.json`**: Loaded by `engine/twin.py`. If missing, the Digital Twin uses a uniform prior based on a canonical stage order.

---

## PART 4 — Runtime Loading

The execution trace for loading models at startup:

1. **`main.py` starts:** Uvicorn spins up the FastAPI app.
2. **`warm()` hook fires:** `@app.on_event("startup")` executes before the first request.
3. **`load_classifier()`:**
   * Checks if `ml/artifacts/stage-classifier/config.json` exists.
   * Calls `_checkpoint_is_better()` which reads `backend_comparison.json`.
   * If MuRIL is better, it imports `torch` and loads `MuRILStageClassifier(model_dir)` eagerly into memory.
   * Caches the instance in a global `_cached` singleton to prevent blocking future requests.
   * Device Selection: `"cuda" if torch.cuda.is_available() else "cpu"`.
   * **Fallback:** If torch is missing, or the model fails to load, or Lexical scored better, it loads `LexicalStageClassifier`.
4. **`get_kb()` & `get_coach()`:** Loads the Markdown files and `coach_library.json`. Initializes the `DenseIndex` (sentence-transformers), falling back to `BM25Index` if torch or the model download fails.

---

## PART 5 — Runtime Inference

Trace of an utterance: `"I am Inspector Sharma from CBI."`

1. **Text arrives** at `Session.ingest("I am Inspector Sharma from CBI.", speaker="CALLER")`.
2. **Classifier Context:** `history` (e.g. `["Haan ji?"]`) is retrieved. Joined string: `VICTIM: Haan ji? [SEP] CALLER: I am Inspector Sharma from CBI.`
3. **Tokenizer:** Converts the string to Input IDs and Attention Masks padded to `max_length=128`.
4. **MuRIL Inference:** `self.model(**enc)` generates logits.
5. **Softmax:** `torch.softmax(logits, dim=-1)` converts logits to a probability distribution (e.g., `{"AUTHORITY_CLAIM": 0.92, ...}`).
6. **Object Creation:** Extracts the `label` with `max()` probability. Returns a `StagePrediction` object.
7. **Downstream:** 
   * `DigitalTwin` uses the label to check if its last forecast was correct.
   * `ManipulationAccumulator` increments the `authority` bar by `0.34 * 0.92`.
   * `TrustPassport` matches `"CBI"` and flags `"Claimed identity"`.
8. **Threat Fusion:** `fuse()` combines all this into a final Threat Score.

---

## PART 6 — RAG Pipeline

**1. Where documents come from:** `services/api/knowledge/*.md` (RBI advisories, playbooks).
**2. How they are chunked:** `rag/store.py` splits markdown files exclusively on `##` headings. Fixed-token chunking is avoided to prevent splitting semantic rules mid-sentence.
**3. How they are indexed:** 
   * **DenseIndex:** Uses `sentence-transformers` (`all-MiniLM-L6-v2`). Generates embeddings at server startup and stores them in an in-memory numpy `matrix`.
   * **BM25Index:** Standard Okapi BM25 TF-IDF algorithm, built purely in Python (no dependencies).
**4. Retrieval:** `search(query, tags)` computes cosine similarity (`sims = self.matrix @ q`) or BM25 scores. Tags act as a hard boolean gate, not a boost (e.g., you can't show an `ISOLATION` tip during `GREETING`).
**5. Coach Usage:** `rag/coach.py` picks a verified anti-fraud line from `coach_library.json` based on the current stage and victim state. It then queries the Knowledge Base (`get_kb().search(tactic + " " + why)`) to append real PDF citations to the coaching line.

---

## PART 7 — Rule-based AI

### 1. Trust Passport (`engine/passport.py`)
* **Inputs:** Raw text.
* **Algorithm:** Regex matching. Evaluates explicit mechanical rules:
  * Claiming to be police (`IDENTITY_PATTERNS`).
  * Asking for a credential (`_is_credential_request` ensures it's an ask, not a warning like "we never ask for OTP").
  * Demanding secrecy, callbacks, or individual payments.
* **Outputs:** Latched states of `PASS`, `FAIL`, or `UNKNOWN`. `final_trust_pct` = `(passed / resolved) * 100`.

### 2. Coercion Index (`engine/coercion.py`)
* **Inputs:** Victim text, duration, word count.
* **Algorithm:** 
  * Lexical: Counts hits for Compliance, Resistance, Distress regexes.
  * Math: `lexical = 22 * compliance + 26 * distress - 30 * resistance`. 
  * Prosodic: Measures `wpm` (variance from 140wpm normal).
  * Fusion: `index = 0.6 * lexical + 0.4 * prosodic`. Smooths via `0.65 * index + 0.35 * prev_index`.
* **Outputs:** `CoercionOut` (0-100 index, trend, victim_state: CALM/RESISTING/PANICKED).

### 3. Threat Fusion (`engine/threat.py`)
* **Inputs:** Stage, Stage Confidence, Manipulation Accumulator, Coercion Index, Trust Pct, Previous Score.
* **Algorithm:** 
  * Base = `0.40 * stage_weight + 0.25 * manipulation_pressure + 0.20 * coercion + 0.15 * (100 - trust)`.
  * Ratchet: `score = max(base, previous_score - (DECAY_PER_S * dt_s))`. (Score rises fast, decays slowly).
* **Outputs:** `FusionResult` (Score 0-100, Threat Level, Drivers).

### 4. Digital Twin (`engine/twin.py`)
* **Inputs:** Current stage, time spent in stage.
* **Algorithm:** Uses a 1st order Markov matrix (`transitions.json`) to find `max(P(next_stage | current_stage))`. 
  * `eta_s = max(3.0, median_dwell - time_spent)`. 
  * `eta_to_payment = max(0.0, median_turns_to_pay * 12.0s - time_spent)`.
* **Outputs:** `ForecastOut` (Next Stage, Probability, ETA).

---

## PART 8 — Cross Module Flow

Trace of a single utterance:

1. **`Session.ingest(text, speaker)`** in `engine/session.py`.
2. **Stage Classifier** (`classifier.predict()`): Output `StagePrediction`.
3. **Digital Twin** (`twin.score_transition()`): Verifies if its past prediction was right based on the new stage.
4. **Manipulation Engine** (`manip.observe()`): Accumulates fear/authority bars based on classifier confidence.
5. **Trust Passport** (`passport.observe()`): Looks for rule-breaks (e.g., asks for OTP).
6. **Coercion Engine** (`coercion.observe()`): (If victim spoke) Calculates victim stress level.
7. **Threat Fusion** (`Session._recompute()` -> `fuse()`): Computes the 0-100 score. Mutates `guardian_state` to `ALERTING` if threshold crossed.
8. **Digital Twin** (`twin.forecast()`): Predicts what will happen next.
9. **Coach** (`coach.suggest()`): Fetches the next thing the victim should say out loud.
10. **Knowledge Base / Narration** (`_update_narration()`): Generates "Threat is 85. Biggest contributor...".
11. **StateFrame** (`Session.frame()`): Wraps all variables into a JSON-serializable snapshot.
12. **Frontend**: React receives the frame over WebSocket and updates the UI blindly.

---

## PART 9 — Repository Map

```mermaid
graph TD
    subgraph "Training Pipeline (ml/)"
        A[generate_calls.py (LLM)] --> B[paraphrase.py (Local LLM)]
        B --> C[build_dataset.py]
        C --> D[train.py (MuRIL)]
        C --> E(transitions.json)
        D --> F(stage-classifier checkpoint)
    end

    subgraph "Backend Initialization (services/api/)"
        F --> G[main.py: warm()]
        E --> G
        K[knowledge/*.md] --> G
    end
    
    subgraph "Live Inference Engine (services/api/engine/)"
        G --> H[Session Manager]
        H --> I1[MuRIL Classifier]
        H --> I2[Trust Passport]
        H --> I3[Coercion Tracker]
        I1 --> J[Threat Fusion]
        I2 --> J
        I3 --> J
        I1 --> L[Digital Twin]
    end

    subgraph "RAG (services/api/rag/)"
        H --> M[Coach]
        K --> N[Knowledge Base Store]
        M --> N
    end

    J --> O[StateFrame JSON]
    L --> O
    M --> O
    O --> P((WebSocket / REST))
    P --> Q[React Frontend (apps/web)]
```

---

## PART 10 — Code Walkthrough

### 1. `engine/classifier.py`
**Classes:**
- `StagePrediction`: Dataclass holding label, confidence, full distribution, and backend name.
- `LexicalStageClassifier`: Rule-based fallback.
  * **Variables:** `CUES` dict containing regex patterns mapped to weights. `_COMPILED` caches compiled regexes.
  * **`predict()`:** Evaluates regexes, adds weights. If no hits, returns `BENIGN` at low confidence (so Threat Fusion can scale it appropriately). Uses a custom `_softmax(temp=0.45)` to sharpen the distribution.
- `MuRILStageClassifier`: The fine-tuned model.
  * **Variables:** Loads `AutoTokenizer` and `AutoModelForSequenceClassification` lazily.
  * **`predict()`:** Formats text as `PREV_SPEAKER: msg [SEP] CURR_SPEAKER: msg`. Pushes through model, takes argmax.

**Functions:**
- `_checkpoint_is_better()`: Reads `backend_comparison.json`. Prevents loading a bad checkpoint.
- `load_classifier()`: Implements singleton pattern via `global _cached`. Loads MuRIL or Lexical based on `_checkpoint_is_better()`.

### 2. `engine/twin.py`
**Classes:**
- `DigitalTwin`: Markov-chain forecaster.
  * **Variables:** `transitions`, `dwell_turns`, `turns_to_payment`.
  * **`_load()`:** Parses `transitions.json`. Drops data if support `< MIN_SUPPORT (20)` to prevent noise.
  * **`forecast(stage, since_s)`:** Multiplies median turns by `SECONDS_PER_TURN (12.0)`. Clamps ETA to `max(3.0, eta)`.
  * **`score_transition()`:** Called when stage actually changes to log a hit/miss for metrics.

### 3. `engine/coercion.py`
**Classes:**
- `CoercionTracker`: 
  * **Variables:** Arrays of regexes (`_COMPLIANCE`, `_RESISTANCE`, `_DISTRESS`).
  * **`observe()`:** Calculates lexical score (22*compliance + 26*distress - 30*resistance). Calculates prosodic score based on `wpm`, `pause_ratio`, `pitch_var` distance from norms. Blends 60/40. Smooths with `0.65 * current + 0.35 * previous`. Returns `CoercionOut`.
  * **`_victim_state()`:** Returns categorical state (e.g. `RESISTING`, `COMPLIANT`). Resistance takes priority over panic.

### 4. `engine/passport.py`
**Classes:**
- `TrustPassport`: 
  * **Variables:** `IDENTITY_PATTERNS`.
  * **`observe()`:** Checks text against identities. The most complex logic is `_is_credential_request()`, which looks for an OTP/PIN word, but then looks 45 chars around it for an advisory word (like "never share"). This prevents a legitimate bank warning from triggering a fraud alert.
  * **`_fail()` / `pass_check()`:** Latches a check. A failed check cannot be unfailed.
  * **`snapshot()`:** Computes `final_trust_pct` dynamically based *only* on resolved checks.

### 5. `engine/threat.py`
**Classes:**
- `ManipulationAccumulator`: Cumulative tracker. 
  * **Variables:** Bars for authority, fear, isolation, urgency, compliance.
  * **`observe()`:** Charges specific bars based on the current stage and confidence (e.g., `FEAR_INDUCTION` charges the fear bar by 30%). Never decays.
**Functions:**
- `fuse()`: The core heuristic math. Calculates base threat, ratchets it against the previous score using `DECAY_PER_S` (2.5), and returns the specific drivers responsible for the score.

### 6. `engine/session.py`
**Classes:**
- `Session`: The core State Machine.
  * **`ingest()`:** Routes caller text to classifier, twin scoring, manipulation, passport. Routes victim text to coercion. 
  * **`_recompute()`:** Fetches all subsystem snapshots. Calls `fuse()`. Triggers `GUARDIAN_ALERTED` if threshold crossed. Updates RAG Narration.
  * **`attempt_payment()`:** The circuit breaker. If threat is above `PAYMENT_HOLD_THRESHOLD (55.0)`, mutates `payment_state` to `"HELD"`.
  * **`frame()`:** Generates a massive JSON dict representing the entire state to be sent to the frontend.

### 7. `rag/store.py`
**Classes:**
- `BM25Index`: Okapi BM25 implementation. Calculates inverse document frequency (IDF) and term frequency (TF) at init. `search()` applies tags as a strict filter, then computes scores.
- `DenseIndex`: Uses numpy dot product over embeddings. 
- `KnowledgeBase`: Loads markdown, splits by `##`. Chooses `DenseIndex` if torch works, otherwise falls back to `BM25Index`.

### 8. `rag/coach.py`
**Classes:**
- `CoachLibrary`: Loads `coach_library.json`.
  * **`suggest(stage, escalation, victim_state)`:** Looks up the current stage. If the victim is already compliant, skips weak lines and escalates to the strongest anti-fraud statement. Merges `sources` by dynamically querying `get_kb().search()` to find citations for the suggested tactic.

### 9. `ml/build_dataset.py` & `ml/train.py` (Data Pipeline)
* **`build_dataset.py`**: Reads raw calls. `split_by_call()` guarantees that calls generated from the same seed archetype are kept on the same side of the train/test split. `to_utterances()` flattens calls and removes generic duplicates ("haan ji"). `fit_transitions()` collapses consecutive stage runs to build the Markov matrix.
* **`train.py`**: Wraps HuggingFace `Trainer`. Uses `LBFGS` at the very end to run temperature scaling calibration on the validation set, storing the final `T` scalar into `metrics.json`. Saves the `pytorch_model.bin` model artifact.

*(End of Comprehensive Walkthrough)*
