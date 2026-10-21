# AegisAI — Product Requirements Document

**AegisAI: An Agentic Digital Public Safety Platform for Autonomous Multi-Modal
Fraud Investigation**

| | |
|---|---|
| Version | 1.0 — 2026-10-22 (T-01) |
| Status | 🧪 Awaiting the owner's review |
| Owner | Dhrumil Kadchha |
| Team | **[ASSUMPTION]** four members per the brief; the repository credits two authors. Names to be supplied |
| Programme | Final-year Major Project, B.Tech CSE, Dayananda Sagar University, AY 2026–27 (brief §2) |
| Sources | [`AEGIS_AGENT_BRIEF.md`](../AEGIS_AGENT_BRIEF.md) · [`AUDIT.md`](AUDIT.md) · [`ARCHITECTURE.md`](ARCHITECTURE.md) · [`AUTH.md`](AUTH.md) · [`DATASETS.md`](DATASETS.md) · [`TASKS.md`](TASKS.md) |

**How to read this document.** It describes the product the brief pitches,
grounded in what the audit found exists. Every requirement carries a status:

- ✅ **Built** — exists and was run (audit, 2026-10-09, or a later approved task)
- 🟡 **Partial** — exists, incomplete
- 🆕 **New** — does not exist; the task that builds it is named

Anything guessed rather than known is marked **[ASSUMPTION]** for the owner to
confirm or correct. Nothing here describes as built something the audit marks
missing.

---

## 1. Overview

### 1.1 The problem

India records cyber-fraud at a volume the response system cannot absorb. The
National Cybercrime Reporting Portal received **1.14 million** complaints in
2023, and digital-arrest fraud alone cost **₹1,776 crore** in the first nine
months of 2024 (both figures as cited on the product's landing page). The
fraud is joined up: one operation reaches a person by SMS, moves them to
WhatsApp, sends a forged warrant as a PDF, keeps a voice on the line for hours,
and collects on a UPI ID. The defence is not: a URL scanner never hears the
call, and a call blocker never reads the PDF.

### 1.2 The evidence-assembly gap

Detection is not the bottleneck. Most victims and many first responders can
tell, eventually, that something was a scam. What turns a complaint into
action is **an evidence package an investigator can act on**: what was said,
which identifiers were used, which earlier cases share them, how sure the
system is, and why. Today that package is assembled by hand, from screenshots
and memory, if at all. **[ASSUMPTION]** the brief's statement that "only a tiny
fraction" of complaints become FIRs — the repository holds no sourced figure
for the conversion rate; one must be cited before it is used in a review.

### 1.3 Why now

- Fraud has moved to **multimodal, scripted, multi-hour** operations — digital
  arrest is a script, not a message — which single-channel filters cannot see.
- Open multilingual models (MuRIL, Whisper) make **Hindi and Hinglish**
  analysis feasible on modest hardware.
- **Agent orchestration** (LangGraph) makes it practical to run many narrow,
  auditable checks and keep a trace of each, instead of one opaque model.

### 1.4 Target outcome

A citizen or investigator submits evidence — a message, a screenshot, a call
recording, a UPI ID — and within seconds receives a **verified, explained,
scored case file**: the risk and how sure the system is, the signals behind
it, the identifiers it found and the earlier cases they connect to, and the
next thing to do. For a scam still in progress, the same engine runs **live**
and intervenes before money moves.

### 1.5 Base paper and contribution

**[ASSUMPTION]** The brief names **SAGE (arXiv:2606.08146)** — LLM multi-agent
fraud detection on tabular data — as the base paper. It has not been read for
this project (audit Q5 is still open); nothing in this document characterises
it beyond the brief's own sentence. The intended contribution over it:
**multimodal input, a case-file output, and live intervention.**

---

## 2. Goals and non-goals

### 2.1 Goals for AY 2026–27

| ID | Goal | Measured by |
|---|---|---|
| G-1 | One submission flow takes a message, screenshot, call recording or UPI ID to a scored, explained case file | US-01 – US-05 pass end to end (T-47, T-61) |
| G-2 | Seven agent roles (A1–A7) run on LangGraph; A7 can reject or downgrade a finding | The A7 rejection path is tested (T-21, T-22) |
| G-3 | Four modalities are scored separately and fused with **calibrated** late fusion | ECE reported per modality and fused (T-41, T-42) |
| G-4 | A scam-stage state machine tracks a conversation and forecasts the next move | Stage accuracy and forecast accuracy on held-out conversations (T-46) |
| G-5 | Live intervention on an in-progress scam, with **measured** latency | p95 utterance-to-frame latency on file (T-53) |
| G-6 | Research-grade evaluation: leak-free splits, baselines, ablations, a results file | `research/results/` reproduces every reported number (T-56, T-57) |
| G-7 | False positives on benign evidence are treated as failures | A false-positive harness gates CI (T-43) |

### 2.2 Non-goals this semester

Decided under the owner's delegation on 2026-10-09 (audit §9, Q1). Each is in
the "Parked" table of `TASKS.md` and can be brought back by the owner.

- Email-header analysis; APK static analysis; image forensics (ELA, CLIP, logo
  matching); voice authenticity; video; PDF/DOCX parsing beyond text.
- WebRTC capture, streaming speech-to-text, an SMS channel, SIP integration.
  **Live intervention is demonstrated on text utterances**, and says so.
- Migrating the fraud graph to Neo4j or retrieval to Qdrant (NetworkX and the
  in-house store work behind the same interfaces).
- Anomaly detection; load testing; inter-annotator agreement studies; a public
  dataset release; a human evaluation study.
- A Hindi-language interface (audit U-06) — recorded, not scheduled.
- Any direct integration with a police or bank system. The case file is an
  export a human files; AegisAI does not file it.

---

## 3. Users and personas

Seven roles exist in code (`services/api/permissions.py`, `docs/AUTH.md`):
`citizen`, `viewer`, `researcher`, `analyst`, `police`, `admin`, `owner`. The
brief's three personas map onto them as below; the researcher is a fourth
persona the code already serves.

### P-1 — Citizen / victim (`citizen`)

*Meera, 58, retired teacher in Pune.* Receives a video call from "CBI Mumbai"
saying a parcel in her name contained drugs and that she is under digital
arrest. She is told not to tell her family.

| | |
|---|---|
| Needs | A fast, plain answer — *is this real?* — and what to do next, in language she understands, without creating an account first |
| Pain points | Fear and time pressure engineered by the caller; official helplines she cannot verify; no way to prove later what happened |
| Jobs to be done | Check a message, number, UPI ID or screenshot · get protection during a call · preserve evidence · file a complaint with it |
| Lands on | `/home` (citizen surfaces need no account: `/analyze`, `/live`, `/learn`, `/emergency`) |

### P-2 — Cyber-cell investigator / analyst (`police`, `analyst`)

*Inspector Rao, district cyber cell.* Forty open complaints, most of them a
screenshot and a paragraph.

| | |
|---|---|
| Needs | A queue of cases with the evidence already assembled; the identifiers in each and which other cases share them; a file she can attach to an FIR |
| Pain points | Re-typing evidence from screenshots; no view across complaints; cannot tell which signals a tool's verdict rests on, so cannot defend it |
| Jobs to be done | Triage the queue · open a case and read its verified findings and trace · see the campaign it belongs to · export the case file |
| Lands on | `/police/dashboard` (police), `/dashboard` (analyst) |

### P-3 — Administrator (`admin`, `owner`)

*An organisation's IT lead; the platform owner above all organisations.*

| | |
|---|---|
| Needs | Manage users and roles; see an audit trail; set retention; know what the deployment is actually running |
| Pain points | Shared demo credentials; no record of who did what; uncertainty whether a fallback model is serving |
| Jobs to be done | Invite and disable users · change roles · read the audit log · create tenants (owner) · check health and the model card |
| Lands on | `/admin/dashboard` |

### P-4 — Researcher (`researcher`)

*A team member or examiner reproducing the paper's numbers.*

| | |
|---|---|
| Needs | Dataset statistics, model evaluation and anonymised trends; every number traceable to a file |
| Jobs to be done | Read the research overview · reproduce results from `research/` |
| Lands on | `/research/dashboard` |

---

## 4. User stories

Status: ✅ built · 🟡 partial · 🆕 new, with the task that delivers it.

**US-01 — Check a suspicious message** · P-1 · ✅ (`/analyze`, `POST /api/analyze/text`)
- **Given** a citizen with no account on `/analyze`
- **When** they paste a message and submit
- **Then** they see a score from 0 to 100, a level shown as colour **and** label **and** number, a verdict, the signals behind it, and recommended actions — and a benign message (e.g. a bank debit alert) scores CALM.

**US-02 — Check a screenshot** · P-1 · 🟡 legacy path only (`POST /api/analyze/image`); in the graph: T-27, T-28
- **Given** a screenshot of a fake notice or payment request
- **When** it is uploaded
- **Then** the text and any QR payload are extracted and scored like a pasted message; **and if no OCR engine is installed**, the answer says so (`ocr:unavailable`) instead of scoring an empty read.

**US-03 — Check a call recording** · P-1 · 🟡 legacy path only (`POST /api/analyze/audio`); in the graph: T-29
- **Given** a voice note or recording
- **When** it is uploaded
- **Then** it is transcribed, the transcript is scored, the stage of the scam script is shown; and a missing ASR backend is reported as `asr:unavailable`.

**US-04 — Check a UPI ID or caller number** · P-1 · 🟡 (`POST /api/analyze/upi`, number spoofing); in the graph: T-30
- **Given** a UPI ID, a `upi://pay` link or a phone number
- **When** it is checked
- **Then** the structural findings are listed (impersonating handle, unknown PSP, personal number posing as an office, international routing), each with the source it cites; and metadata alone can never raise a case to CRITICAL.

**US-05 — Submit evidence and receive a case file** · P-1, P-2 · 🟡 (`POST /api/investigations` runs; no score, entities or actions — B-02, B-03); T-17 – T-25, T-47
- **Given** one or more evidence items submitted together
- **When** the investigation completes
- **Then** the case file holds: the inputs and their detected types; extracted entities; each agent's findings, status and latency; which findings A7 upheld, downgraded or rejected; a calibrated score with an explanation; recommended actions; and any degradation, named.

**US-06 — Watch an investigation run** · P-2 · 🟡 (`GET …/stream`, `/investigate`); T-48, T-49
- **Given** a submitted investigation
- **When** the investigator opens it
- **Then** each agent's progress appears as it runs, and on completion each node shows its inputs, outputs and latency.

**US-07 — See why a finding was rejected** · P-2 · 🆕 T-21, T-22, T-25
- **Given** a finding A7 rejected or downgraded
- **When** the investigator opens it
- **Then** the original finding, A7's challenge and the reason are shown, and the score shows it was computed without (or with reduced weight on) that finding.

**US-08 — Export a case file** · P-1, P-2 · 🟡 (JSON + PDF exist, thin); T-50
- **Given** a completed investigation
- **When** the user exports it
- **Then** a JSON and a PDF are produced containing entities, verified findings, score and explanation, a timeline and SHA-256 hashes of every evidence item — something an investigator could attach to a complaint.

**US-09 — Protection during a live call** · P-1 · 🟡 (text utterances; latency unmeasured); T-53, T-54
- **Given** a citizen in a protected session, with recording consent given and a visible indicator
- **When** each utterance arrives
- **Then** the stage, coercion index, risk and forecast update; at HIGH a verbatim coach line from the reviewed library appears; a payment attempt can be held; a guardian can be alerted — within a p95 latency that is measured and stated.

**US-10 — Preserve evidence and file a complaint** · P-1 · ✅ (`/api/shield/preserve`, vault, complaint PDF — not exercised in the audit)
- **Given** a verified submission
- **When** the citizen chooses to preserve it
- **Then** they receive a token; with it they can read the preserved report and download a structured complaint package, without an account.

**US-11 — Triage a queue** · P-2 · 🆕 T-51
- **Given** an investigator with many open cases
- **When** they open the queue
- **Then** cases are sortable by risk and age, assignable, and filterable by status; a caller with only `*_READ_OWN` sees only their own cases, and another's case returns 404, not 403.

**US-12 — See the campaign behind a case** · P-2 · 🟡 (`/intel`, clusters; not linked to investigations); T-34
- **Given** a case whose phone number or UPI ID appears in earlier cases
- **When** the investigator opens it
- **Then** the linked cases, shared identifiers, cluster risk and states affected are shown, with co-occurrence stated as evidence, not proof.

**US-13 — Manage users** · P-3 · ✅ (`/api/auth/users`, `/admin/dashboard`)
- **Given** an admin
- **When** they change a user's role or disable them
- **Then** the change takes effect, every session that user holds is revoked, and the action appears in the audit log.

**US-14 — Read the audit log** · P-3 · 🟡 (`GET /api/audit`; viewer UI is T-55)
- **Given** an admin
- **When** they open the audit view
- **Then** each sensitive action shows who, what, when and on which record.

**US-15 — Set retention** · P-3 · 🆕 T-55
- **Given** an admin
- **When** they set a retention period
- **Then** evidence and live-session data older than it are deleted on schedule, and the deletion is audited.

**US-16 — Know what the model is** · P-3, P-4 · ✅ (`/model`, `GET /api/model/card`, `GET /api/health`)
- **Given** anyone with the model page
- **When** they open it
- **Then** they see which classifier is serving and why, its measured figures on a leak-free comparison, and its limitations — and a fallback is never presented as the best model.

**US-17 — Reproduce a result** · P-4 · 🆕 T-06, T-56
- **Given** a researcher with the repository
- **When** they run the experiment script
- **Then** the committed results file is reproduced byte for byte.

---

## 5. Functional requirements

Grouped as the brief lists them. **Path** is where it lives today; **Task** is
what builds or finishes it.

### 5.1 Ingestion

| ID | Requirement | Status | Path / Task |
|---|---|---|---|
| FR-01 | Accept text, files and identifiers as evidence items in one submission | ✅ | `investigations/intake.py` |
| FR-02 | Detect each item's type from its bytes, not its extension, and flag a conflict with the declared type | ✅ | `agents/classify/sniff.py` (≥98% on a 200-item corpus with 20 adversarial items) |
| FR-03 | Enforce a per-file size cap while reading (default 4 MB, `settings.max_upload_bytes`) | ✅ | `config.py`, `intake.py` |
| FR-04 | Hash every evidence item (SHA-256) at intake and keep the hash with the case | ✅ | `intake.py` |
| FR-05 | Validate uploads on the `/api/analyze/*` routes by magic bytes (today they check the extension) | 🆕 | T-59 |
| FR-06 | A per-organisation upload quota | 🆕 | T-59 (S-04) |

### 5.2 Modality — text and chat

| ID | Requirement | Status | Path / Task |
|---|---|---|---|
| FR-07 | Classify each caller turn into one of eight stages (GREETING … PAYMENT_EXECUTION, BENIGN) in English, Hindi and Hinglish | ✅ (lexical serves; the transformer failed the leak-free gate) | `engine/classifier.py` |
| FR-08 | Match caller turns against known scam scripts, robust to paraphrase | ✅ | `engine/scripts.py`, `script_match` |
| FR-09 | Track the victim's coercion independently of the stage | ✅ | `engine/coercion.py`, `coercion_tracker` |
| FR-10 | Run six mechanical trust checks (e.g. OTP request) with a cited source each | ✅ | `engine/passport.py`, `trust_passport` |
| FR-11 | Extract entities (phones, UPI IDs, URLs, amounts, claimed authorities) inside the graph | 🆕 (legacy path only, B-03) | T-18 |
| FR-12 | Produce a per-modality text score | 🆕 | T-26, T-39 |

### 5.3 Modality — audio and call

| ID | Requirement | Status | Path / Task |
|---|---|---|---|
| FR-13 | Transcribe a recording (Whisper) and score the transcript | 🟡 legacy path | `ingest/asr.py`; graph agent T-29 |
| FR-14 | Report a missing ASR backend or ffmpeg as `asr:unavailable` | ✅ | `routes/analyze.py` |
| FR-15 | Separate speakers where possible (diarization) | 🟡 | `ingest/diarize.py` |
| FR-16 | Produce a per-modality audio score | 🆕 | T-29, T-39 |

### 5.4 Modality — image and document

| ID | Requirement | Status | Path / Task |
|---|---|---|---|
| FR-17 | Extract text from images (Tesseract by default; EasyOCR, configured for English and Hindi, by `AEGIS_OCR`) | 🟡 legacy path | `engine/ocr.py`; graph agent T-27 |
| FR-18 | Decode QR codes and route the payload by type | 🟡 legacy path | `engine/ocr.py`; T-28 |
| FR-19 | Read text documents (.txt, .csv, .json, .md, .log, .vtt, .srt) | ✅ | `POST /api/analyze/file` |
| FR-20 | Treat low-confidence extraction as low-confidence evidence | 🆕 | T-27 |
| FR-21 | Produce a per-modality image/document score | 🆕 | T-27, T-39 |

### 5.5 Modality — transaction and metadata

| ID | Requirement | Status | Path / Task |
|---|---|---|---|
| FR-22 | Structural UPI checks: impersonation tokens, unknown PSP handle, personal number as payee, inverted payment framing | ✅ legacy path | `engine/upi.py`; graph agent T-30 |
| FR-23 | Caller-number checks: reported list, international routing, VoIP prefix, caller ID vs claimed authority | ✅ | `engine/spoofing.py`, `number_spoofing` |
| FR-24 | Metadata may raise a score but can never make a case CRITICAL alone | ✅ | `engine/threat.py` (bounded escalator) |
| FR-25 | URL analysis behind an SSRF guard (block private ranges, re-resolve DNS after every redirect, cap depth, http/https only) | 🆕 | T-31, T-32 |
| FR-26 | Produce a per-modality transaction/metadata score | 🆕 | T-30, T-39 |

### 5.6 Agents

| ID | Requirement | Status | Path / Task |
|---|---|---|---|
| FR-27 | Every agent implements the `Agent` protocol and returns a valid `AgentResult` | ✅ | `agents/base.py` |
| FR-28 | Every agent is registered with a version; an unversioned agent is refused | ✅ | `agents/registry.py` |
| FR-29 | Every agent records latency and status, and has a tested degradation path | ✅ for the 8 registered | `orchestration/policy.py` |
| FR-30 | Every agent ships a benign-input (false-positive) test | ✅ for the 8 registered | `services/api/tests/` |
| FR-31 | The seven roles A1–A7 of §6 are each implemented | 🟡 A1, A2 partial, A5 partial; rest 🆕 | T-18, T-21 – T-36 |

### 5.7 Orchestration

| ID | Requirement | Status | Path / Task |
|---|---|---|---|
| FR-32 | Run agents on a LangGraph `StateGraph` with per-node timeout and retry | ✅ | `orchestration/graph.py`, `policy.py` |
| FR-33 | Record a trace span per node: inputs, outputs, latency, status | ✅ | `orchestration/` trace recorder |
| FR-34 | Run long investigations on a worker with an in-process fallback, and report progress the UI can stream | ✅ (worker path last verified 2026-08-27) | `jobs/`, `services/worker/`; re-verify T-07 |
| FR-35 | Fan out on discovered entities with bounded recursion (default depth 2) | 🆕 | T-36 |
| FR-36 | Place A7 between the evidence join and the judge, able to reject or downgrade | 🆕 | T-21, T-22 |
| FR-37 | Carry a request and case ID through structured logs | 🆕 (D-08) | T-12 |

### 5.8 Fusion and scoring

| ID | Requirement | Status | Path / Task |
|---|---|---|---|
| FR-38 | The score comes from calibrated models, deterministic rules and graph evidence — **never from the LLM** | ✅ invariant; enforced in `llm.py`'s instructions | `engine/threat.py`, `llm.py` |
| FR-39 | Every point of the score is attributed to a named driver | ✅ legacy path | `engine/threat.py` |
| FR-40 | The investigation path produces a score (provisional, tagged `score:uncalibrated`, until calibration lands) | 🆕 (B-02) | T-20 |
| FR-41 | Per-modality scores are calibrated, and fused late with documented weights; ECE is reported | 🆕 | T-39 – T-42 |
| FR-42 | A finding A7 rejected does not contribute; a downgraded one contributes at reduced weight | 🆕 | T-21, T-42 |

### 5.9 Scam-stage tracking

| ID | Requirement | Status | Path / Task |
|---|---|---|---|
| FR-43 | Track the stage across a live conversation and publish it in every `StateFrame` | ✅ | `engine/session.py` |
| FR-44 | Forecast the next stage, the seconds to it, and the seconds to payment (Markov twin) | ✅ | `engine/twin.py` |
| FR-45 | Generalise the stage machine from calls to any conversation (chat transcripts), evaluated separately | 🆕 | T-46 |

### 5.10 Case file generation

| ID | Requirement | Status | Path / Task |
|---|---|---|---|
| FR-46 | Generate a case file from every investigation | 🟡 thin (findings and trace; no score, entities, actions) | `investigations/report.py`; T-50 |
| FR-47 | The case file includes entities, verified findings with A7's verdict, score, explanation, recommendations, timeline, evidence hashes, degradation | 🆕 | T-23, T-24, T-50, T-52 |
| FR-48 | Generate an evidence package from a live session | ✅ | `GET /api/session/{id}/report` |

### 5.11 Live intervention

| ID | Requirement | Status | Path / Task |
|---|---|---|---|
| FR-49 | Accept utterances over REST and push frames over a WebSocket | ✅ | `routes/session.py` |
| FR-50 | Show coach lines **verbatim** from the human-reviewed library (14 lines); a model may rank, never write them | ✅ | `rag/`, `engine/session.py` |
| FR-51 | Hold, cancel or approve a payment attempt; acknowledge a guardian | ✅ endpoints | `routes/session.py` |
| FR-52 | Require explicit recording consent and show a visible indicator; retention is configurable | 🆕 consent capture and retention | T-54, T-55 |
| FR-53 | Run the live session on a pruned real-time subgraph and measure p95 latency | 🆕 | T-53 |

### 5.12 Dashboard

| ID | Requirement | Status | Path / Task |
|---|---|---|---|
| FR-54 | Role-specific dashboards (`/dashboard`, `/police/dashboard`, `/admin/dashboard`, `/research/dashboard`) | ✅ | `pages/RoleDashboard.tsx` etc. |
| FR-55 | Intelligence view: clusters, centrality, predicted links, geography | ✅ | `/intel`, `/api/intel/*` |
| FR-56 | Investigation workspace: evidence, live agent progress, findings, risk, actions | 🆕 | T-48 |
| FR-57 | Agent trace view: the graph, nodes coloured by status, inputs/outputs/latency on click | 🆕 | T-49 |
| FR-58 | Case queue with status, assignment and triage | 🆕 | T-51 |
| FR-59 | Every async view has loading, empty, error and success states | 🟡 | T-16, T-60 |

### 5.13 Auth and roles

| ID | Requirement | Status | Path / Task |
|---|---|---|---|
| FR-60 | Seven roles, one grant map (`permissions.py`), revocable server-side sessions | ✅ | `auth.py`, `permissions.py` |
| FR-61 | Tenancy (`org_id`) enforced in the repository layer | ✅ | `stores/` |
| FR-62 | A caller with only `*_READ_OWN` is narrowed in the query; another's record 404s | ✅ | `docs/AUTH.md` |
| FR-63 | Every route declares its permission, or is documented as deliberately public | 🟡 **gap found during T-01:** 25 routes — all 8 analyze, all 7 shield, 10 of 13 session — declare none and do not identify the caller; `ANALYZE_USE` exists and is required nowhere (audit S-07) | T-59 |
| FR-64 | Production refuses open demo mode | 🟡 (S-01; `render.yaml` sets `AEGIS_AUTH=1`; production not probed) | T-66 |

### 5.14 Export

| ID | Requirement | Status | Path / Task |
|---|---|---|---|
| FR-65 | Export an investigation as JSON and PDF | ✅ | `GET /api/investigations/{id}/report`, `.pdf` |
| FR-66 | Export a live-session evidence package as PDF | ✅ | `GET /api/session/{id}/report.pdf` |
| FR-67 | Export a citizen complaint package as PDF | ✅ | `GET /api/shield/vault/{token}/complaint.pdf` |
| FR-68 | Case file v2 export with hashes, timeline and A7 verdicts | 🆕 | T-50 |

### 5.15 Admin

| ID | Requirement | Status | Path / Task |
|---|---|---|---|
| FR-69 | Create, edit, disable users; change roles (revokes sessions) | ✅ | `/api/auth/users` |
| FR-70 | Create tenants (owner) | ✅ | `/api/orgs` |
| FR-71 | Audit log of sensitive actions, readable by admins | ✅ API / 🆕 viewer | `GET /api/audit`; T-55 |
| FR-72 | Retention settings, enforced on a schedule | 🆕 | T-55 |
| FR-73 | Report what the deployment runs: health, classifier, degradation | ✅ | `GET /api/health`, `/model` |

---

## 6. Agent specification

**[ASSUMPTION]** The brief says "6 specialist agents + 1 adversarial verifier".
No document in the repository names the six (audit Q2). The **roles A1–A7**
below are the working names, each implemented by one or more registered
agents. Every agent returns the same `AgentResult` schema
(`schema/models.py`):

```text
AgentResult { agent: str, version: str, status: OK|DEGRADED|SKIPPED|ERROR,
              confidence: 0..1, findings: Finding[], features: {str: float},
              latency_ms: int, provenance: str[], error: str? }
Finding     { label: str, value: str?, confidence: 0..1, source: str, detail: str? }
```

Models are swappable through config (`AEGIS_*`); the LLM provider is chosen in
`services/api/llm.py` (Gemini, Ollama or Anthropic) and is used only to explain.

| Role | Responsibility | Inputs | Outputs (beyond `AgentResult`) | Tools it may call | Model | Failure behaviour | How A7 challenges it |
|---|---|---|---|---|---|---|---|
| **A1 Intake & classification** — `input_classifier` ✅ | Decide what each evidence item is from its bytes; route the graph | `state.inputs` (bytes via blob URI, inline text, filename, declared type) | One `detected_type` finding per item; `type_conflict` where the label lies; sets `state.input_types` | Magic-byte sniffing, blob store | None (deterministic) | Unknown type → `UNKNOWN`, routed to text if text is present; never blocks the graph | A conflict between declared and detected type is surfaced to A7, which may downgrade findings drawn from that item |
| **A2 Conversation & text** — `stage_classifier`, `script_match`, `coercion_tracker`, `trust_passport`, `digital_twin` ✅ (text only) | Read the conversation: stage per caller turn, closeness to a known script, victim coercion, six trust checks, next-stage forecast | Caller and victim turns (`conversation.py`) | `stage` findings, `peak_stage`; `script_similarity`; `coercion_index`; `trust_pct`; forecast | Lexical / fused stage classifier, script templates, knowledge base for citations | Lexical classifier (serving); MuRIL behind the leak-free gate; Markov twin | Classifier unavailable → lexical fallback, tagged `clf:lexical_fallback`; single-line input → twin SKIPs | A7 checks a stage finding's confidence against `MIN_STAGE_CONFIDENCE`, and a script match against whether the matched template's stage agrees with the classifier; disagreement → downgrade |
| **A3 Visual & document** — 🆕 (T-27, T-28) | Extract text and QR payloads from images and documents | Image/document evidence items | `ExtractedText` with confidence; QR payloads routed by type | Tesseract / EasyOCR, zbar | OCR engines (no LLM) | Engine missing → `ocr:unavailable`, no score from an empty read | Low-confidence extraction is challenged; findings resting only on it are downgraded |
| **A4 URL & infrastructure** — 🆕 (T-31, T-32) | Assess URLs: lexical features offline, then guarded network checks | URLs from entities | Domain age, redirect chain, typosquat distance, certificate | SSRF-guarded fetcher, cached lookups | None | Network unavailable → offline features only, tagged; never a live call without a cached fallback | A7 refuses any finding whose fetch was not SSRF-guarded, and downgrades a "new domain" finding when the domain is on an allow-list |
| **A5 Financial & identity** — `number_spoofing` ✅; UPI 🆕 in graph (T-30) | Check UPI IDs and caller numbers structurally | Entities: phones, UPI IDs, payment links | `spoofing_risk`; UPI findings each with a cited source | Reported-number list (synthetic sample), PSP handle list | None | No identifier → SKIP, and fusion receives `None`, not 0 | A7 caps metadata: a case cannot reach CRITICAL on A5 alone (already enforced in fusion; A7 makes it explicit per finding) |
| **A6 Intelligence** — 🆕 in graph (T-33 – T-35; legacy code exists) | Connect the case to earlier cases and cited guidance | Entities | Linked cases, cluster, centrality; retrieved passages | NetworkX fraud graph, retrieval store | sentence-transformers retrieval | Store unreachable → snapshot or none, tagged | Co-occurrence is weighted evidence, not proof: A7 downgrades a link that rests on a single shared identifier |
| **A7 Adversarial verifier** — 🆕 (T-21 deterministic, T-22 LLM) | Challenge every finding before the judge: **uphold, downgrade or reject**, with a reason | All findings and their provenance | A verdict per finding: `UPHELD`, `DOWNGRADED(weight)`, `REJECTED`, plus reason | Deterministic rule set; an LLM challenger that may only *argue* against a finding, never score | Rules; LLM via `llm.py` | LLM unavailable → deterministic challenger only, tagged; A7 failing entirely → findings pass unchallenged and the case says so | — (A7 is the challenger; its own decisions are tested: T-21 asserts a rejection removes the finding's contribution) |
| *Decision layer* (not an agent) — `threat_fusion` ✅ legacy weights | Fuse verified findings into one score, attribute every point, explain | Features and A7 verdicts | `risk_score`, `risk_level`, `confidence`, drivers, explanation | Calibrators, fusion weights, LLM for prose | Calibrated late fusion (T-41, T-42) | Missing modality → fused over what is present; `confidence` is the fraction reached | Consumes A7's verdicts (FR-42) |

---

## 7. Non-functional requirements

| ID | Area | Requirement | Status |
|---|---|---|---|
| NFR-01 | Latency (batch) | A text-only investigation completes in under 5 s p95 on a laptop; multimodal under 30 s. **Targets, not measurements** — T-58 measures them | 🆕 |
| NFR-02 | Latency (live) | Real-time agents under 400 ms p95; utterance-to-frame p95 measured and stated. "Real-time" is not used until it is measured (invariant 7) | 🆕 T-53 |
| NFR-03 | Budget | An investigation has a hard budget (45 s today, `/api/health` `budget_s`); a node that times out is recorded, not fatal | ✅ |
| NFR-04 | Reliability | Every dependency has a fallback that still answers and records a tag in `degraded` (invariant 4) | ✅ for existing paths |
| NFR-05 | Reliability | A worker killed mid-job does not lose the investigation (retry policy, dead-letter queue) | ✅ last verified 2026-08-27; T-07 re-verifies |
| NFR-06 | Privacy | Evidence is stored per organisation; evidence items are hashed; the token of a session is never stored | ✅ |
| NFR-07 | Privacy | Configurable retention for evidence and live sessions, enforced and audited | 🆕 T-55 |
| NFR-08 | Privacy | Live audio requires explicit consent and a visible indicator; covert recording is never designed for | 🟡 indicator ✅, consent capture 🆕 T-54 |
| NFR-09 | Privacy | Demo data is labelled as demo in the database and the UI; nothing synthetic can be mistaken for real | 🟡 T-64 |
| NFR-10 | Security | SSRF guard before any URL fetch; APK analysis (parked) only static, network-less, read-only | 🆕 T-31 |
| NFR-11 | Security | Uploads validated by magic bytes with size caps on every route | 🟡 FR-05 |
| NFR-12 | Security | Evidence text is untrusted data in every prompt, never instructions; tested with injection inputs | 🆕 (S-03) T-62 |
| NFR-13 | Security | Secrets only in the environment; `.env.example` current; git history clean | ✅ |
| NFR-14 | Security | Every route declares its permission (S-07) | 🟡 T-59 |
| NFR-15 | Explainability | Every score lists its drivers; every finding names its source; the LLM never scores | ✅ legacy path; 🆕 graph T-24 |
| NFR-16 | Explainability | Every agent's trace is stored so the UI can show why | ✅ |
| NFR-17 | False positives | Benign input is a first-class test case; a false-positive harness gates CI | 🟡 per-agent tests ✅; harness T-43 |
| NFR-18 | Accessibility | WCAG 2.1 AA: contrast measured, visible focus, keyboard path through each main flow, risk never by colour alone | 🟡 T-60 |
| NFR-19 | Responsiveness | Every screen usable from 375 px to desktop with no horizontal scroll | 🟡 T-60 |
| NFR-20 | Reproducibility | Every reported number traces to a script and a results file; a model is never scored on its own training data | 🟡 gate ✅ (T-05); results T-06, T-56 |

---

## 8. Data model

### 8.1 Persistent (SQLAlchemy, migrations `0001` – `0003`)

| Entity | Table | Key fields | Relations | Status |
|---|---|---|---|---|
| Organisation | `organizations` | id, slug, name, created_at | has users, investigations | ✅ |
| Role | `roles` | name (unique), description | many-to-many permissions | ✅ |
| Permission | `permissions` | code (e.g. `INVESTIGATION_CREATE`) | via `role_permissions` | ✅ |
| User | `users` | id, email (unique), password_hash (PBKDF2-SHA256), role, role_id, org_id, full_name, phone, avatar_url, disabled, email_verified, created/updated/last_login | belongs to org and role; has sessions | ✅ |
| Session | `user_sessions` | jti, user_id, expires_at, revoked_at, last_seen, IP, user agent — **never the token** | belongs to user | ✅ |
| Password reset | `password_resets` | single-use token hash, expiry | belongs to user | ✅ |
| Investigation | `investigations` | case_id, org_id, contract_v, created_by, mode, status, risk_score, risk_level, confidence, classification, `rest` (JSON: the remaining `InvestigationState`), timestamps | has evidence items, agent results, findings, entities | ✅ |
| Evidence item | `evidence_items` | id, case, kind, filename, media type, size, `sha256` (chain-of-custody handle), blob URI | belongs to investigation | ✅ |
| Agent result | `agent_results` | agent, version, status, confidence, latency_ms, error | belongs to investigation; has findings | ✅ |
| Finding | `findings` | label, value, confidence, source, detail | belongs to agent result | ✅ |
| Entity | `entities` | kind, value (canonical) | many-to-many investigations via `case_entities` | ✅ (populated by legacy paths; graph extraction is T-18) |
| Case record | `case_records` | report_id, session_id, org_id, created_by, caller_number, incident_type, peak_threat, final_level, package_json | a saved live-session evidence package | ✅ |
| Citizen report | `citizen_reports` | vault token, verdict, complaint data | standalone (token-addressed) | ✅ |
| Audit event | `audit_events` | actor, action, target, timestamp | — | ✅ |
| A7 verdict | 🆕 columns on `findings`: `verification` (`UPHELD`/`DOWNGRADED`/`REJECTED`), `verification_reason`, `verified_weight` | | | 🆕 T-17 |
| Per-modality score | 🆕 on `investigations`: `modality_scores` (JSON), `calibration_version` | | | 🆕 T-39 |
| Assignment | 🆕 `investigations.assigned_to`, `triage_status` | | | 🆕 T-51 |
| Retention policy | 🆕 `retention_policies` (org_id, evidence_days, session_days) | | | 🆕 T-55 |

### 8.2 The contract (`schema/models.py` ↔ `schema/types.ts`)

The single source of truth for what crosses the API (invariant 1). Live:
`StateFrame` (idempotent snapshot) and `Event` (one-shot edge), with `Stage`,
`ThreatLevel`, `VictimState`, `Forecast`, `TrustPassport`, `NumberIntel`,
`CoachSuggestion`. Investigation: `InvestigationState` — `inputs`,
`input_types`, `extracted_text`, `entities: EntitySet`, `transcript`,
`agent_results`, `threat_intel`, `graph_context`, `rag_context`,
`risk_features`, `risk_score`, `risk_level`, `confidence`, `classification`,
`evidence`, `recommendations`, `degraded`, `trace`.

**Additions, all `Optional[...] = None`** so existing fixtures stay valid:
`Finding.verification` and `verification_reason` (T-17), per-modality scores
on `InvestigationState` (T-39).

### 8.3 Stores beside the database

| Store | Today | Fallback |
|---|---|---|
| Fraud graph | NetworkX in process, seeded with a **synthetic** case set (`seed_cases()`): 115 cases, 9 clusters, 48 entities on 2026-10-22 | — (Neo4j parked) |
| Retrieval | In-house dense store: 31 passages from 4 curated documents | Lexical |
| Evidence blobs | Filesystem (`evidence_storage`), ephemeral by default in dev | — |
| Queue | Redis + Celery | In-process execution |

---

## 9. API surface

**73 routes**: 72 REST and one WebSocket, across nine routers. (The audit said
61; it undercounted. Counted from source on 2026-10-22.) Authentication is a
Bearer JWT; "Public" below means **no `require_permission` on the route** —
which for the analyze, shield and most session routes is the gap recorded as
S-07, not a design decision this document endorses.

**Errors.** Today handlers raise FastAPI `HTTPException` with a string
`detail`; validation errors return Pydantic's list (D-09). Codes in use:
400, 401, 403, 404, 409, 413 (too large), 415 (unsupported type), 422, 429
(rate limit), 503 (dependency unavailable). **T-13** introduces one envelope
for all of them: `{ "error": { "code", "message", "detail", "request_id" } }`.

### 9.1 Analyze — single-shot checks (`routes/analyze.py`)

| Method | Path | Auth | Request | Response | Errors |
|---|---|---|---|---|---|
| POST | `/api/analyze/text` | Public (S-07) | `{ text (1–200,000 chars), kind = "text", claimed_identity?, caller_number?, explain = false }` | `AnalysisResult`: score, level, verdict, summary, findings, drivers, recommended_actions, degraded, explanation? | 422 |
| POST | `/api/analyze/upi` | Public | `{ upi_id, claimed_identity? }` | `AnalysisResult` + `upi` analysis | 422 |
| POST | `/api/analyze/file` | Public | multipart `file` (.txt .json .csv .md .log .vtt .srt) | `AnalysisResult` + filename | 413, 415 |
| POST | `/api/analyze/image` | Public | multipart `file` (image), `claimed_identity?`, `caller_number?` | `AnalysisResult` + `ocr { engine, text, qr_payloads }`; `INSUFFICIENT` when nothing readable | 413, 415 |
| POST | `/api/analyze/audio` | Public | multipart `file` (audio) | `AnalysisResult` + `asr { backend, ok, text }`; `INSUFFICIENT` when no ASR | 413, 415 |
| GET | `/api/analyze/knowledge/search` | Public | `q`, `k` | retrieved passages | 422 |
| POST | `/api/analyze/knowledge/ask` | Public | `{ question (3–2,000 chars), k = 5 }` | grounded answer + citations, or none | 422 |
| GET | `/api/analyze/knowledge/docs` | Public | — | the corpus, grouped by document | — |

### 9.2 Investigations — the agent graph (`routes/investigations.py`)

| Method | Path | Auth | Request | Response | Errors |
|---|---|---|---|---|---|
| POST | `/api/investigations` | `INVESTIGATION_CREATE` | multipart `files[]` and/or `text` | 202 + `{ case_id, status }` | 413, 422 |
| GET | `/api/investigations` | `INVESTIGATION_READ_OWN` | — | case list, narrowed in the query by permission | — |
| GET | `/api/investigations/{case_id}` | `INVESTIGATION_READ_OWN` | — | `InvestigationState` | 404 |
| GET | `/api/investigations/{case_id}/report` | `INVESTIGATION_READ_OWN` | — | report JSON | 404 |
| GET | `/api/investigations/{case_id}/report.pdf` | `INVESTIGATION_READ_OWN` | — | PDF | 404, 503 (reportlab not installed) |
| GET | `/api/investigations/{case_id}/trace` | `INVESTIGATION_READ_OWN` | — | `TraceSpan[]` | 404 |
| GET | `/api/investigations/{case_id}/stream` | `INVESTIGATION_READ_OWN` | — | SSE of `InvestigationEvent` | 404, 409 (finished, or not running in this process) |
| DELETE | `/api/investigations/{case_id}` | `INVESTIGATION_DELETE` | — | 204 | 403, 404 |
| POST | 🆕 `/api/investigations/{case_id}/assign` | 🆕 `INVESTIGATION_ASSIGN` | `{ user_id }` | updated case | T-51 |

### 9.3 Live session (`routes/session.py`)

| Method | Path | Auth | Request | Response | Errors |
|---|---|---|---|---|---|
| POST | `/api/session` | Public (S-07) | `{ caller_number?, guardian_name? }` | session + first `StateFrame` | — |
| GET | `/api/session` | Public | — | sessions | — |
| GET | `/api/session/{id}` | Public | — | `StateFrame` | 404 |
| POST | `/api/session/{id}/utterance` | Public | `{ text (1–4,000), speaker = "CALLER", duration_s = 3.0, partial = false }` | `StateFrame` + `Event[]` | 404 |
| POST | `/api/session/{id}/guardian/ack` | Public | — | `StateFrame` | 404 |
| POST | `/api/session/{id}/payment/attempt` | `LIVE_SESSION_USE` | `{ amount_inr > 0, payee? }` | `StateFrame` | 404 |
| POST | `/api/session/{id}/payment/cancel` | `LIVE_SESSION_USE` | — | `StateFrame` | 404 |
| POST | `/api/session/{id}/payment/approve` | `LIVE_SESSION_USE` | — | `StateFrame` | 404 |
| GET | `/api/session/{id}/report` | Public | — | evidence package | 404 |
| POST | `/api/session/{id}/investigate` | Public | — | fused citizen report | 404, 503 |
| GET | `/api/session/{id}/report.pdf` | Public | — | PDF | 404 |
| DELETE | `/api/session/{id}` | Public | — | 204 | 404 |
| WS | `/api/session/ws/{id}` | Public | `ClientCommand` messages | `StateFrame` on a fixed clock + `Event`s | unknown session: an `error` message, then close |

### 9.4 Auth (`routes/auth.py`)

| Method | Path | Auth | Purpose | Errors |
|---|---|---|---|---|
| POST | `/api/auth/signup` | Public | create a `citizen` account and session | 409, 422, 429 |
| POST | `/api/auth/login` | Public | sign in | 401, 403 (disabled), 429 |
| POST | `/api/auth/logout` | Signed in | revoke this session | — |
| POST | `/api/auth/refresh` | Signed in | rotate the token | 401 |
| GET / PATCH | `/api/auth/me` | Signed in | read / edit own profile (name, phone) | 422 |
| GET / DELETE | `/api/auth/sessions` | Signed in | list / revoke other sessions | — |
| POST | `/api/auth/password/change` | Signed in | change password, revoke other sessions | 400, 403 |
| POST | `/api/auth/password/forgot` | Public | mint a single-use reset token | 422 |
| POST | `/api/auth/password/reset` | Public | consume it | 403, 422 |
| GET | `/api/auth/roles` | Signed in | roles and their permissions | — |
| GET | `/api/auth/demo-accounts` | Public | seeded roster (S-01); empty whenever auth is enforced | — |
| GET / POST | `/api/auth/users` | `USER_MANAGE` | list / create users | 403, 409, 422 |
| PATCH | `/api/auth/users/{user_id}` | `USER_MANAGE` | change role, enable/disable (revokes sessions) | 403, 404, 422 |
| GET | `/api/auth/status` | Public | what this deployment's auth is | — |

### 9.5 Intelligence (`routes/intel.py`)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/intel/stats` | `THREAT_INTEL_READ` | cases, clusters, campaigns, entities, loss |
| GET | `/api/intel/clusters` | `GRAPH_READ` | all clusters, worst first |
| GET | `/api/intel/clusters/{id}` | `GRAPH_READ` | cluster + subgraph + report (404 if unknown) |
| GET | `/api/intel/clusters/{id}/report` | `GRAPH_READ` | the cluster's report (404) |
| GET | `/api/intel/geo` | `THREAT_INTEL_READ` | state / district / city hotspots |
| GET | `/api/intel/points` | `THREAT_INTEL_READ` | per-case map points |
| GET | `/api/intel/centrality` | `GRAPH_READ` | most-reused entities |
| GET | `/api/intel/links` | `GRAPH_READ` | predicted hidden links |
| GET | `/api/intel/search` | `GRAPH_READ` | search by phone / UPI / wallet / email / case id |
| GET | `/api/intel/graph` | `GRAPH_READ` | capped whole-graph view |

### 9.6 Citizen shield (`routes/shield.py`)

| Method | Path | Auth | Purpose | Errors |
|---|---|---|---|---|
| GET | `/api/shield/helplines` | Public | official reporting directory | — |
| POST | `/api/shield/verify` | Public | verify a message / number / UPI | 422 |
| POST | `/api/shield/preserve` | Public | verify and preserve; returns a vault token | 422, 503 |
| GET | `/api/shield/vault/{token}` | Token | read a preserved report | 404 |
| GET | `/api/shield/vault/{token}/complaint` | Token | complaint package | 404 |
| GET | `/api/shield/vault/{token}/complaint.pdf` | Token | complaint PDF | 404 |
| GET | `/api/shield/awareness` | Public | fraud-awareness feed | — |

### 9.7 Reports, organisations, research, platform

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/api/session/{id}/report/save` | `REPORT_CREATE` | persist a live evidence package as a case record |
| GET | `/api/reports` · `/api/reports/{id}` | `REPORT_READ_OWN` | case records (404 on another's) |
| GET | `/api/audit` | `AUDIT_READ` | audit events |
| GET / POST | `/api/orgs` | `ORG_MANAGE` | list / create tenants |
| GET | `/api/orgs/current` | Signed in | the caller's tenant |
| GET | `/api/research/overview` | `RESEARCH_READ` | dataset statistics, evaluation, trends |
| GET | `/api/health` | Public | what is running, what is degraded |
| GET | `/api/model/card` | Public | model card |
| GET | 🆕 `/api/admin/retention` · PUT | 🆕 `ORG_MANAGE` | retention policy (T-55) |

---

## 10. Screens

22 page components today (`apps/web/src/App.tsx`). Every screen must meet
FR-59 (loading, empty, error, success) and NFR-18/19.

| Screen | Route | Who | Purpose | Key components | Status |
|---|---|---|---|---|---|
| Landing | `/` | Anyone | Explain the product honestly; live figures from the API | Hero network, problem web, evidence grid, pinned investigation, agent registry diagram, intelligence graph, research sidebar | ✅ (T-69, T-70) |
| Sign in · Sign up · Forgot · Reset | `/login`, `/signup`, `/forgot-password`, `/reset-password` | Anyone | Accounts | Auth shell, role switcher (demo) | ✅ |
| Citizen home | `/home` | Citizen, no account | Task-oriented start | Action cards | ✅ |
| Analyze (Shield) | `/analyze` | Citizen | US-01 – US-04, US-10 | Input tabs (text, file, image, audio, UPI), verdict, drivers, actions, preserve | ✅ |
| Live protection | `/live` | Citizen | US-09 | Consent, call indicator, risk meter, stage, coach line, payment hold | 🟡 consent capture T-54 |
| Case book | `/reports` | Citizen | Saved reports | List, report viewer | ✅ |
| Learn | `/learn` | Anyone | Knowledge base, cited | Search, document list | ✅ |
| Emergency | `/emergency` | Anyone | What to do now | Helplines, checklist | ✅ |
| Profile | `/profile` | Signed in | Own profile and sessions | Form, session list | ✅ |
| Role dashboard | `/dashboard`, `/police/dashboard` | Analyst, police, viewer | Overview | Stats, recent cases | 🟡 → queue T-51 |
| Live console | `/analyst/console` | Analyst | Watch a session; recorded stream labelled as such | Transcript, frame panels | ✅ |
| Guardian | `/guardian` | Analyst | Guardian acknowledgement flow | Alert, ack | ✅ |
| Analyzer | `/analyzer` | Analyst | Analyst-grade single-shot analysis | Same engine, more detail | ✅ |
| Intelligence | `/intel` | Analyst, police | US-12 | Graph, clusters, map, centrality, links, search | ✅ |
| Model card | `/model` | Analyst, admin | US-16 | Serving model, gate result, limitations | ✅ (limitations stale — D-12, being fixed) |
| Investigate | `/investigate` | Analyst, police | US-05, US-06 | Submission, agent trace, findings | 🟡 → workspace T-48, T-49 |
| Research dashboard | `/research/dashboard` | Researcher | US-17 | Dataset stats, evaluation | 🟡 |
| Admin dashboard | `/admin/dashboard` | Admin, owner | US-13, US-14 | Users, roles, tenants, audit | 🟡 audit viewer, retention T-55 |
| 🆕 Investigation workspace | `/investigations/{id}` | Analyst, police | US-05 – US-08 | Evidence viewer, agent-trace panel, verified findings with A7 verdicts, risk gauge, stage timeline, case-file viewer, export | 🆕 T-48 – T-50, T-52 |
| 🆕 Case queue | `/queue` | Police, analyst | US-11 | Sortable table, assignment, triage status | 🆕 T-51 |

---

## 11. Evaluation plan (research)

### 11.1 Principles

- **No claim without a measurement**, and no measurement on data the model was
  trained on. Since T-05 the promotion gate refuses to score a checkpoint whose
  training data overlaps the test split (exit 2).
- Every reported number is produced by a committed script into a committed
  results file under `research/results/`, reproducible byte for byte (T-06,
  T-56).
- Splits are built by a leak-free split builder with an overlap test (T-38),
  holding out whole **scam types**, not only call skeletons (B-07).

### 11.2 Datasets

| Dataset | Size today | Labels | Provenance |
|---|---|---|---|
| Synthetic scam-call corpus | **338 calls (209 scam, 129 benign), 1,617 utterances** after de-duplication (`ml/data/processed/report.md`) | 8 stages per utterance | Synthetic, generated by `ml/corpus/` |
| Knowledge corpus | 31 passages, 4 documents | — | Curated |
| Coach library | 14 lines | Human-reviewed | Curated |
| Fraud graph seed | 115 cases, 9 clusters | Synthetic | `intel/repository.py seed_cases()` |
| AIFC v1 (target) | ≥10,000 items, 12 categories + ≥3,500 benign (`DATASETS.md`) | Per item: `synthetic` / `public` / `consented` | T-37 |

`DATASETS.md` §2 gives the call corpus as "1,692 calls", which disagrees with
the generated report's 338 calls / 1,617 utterances; the report is generated
from the data and is used here. Recorded for T-37's data card.

### 11.3 Metrics

Precision, recall, F1 (macro and per class), AUROC, **expected calibration
error (ECE)** and reliability diagrams for every score shown to a user,
latency (p50/p95 per agent and end to end), LLM cost per investigation, and
**case-file completeness** (fraction of required fields populated and
verified, T-50). False-positive rate on benign evidence is reported
separately and gated (T-43).

### 11.4 Baselines

| Baseline | Status |
|---|---|
| Lexical stage classifier | ✅ measured |
| MuRIL fine-tuned stage classifier | ✅ measured — **fails the gate** |
| Fused (MuRIL max-fused with lexical) | Scored only once a valid comparison exists |
| SAGE-style tabular baseline | ⛔ blocked on audit Q5 (the paper has not been read); T-40 |
| Single-LLM baseline (one prompt, no agents) | 🆕 T-40 [ASSUMPTION — proposed, not yet agreed] |

**The first result (T-06), leak-free:** on the 112 test turns from archetypes
the served checkpoint never saw, lexical scores macro-F1 **0.431** against
MuRIL's **0.300**; on MuRIL's own original held-out split, 0.372 against
0.221. The 0.767 once published for MuRIL was a train/test leak — measured on
its own training data — and must not be cited.

### 11.5 Ablations (T-57)

Each is a parameter of the same harness, not a separate script:
1. Remove one modality at a time.
2. Remove A7 (findings pass unchallenged).
3. Remove fusion calibration (raw scores).
4. Lexical-only vs fused stage classifier.

### 11.6 Robustness (T-62)

Paraphrase, code-switching (English ↔ Hindi ↔ Hinglish), and prompt-injection
attacks embedded in evidence, with failures reported alongside successes.

---

## 12. Risks and mitigations

| ID | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R-01 | The research claim is overturned again by a leak | Medium | High | Gate refuses overlapping data (✅ T-05); split builder with overlap test (T-38); results reproducible (T-56) |
| R-02 | The trained model never beats the lexical baseline | High | High | Report it honestly; contribution rests on multimodality, A7 and calibration, not on one classifier; corpus work (T-45) before retraining |
| R-03 | Synthetic data does not reflect real scams | High | High | Every item labelled by provenance; benign set ≥ scam set; public examples where licensed; state the limitation in the paper |
| R-04 | False positives on legitimate bank or delivery messages | Medium | High | Benign tests per agent (✅); harness gating CI (T-43); metadata cannot reach CRITICAL alone (✅) |
| R-05 | Prompt injection through evidence text | Medium | High | Evidence is data, never instructions (invariant 8); injection tests (T-62) |
| R-06 | Live latency too high to intervene | Medium | Medium | Pruned real-time subgraph (T-53); measure before claiming |
| R-07 | Schedule: the plan is behind (D-11) | High | High | Critical path to a defensible review (`TASKS.md`); parked scope stays parked |
| R-08 | A deployed API runs open demo mode (S-01) or unguarded routes (S-07) | Medium | High | T-59 (permissions), T-66 (prove production mode) |
| R-09 | External dependency (LLM, store) unavailable during a review demo | Medium | Medium | Every dependency degrades explicitly; demo script has a fallback per step (T-67) |
| R-10 | The SAGE comparison cannot be made credibly | Medium | Medium | Read the paper before T-40; if a faithful baseline is impossible, say so |

---

## 13. Milestones

Review dates are **[ASSUMPTION]** placeholders until the owner supplies them.

| Milestone | Content | Exit criterion | College review |
|---|---|---|---|
| P1–P2 Documents | PRD (T-01), architecture (T-02), design system (T-03) | Approved by the owner | — |
| **M0 Stabilise** | T-04 – T-11 | Every published number leak-free; a fresh clone passes the gates and boots; the stack path re-verified | **Review-1 — [ASSUMPTION: date]** |
| **M1 Foundation** | T-12 – T-16 | A case ID follows a run through the logs; prompts are versioned; a frontend test runs in CI | |
| **M2 Core AI** | T-17 – T-46 | Message, screenshot, call recording and UPI ID each go through the graph; A7 can reject a finding; the score is calibrated and its ECE is on file | **Review-2 — [ASSUMPTION: date]** |
| **M3 Product** | T-47 – T-55 | One submission flow; a case queue; a case file exported; live intervention latency measured | |
| **M4 Quality** | T-56 – T-63 | Results file with baselines and ablations; security review closed; WCAG AA; e2e tests green | |
| **M5 Delivery** | T-64 – T-68 | Labelled demo data, a run guide, a deployed build, a review script, the paper draft | **Final — [ASSUMPTION: date]** |

**Critical path to a defensible Review-2:** T-17 – T-25, T-27, T-29, T-30,
T-37 – T-42, T-56, T-57.

---

## Appendix — assumptions to confirm

| # | Assumption | Where |
|---|---|---|
| A-1 | Team of four; names to be supplied | Header |
| A-2 | "Only a tiny fraction of complaints become FIRs" — needs a cited source before use | §1.2 |
| A-3 | SAGE (arXiv:2606.08146) is the base paper; not yet read | §1.5, §11.4 |
| A-4 | The six specialists are the roles A1–A6 | §6 |
| A-5 | A single-LLM baseline is wanted alongside SAGE | §11.4 |
| A-6 | Review-1, Review-2 and final dates | §13 |
