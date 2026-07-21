// GENERATED — do not edit. Source: schema/types.ts
// Regenerate: ./scripts/sync-contract.sh
/**
 * PRESAGE — WebSocket contract, frontend view.
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
export interface PresageEvent {
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

export type ServerMessage = StateFrame | PresageEvent | ErrorMessage;

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
export const isEvent = (m: ServerMessage): m is PresageEvent => m.type === "event";
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
