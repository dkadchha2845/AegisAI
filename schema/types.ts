/**
 * AegisAI — WebSocket contract, frontend view.
 *
 * Mirrors schema/models.py exactly. That file is the source of truth; this one
 * must be updated in the same commit whenever it changes. `npm run check:contract`
 * (schema/check_contract.py) fails the build if the enums drift apart.
 *
 * How the frontend is expected to consume this
 * --------------------------------------------
 * `StateFrame` is a complete, idempotent snapshot — render it directly. Do not
 * accumulate, diff, or derive from it. If the UI needs a number, that number is
 * a field here; if it isn't, add it to the contract rather than computing it in
 * React, or the same logic drifts apart in two languages.
 *
 * `Event` is a discrete edge — trigger animations from these. Never try to
 * detect "the threat just crossed 70" by comparing consecutive frames: frames
 * drop, repeat and arrive late, so the meter would shake twice or not at all.
 * The backend knows the truth and emits the edge.
 */

export const CONTRACT_VERSION = 1;

// ---------------------------------------------------------------------------
// Enums
// ---------------------------------------------------------------------------

export const STAGES = [
  "GREETING",
  "AUTHORITY_CLAIM",
  "FEAR_INDUCTION",
  "ISOLATION",
  "VERIFICATION_DEMAND",
  "PAYMENT_SETUP",
  "PAYMENT_EXECUTION",
  "BENIGN",
] as const;
export type Stage = (typeof STAGES)[number];

/** Bands, not raw score — the UI keys colour and motion off these so a score
 *  wobbling around 69/71 doesn't flicker the whole interface. */
export const THREAT_LEVELS = [
  "CALM",
  "WATCH",
  "ELEVATED",
  "HIGH",
  "CRITICAL",
] as const;
export type ThreatLevel = (typeof THREAT_LEVELS)[number];

export const VICTIM_STATES = [
  "UNKNOWN",
  "CALM",
  "CONFUSED",
  "ANXIOUS",
  "PANICKED",
  "COMPLIANT",
  "RESISTING",
] as const;
export type VictimState = (typeof VICTIM_STATES)[number];

export const PAYMENT_STATES = [
  "NONE",
  "PENDING",
  "HELD",
  "CANCELLED",
  "APPROVED",
] as const;
export type PaymentState = (typeof PAYMENT_STATES)[number];

export const GUARDIAN_STATES = [
  "IDLE",
  "ALERTING",
  "ACKNOWLEDGED",
  "CALLING",
] as const;
export type GuardianState = (typeof GUARDIAN_STATES)[number];

export const VERDICTS = ["PASS", "FAIL", "UNKNOWN"] as const;
export type Verdict = (typeof VERDICTS)[number];

export const EVENT_KINDS = [
  "THRESHOLD_CROSSED",
  "STAGE_CHANGED",
  "FORECAST_HIT",
  "GUARDIAN_ALERTED",
  "GUARDIAN_ACKNOWLEDGED",
  "PAYMENT_ATTEMPTED",
  "PAYMENT_HELD",
  "PAYMENT_CANCELLED",
  "COACH_URGENT",
  "CALL_ENDED",
] as const;
export type EventKind = (typeof EVENT_KINDS)[number];

export type Speaker = "CALLER" | "VICTIM";
export type Trend = "rising" | "falling" | "flat";
export type CoachUrgency = "info" | "warn" | "urgent";

// ---------------------------------------------------------------------------
// Sub-structures
// ---------------------------------------------------------------------------

export interface Utterance {
  id: string;
  speaker: Speaker;
  text: string;
  /** seconds from call start */
  t0: number;
  t1: number;
  stage: Stage;
  /** 0–1 */
  confidence: number;
  victim_state: VictimState;
}

export interface Transcript {
  final: Utterance[];
  /** In-flight ASR text, not yet classified. Render dimmed; never score it. */
  partial: string | null;
  partial_speaker: Speaker | null;
}

export interface StageState {
  current: Stage;
  confidence: number;
  since_s: number;
  /** Full distribution — lets the UI show runner-up stages. */
  distribution: Partial<Record<Stage, number>>;
}

export interface CoercionState {
  /** 0–100 */
  index: number;
  trend: Trend;
  /** recent values, for the sparkline */
  history: number[];
  features: Record<string, number>;
}

/** One named reason the threat score is what it is. */
export interface ThreatDriver {
  label: string;
  contribution: number;
  detail: string;
}

export interface ThreatState {
  /** 0–100 */
  score: number;
  level: ThreatLevel;
  drivers: ThreatDriver[];
}

/** Cumulative tactic pressure, 0–1 each. Bars fill over the call. */
export interface ManipulationMap {
  authority: number;
  fear: number;
  isolation: number;
  urgency: number;
  compliance: number;
}

/** The Digital Twin — beat 3, and the reason anyone remembers the demo. */
export interface Forecast {
  next_stage: Stage;
  /** 0–1 */
  probability: number;
  eta_s: number;
  /** The headline number: how long until money moves if nobody intervenes. */
  eta_to_payment_s: number | null;
  /** Set once the predicted stage actually occurs — lets the UI show "we called it". */
  last_prediction_correct: boolean | null;
}

export interface PassportCheck {
  name: string;
  verdict: Verdict;
  detail: string;
  /** RAG citation — which document backed this check. */
  source: string | null;
}

export interface TrustPassport {
  claimed_identity: string | null;
  /** 0–100 */
  final_trust_pct: number;
  checks: PassportCheck[];
}

/** Caller-number intelligence — the metadata half of a verdict.
 *
 *  Reuses `PassportCheck` rows so both render with one component. `risk` runs
 *  opposite to the passport's trust percentage — higher means more likely
 *  spoofed — because the number is evidence *against* a caller. */
export interface NumberIntel {
  number: string | null;
  /** 0–100, higher = more likely spoofed / fraudulent */
  risk: number;
  verdict: Verdict;
  checks: PassportCheck[];
}

/** Retrieved from a curated, safety-reviewed library — never generated at runtime. */
export interface CoachSuggestion {
  line: string;
  tactic: string;
  why: string;
  sources: string[];
  urgency: CoachUrgency;
}

/** Plain-language account of what the system is doing, and why.
 *
 *  A contract field rather than frontend copy, for the same reason every other
 *  number is one: the explanation has to agree with the score it is explaining.
 *  `sources` cites the knowledge-base sections behind the claim, so the panel
 *  is auditable rather than merely fluent. */
export interface Narration {
  headline: string;
  detail: string;
  sources: string[];
}

export interface GuardianInfo {
  state: GuardianState;
  name: string | null;
  alerted_at_s: number | null;
  acknowledged_at_s: number | null;
}

export interface PaymentInfo {
  state: PaymentState;
  amount_inr: number | null;
  payee: string | null;
  held_reason: string | null;
  held_at_s: number | null;
}

export interface CallInfo {
  status: "idle" | "active" | "ended";
  duration_s: number;
  caller_number: string | null;
  started_at: string | null;
}

// ---------------------------------------------------------------------------
// Messages
// ---------------------------------------------------------------------------

/** Complete call state. Idempotent — safe to drop, replay, or reorder. */
export interface StateFrame {
  v: number;
  type: "state";
  session_id: string;
  seq: number;
  /** seconds since call start */
  t: number;

  call: CallInfo;
  transcript: Transcript;
  stage: StageState | null;
  coercion: CoercionState | null;
  threat: ThreatState | null;
  manipulation_map: ManipulationMap;
  forecast: Forecast | null;
  trust_passport: TrustPassport | null;
  number_intel: NumberIntel | null;
  coach: CoachSuggestion | null;
  narration: Narration | null;
  guardian: GuardianInfo;
  payment: PaymentInfo;

  /** Degradation is explicit, never silent — e.g. ["asr:local_fallback"].
   *  Surface it rather than showing a confident number built on nothing. */
  degraded: string[];
}

/** A discrete edge. Animate off these. */
export interface AegisEvent {
  v: number;
  type: "event";
  session_id: string;
  seq: number;
  t: number;
  kind: EventKind;
  payload: Record<string, unknown>;
}

export interface ErrorMessage {
  v: number;
  type: "error";
  session_id: string | null;
  code: string;
  message: string;
  recoverable: boolean;
}

export type ServerMessage = StateFrame | AegisEvent | ErrorMessage;

// ---------------------------------------------------------------------------
// Client -> server
// ---------------------------------------------------------------------------

export type ClientAction =
  | "start_session"
  | "end_session"
  | "inject_text"
  | "guardian_ack"
  | "guardian_cancel_payment"
  | "guardian_approve_payment"
  | "attempt_payment"
  | "replay_demo";

export interface ClientCommand {
  v: number;
  type: "command";
  action: ClientAction;
  payload: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Narrowing helpers
// ---------------------------------------------------------------------------

export const isState = (m: ServerMessage): m is StateFrame => m.type === "state";
export const isEvent = (m: ServerMessage): m is AegisEvent => m.type === "event";
export const isError = (m: ServerMessage): m is ErrorMessage => m.type === "error";

/** Mirrors threat_level() in models.py. Exported for tests and the mock
 *  driver only — never call this to derive a level for display. The level
 *  arrives on the frame; recomputing it is how the two sides drift apart. */
export function threatLevelOf(score: number): ThreatLevel {
  if (score >= 90) return "CRITICAL";
  if (score >= 70) return "HIGH";
  if (score >= 50) return "ELEVATED";
  if (score >= 25) return "WATCH";
  return "CALM";
}

// ===========================================================================
// THE INVESTIGATION CONTRACT
// ===========================================================================
//
// Everything above is the live-call contract: a 4 Hz stream of idempotent
// `StateFrame` snapshots. Everything below is one evidence submission
// travelling through the agent graph (ARCHITECTURE.md §3) — a single object
// that accumulates agent results over seconds to minutes and is persisted.
//
// They share this file so they share a vocabulary. `InvestigationState` reuses
// `ThreatLevel`, `Transcript`, `Stage` and `Verdict` verbatim: the band a
// citizen sees during a live call and the band on their report have to mean
// the same thing, and they will not if each side owns its own thresholds.
//
// Versions are separate because they evolve separately — adding an
// investigation field must not invalidate a client that only speaks frames.

export const INVESTIGATION_CONTRACT_VERSION = 1;

// ---------------------------------------------------------------------------
// Investigation enums
// ---------------------------------------------------------------------------

/** What a piece of evidence *is*, decided by magic bytes first, extension
 *  second, content third — never by the uploader's MIME type. One item may
 *  carry several types; ambiguity is expressed by returning more than one,
 *  never by guessing. UNKNOWN routes to the text agent. */
export const INPUT_TYPES = [
  "TEXT",
  "SMS",
  "EMAIL",
  "IMAGE",
  "SCREENSHOT",
  "PDF",
  "DOCUMENT",
  "URL",
  "APK",
  "AUDIO",
  "VIDEO",
  "QR",
  "PHONE",
  "UPI_ID",
  "UNKNOWN",
] as const;
export type InputType = (typeof INPUT_TYPES)[number];

/** DEGRADED means the agent answered from a fallback — usable, and visibly
 *  short of full capability. SKIPPED means it did not apply, and must never be
 *  rendered (or scored) as "clean". */
export const AGENT_STATUSES = ["ok", "degraded", "skipped", "error"] as const;
export type AgentStatus = (typeof AGENT_STATUSES)[number];

export const INVESTIGATION_STATUSES = [
  "QUEUED",
  "RUNNING",
  "COMPLETE",
  "FAILED",
  "CANCELLED",
] as const;
export type InvestigationStatus = (typeof INVESTIGATION_STATUSES)[number];

/** The twelve categories of DATASETS.md §3, plus the hard negative. Slugs match
 *  the dataset's `category` field exactly. There is no UNKNOWN: `null` means
 *  "not classified yet", `"benign"` means "classified, and legitimate". */
export const FRAUD_CATEGORIES = [
  "digital_arrest",
  "banking_impersonation",
  "upi_payment_fraud",
  "phishing",
  "otp_harvesting",
  "courier_customs",
  "job_task_scam",
  "investment_trading",
  "loan_app",
  "support_impersonation",
  "remote_access",
  "lottery_reward",
  "benign",
] as const;
export type FraudCategory = (typeof FRAUD_CATEGORIES)[number];

/** One ordered scale shared by findings and recommendations, so the report can
 *  rank them in a single column without the UI reconciling two scales. */
export const SEVERITIES = ["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"] as const;
export type Severity = (typeof SEVERITIES)[number];

/** A closed vocabulary of advice. Closed for the same reason coach lines are
 *  retrieved rather than generated: what we tell a frightened person to do is a
 *  safety surface. `detail` carries the specifics; nothing else is free text.
 *
 *  The membership is the vocabulary the backend already ships — every line
 *  `engine/analyzer.py::_actions()` produces maps onto a member here, and a
 *  test fails if one stops doing so. The UI is expected to give each member an
 *  icon and a Hindi string; that is why it is an enum and not a sentence. */
export const RECOMMENDED_ACTIONS = [
  "DO_NOT_PAY",
  "DO_NOT_SHARE_OTP",
  "DO_NOT_OPEN_LINK",
  "DO_NOT_INSTALL_APP",
  "DO_NOT_ACT_YET",
  "END_THE_CALL",
  "VERIFY_VIA_OFFICIAL_CHANNEL",
  "CONTACT_YOUR_BANK",
  "BLOCK_AND_REPORT_NUMBER",
  "REPORT_TO_CYBERCRIME",
  "PRESERVE_EVIDENCE",
  "SEEK_HELP_FROM_TRUSTED_PERSON",
  "PROVIDE_MORE_EVIDENCE",
  "NO_ACTION_NEEDED",
] as const;
export type RecommendedAction = (typeof RECOMMENDED_ACTIONS)[number];

export type InvestigationMode = "batch" | "realtime";

// ---------------------------------------------------------------------------
// Investigation sub-structures
// ---------------------------------------------------------------------------

/** One submitted artefact — never the bytes. `uri` points at object storage;
 *  `text` inlines only genuinely small textual payloads.
 *
 *  `declared_type` is what the uploader claimed; `media_type` is what the magic
 *  bytes say. Both are kept because their disagreement is itself a finding — an
 *  APK renamed `.jpg` can only be flagged if we wrote down the lie. */
export interface EvidenceItem {
  id: string;
  kind: InputType;
  filename: string | null;
  /** user-supplied MIME — recorded, never trusted for routing */
  declared_type: string | null;
  /** type detected from magic bytes */
  media_type: string | null;
  size_bytes: number | null;
  sha256: string | null;
  /** object-store reference */
  uri: string | null;
  /** inline payload for small textual evidence only */
  text: string | null;
  /** ISO-8601 UTC */
  received_at: string | null;
}

/** Text recovered from one evidence item, and how. OCR at 0.62 and a verbatim
 *  paste at 1.0 are different evidence; the report has to say which it stands
 *  on. `source_ref` is an `EvidenceItem.id`. */
export interface ExtractedText {
  source_ref: string;
  text: string;
  /** "en" | "hi" | "hi-Latn" (Hinglish) | null if undetected */
  language: string | null;
  confidence: number;
  /** "verbatim" | "ocr:paddle" | "asr:faster-whisper" | ... */
  extractor: string;
}

/** Every identifier found, flat and deduplicated. Field names match
 *  `services/api/intel/entities.ExtractedEntities` exactly — the graph keys
 *  nodes off these names.
 *
 *  The first ten are *linkable*: two cases sharing one are two cases connected.
 *  `banks`, `locations` and `scam_keywords` are display context and must never
 *  become edges — two cases naming "SBI" are not thereby related. */
export interface EntitySet {
  phones: string[];
  upi_ids: string[];
  emails: string[];
  wallets: string[];
  bank_accounts: string[];
  domains: string[];
  urls: string[];
  ips: string[];
  /** package names or app names named in evidence */
  apps: string[];
  orgs: string[];

  amounts: number[];
  /** institutions the sender claims to be */
  authorities: string[];
  // --- display context only; never graph edges ---
  banks: string[];
  locations: string[];
  scam_keywords: string[];
}

/** One thing an agent observed — machine-facing and cheap. Distinct from
 *  `EvidenceFinding`, the ranked citizen-facing item promoted into a report. */
export interface Finding {
  /** stable machine key, e.g. "domain_age_days" */
  label: string;
  value: string | null;
  confidence: number;
  /** what produced it: "whois", "urlhaus", "muril:v3" */
  source: string;
  detail: string | null;
}

/** The single shape every agent returns.
 *
 *  Uniformity is the point: the orchestrator fans out without knowing what any
 *  agent does, this panel renders generically, and the paper computes per-agent
 *  success rates without a per-agent adapter. */
export interface AgentResult {
  /** registry name, e.g. "url_investigation" */
  agent: string;
  /** pinned for reproducibility, e.g. "1.3.0" */
  version: string;
  status: AgentStatus;
  confidence: number;
  findings: Finding[];
  /** this agent's contribution to the ML feature vector */
  features: Record<string, number>;
  latency_ms: number;
  /** data sources actually consulted */
  provenance: string[];
  error: string | null;
}

/** One threat-intelligence observation with its paperwork attached.
 *
 *  `malicious` is three-valued on purpose: a feed that is unreachable yields
 *  `null` and a `degraded` tag, never `false`. Inventing an intelligence hit is
 *  the most damaging thing this system could do, so "we do not know" has to be
 *  representable. */
export interface TIRecord {
  indicator: string;
  /** "url" | "domain" | "ip" | "upi" | "phone" */
  indicator_type: string;
  /** feed name, e.g. "urlhaus" */
  source: string;
  /** null = the feed could not answer; never a guess */
  malicious: boolean | null;
  confidence: number;
  /** ISO-8601 UTC — when the feed saw it */
  observed_at: string | null;
  /** ISO-8601 UTC — when we read it */
  retrieved_at: string | null;
  /** resolvable link to the record */
  reference: string | null;
  cached: boolean;
}

export interface GraphNeighbour {
  /** graph node id, e.g. "upi:fraud@paytm" */
  key: string;
  /** "phone" | "upi" | "email" | "domain" | ... */
  kind: string;
  value: string;
  /** how it connects, e.g. "SHARED_UPI" */
  relation: string;
  shared_cases: number;
}

/** What the graph already knew — the evidence no single artefact can carry.
 *
 *  `backend` records whether Neo4j or the NetworkX fallback answered: the
 *  fallback covers less data, and the report must not present the two as
 *  interchangeable. */
export interface GraphContext {
  prior_observations: number;
  prior_case_ids: string[];
  neighbours: GraphNeighbour[];
  cluster_id: string | null;
  cluster_risk: number | null;
  centrality: number | null;
  /** ISO-8601 UTC */
  first_seen: string | null;
  /** ISO-8601 UTC */
  last_seen: string | null;
  /** "neo4j" | "networkx" */
  backend: string;
}

/** One retrieved passage. `citation` must resolve to a real chunk — the failure
 *  mode here is not a bad answer but a confident one citing a circular that
 *  does not exist. */
export interface RetrievedChunk {
  chunk_id: string;
  text: string;
  /** document identifier */
  source: string;
  /** human-resolvable reference */
  citation: string;
  score: number;
  /** "dense" | "bm25" | "hybrid" */
  retriever: string;
}

/** One ranked, human-readable item in the report.
 *
 *  `id` exists so generated prose can be held to it: every sentence must name
 *  the finding it rests on. Prose that cannot point at an id is a hallucination
 *  by definition. `contribution` is the SHAP value once it is measured, and
 *  stays null until then rather than being faked with a heuristic weight. */
export interface EvidenceFinding {
  id: string;
  title: string;
  detail: string;
  severity: Severity;
  confidence: number;
  /** SHAP contribution to the risk score, once measured */
  contribution: number | null;
  agent: string | null;
  sources: string[];
}

export interface Recommendation {
  action: RecommendedAction;
  detail: string;
  urgency: Severity;
  sources: string[];
}

/** One node execution — debug tool, this panel, and the paper's latency table.
 *
 *  `parent_span_id` and `depth` carry the fan-out shape; without them a
 *  recursive sub-investigation flattens into an unreadable list. `attempt`
 *  records retries, because a node that succeeded on its second try is not the
 *  same as one that succeeded first time. */
export interface TraceSpan {
  span_id: string;
  /** graph node name */
  node: string;
  agent: string | null;
  version: string | null;
  /** seconds since investigation start */
  t_start: number;
  t_end: number;
  latency_ms: number;
  status: AgentStatus;
  attempt: number;
  depth: number;
  parent_span_id: string | null;
  error: string | null;
}

// ---------------------------------------------------------------------------
// The investigation itself
// ---------------------------------------------------------------------------

/** The shared contract every agent reads and writes (ARCHITECTURE.md §3).
 *
 *  Append-only in spirit: agents add to `agent_results`, `trace` and `degraded`
 *  rather than overwriting each other, which is what makes a parallel fan-out
 *  safe to merge and a crashed investigation safe to resume.
 *
 *  `risk_score`, `risk_level` and `confidence` start null. An unscored
 *  investigation must not render as 0/CALM — that is a false negative wearing a
 *  number. Render null as "not yet", never as "safe".
 *
 *  `risk_level` is a field, not something derived here from `risk_score`: the
 *  live path and the report path must band a 69.6 identically, and they will
 *  not if the threshold lives in React. */
export interface InvestigationState {
  v: number;
  type: "investigation";

  // --- identity ---
  case_id: string;
  org_id: string;
  created_by: string;
  /** ISO-8601 UTC */
  created_at: string;
  mode: InvestigationMode;
  status: InvestigationStatus;
  /** ISO-8601 UTC */
  completed_at: string | null;

  // --- input ---
  inputs: EvidenceItem[];
  input_types: InputType[];

  // --- extraction ---
  extracted_text: ExtractedText[];
  entities: EntitySet;
  transcript: Transcript | null;

  // --- investigation ---
  agent_results: AgentResult[];
  threat_intel: TIRecord[];
  graph_context: GraphContext | null;
  rag_context: RetrievedChunk[];

  // --- judgement ---
  /** the ML model's exact input vector */
  risk_features: Record<string, number>;
  risk_score: number | null;
  risk_level: ThreatLevel | null;
  confidence: number | null;
  classification: FraudCategory | null;
  evidence: EvidenceFinding[];
  recommendations: Recommendation[];

  // --- operational ---
  degraded: string[];
  trace: TraceSpan[];
}

// ---------------------------------------------------------------------------
// The lifecycle stream
// ---------------------------------------------------------------------------

/** The five things the lifecycle API says while a case runs.
 *
 *  Deliberately not a mirror of `EVENT_KINDS`, which belongs to the live-call
 *  contract and names things that happen inside a scam. These name things that
 *  happen to an *investigation*.
 *
 *  There is no `node_started`: the graph reports completions, so a "started"
 *  event would be inferred from the plan rather than observed — a fake timer
 *  wearing a node name. The client gets the whole plan on `accepted` and
 *  renders "3 of 7" from two facts it was actually told. */
export const INVESTIGATION_EVENT_KINDS = [
  "accepted",
  "node_complete",
  "complete",
  "failed",
  "cancelled",
] as const;
export type InvestigationEventKind = (typeof INVESTIGATION_EVENT_KINDS)[number];

/** One server-sent event on `GET /api/investigations/{id}/stream`.
 *
 *  `seq` is the SSE `id:` field, monotonic from 1 within a run. A client that
 *  saw event 4 reconnects with `Last-Event-ID: 4` and is replayed 5 onward, so
 *  nothing arrives twice and nothing is skipped. Keepalives are SSE comment
 *  lines, which carry no id and therefore cannot be duplicated.
 *
 *  `agent_results` and `degraded` are the *delta* for this node, not the
 *  accumulated lists. Appending every event reconstructs the state's own lists
 *  exactly, and a mid-run reconnect does not double-count earlier tiers. */
export interface InvestigationEvent {
  v: number;
  type: "investigation_event";

  /** monotonic within one run; the SSE event id */
  seq: number;
  case_id: string;
  kind: InvestigationEventKind;
  /** ISO-8601 UTC */
  at: string;
  status: InvestigationStatus;

  /** graph node that just completed */
  node: string | null;
  /** every node this run will execute, in order — sent on `accepted` */
  plan: string[];
  nodes_done: number;

  /** results produced by this node only */
  agent_results: AgentResult[];
  /** tags added by this node only */
  degraded: string[];
  error: string | null;
}
