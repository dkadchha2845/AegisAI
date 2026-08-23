/**
 * Typed client for the AegisAI API.
 *
 * One place that knows the base URL, one place that knows how the server
 * reports failure. Every call returns a discriminated result rather than
 * throwing, because every screen in this app has to keep working when the
 * backend is down — the demo has a recorded stream to fall back on, and a
 * component that crashes on a rejected promise cannot fall back to anything.
 */

import type { StateFrame } from "@/types/contract";

export const API_BASE =
  (import.meta.env.VITE_API_BASE as string | undefined) ?? "http://localhost:8000";

export type ApiResult<T> =
  | { ok: true; data: T }
  | { ok: false; error: string; status?: number };

// --- session token ---------------------------------------------------------
// Persisted so a reload keeps you signed in. Auth is off by default on the
// server (open mode), so an absent token is the normal case, not an error.
const TOKEN_KEY = "aegis.token";
export const getToken = (): string | null => localStorage.getItem(TOKEN_KEY);
export const setToken = (token: string | null): void => {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
};

async function request<T>(path: string, init?: RequestInit): Promise<ApiResult<T>> {
  try {
    const token = getToken();
    const authHeader: Record<string, string> = token
      ? { Authorization: `Bearer ${token}` }
      : {};
    const res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers:
        init?.body instanceof FormData
          ? { ...authHeader, ...(init?.headers ?? {}) }
          : { "content-type": "application/json", ...authHeader, ...(init?.headers ?? {}) },
    });
    if (!res.ok) {
      // FastAPI puts the useful message in `detail`. Surfacing it beats
      // "Request failed" — a 415 that says which formats are accepted is
      // the difference between a user retrying correctly and giving up.
      let message = `${res.status} ${res.statusText}`;
      try {
        const body = await res.json();
        if (typeof body?.detail === "string") message = body.detail;
      } catch {
        /* non-JSON error body; the status line is all we have */
      }
      return { ok: false, error: message, status: res.status };
    }
    return { ok: true, data: (await res.json()) as T };
  } catch {
    return {
      ok: false,
      error:
        "Cannot reach the analysis service. Start it with `.venv/bin/uvicorn services.api.main:app --port 8000`.",
    };
  }
}

// ---------------------------------------------------------------------------
// Analyzer
// ---------------------------------------------------------------------------

export interface Finding {
  label: string;
  weight: number;
  detail: string;
  verdict: "FAIL" | "PASS" | "UNKNOWN";
  source: string | null;
}

export interface LabelledLine {
  index: number;
  speaker: string;
  text: string;
  stage: string;
  confidence: number;
  distribution: Record<string, number>;
}

export type Verdict =
  | "LIKELY_SCAM"
  | "SUSPICIOUS"
  | "LIKELY_LEGITIMATE"
  | "INSUFFICIENT";

export interface UpiAnalysis {
  vpa: string | null;
  handle: string | null;
  local_part: string | null;
  valid_format: boolean;
  payee_name: string | null;
  amount: number | null;
  findings: Finding[];
}

export interface AnalysisResult {
  kind: string;
  score: number;
  level: string;
  verdict: Verdict;
  summary: string;
  explanation?: string;
  explanation_source?: string;
  lines: LabelledLine[];
  drivers: { label: string; contribution: number; detail: string }[];
  findings: Finding[];
  manipulation_map: Record<string, number>;
  stages_seen: string[];
  trust_passport: {
    claimed_identity: string | null;
    final_trust_pct: number;
    checks: { name: string; verdict: string; detail: string; source: string | null }[];
  } | null;
  coach: {
    line: string;
    tactic: string;
    why: string;
    sources: string[];
    urgency: string;
  } | null;
  citations: string[];
  recommended_actions: string[];
  degraded: string[];
  upi: UpiAnalysis | null;
  filename?: string;
  /** Present when the input was an image: which engine read it, the extracted
   *  text, and any decoded QR payloads. */
  ocr?: { engine: string; text: string; qr_payloads: string[] };
}

export const analyzeText = (
  text: string,
  opts: { kind?: string; claimedIdentity?: string | null; explain?: boolean } = {},
) =>
  request<AnalysisResult>("/api/analyze/text", {
    method: "POST",
    body: JSON.stringify({
      text,
      kind: opts.kind ?? "text",
      claimed_identity: opts.claimedIdentity ?? null,
      explain: opts.explain ?? false,
    }),
  });

export const analyzeUpi = (upiId: string, claimedIdentity?: string | null) =>
  request<AnalysisResult>("/api/analyze/upi", {
    method: "POST",
    body: JSON.stringify({ upi_id: upiId, claimed_identity: claimedIdentity ?? null }),
  });

export const analyzeFile = (file: File) => {
  const form = new FormData();
  form.append("file", file);
  return request<AnalysisResult>("/api/analyze/file", { method: "POST", body: form });
};

/** Transcribe an audio recording (voice note, call recording) and score the
 *  transcript. Degrades honestly if no speech-to-text backend is installed. */
export const analyzeAudio = (
  file: File,
  opts: { claimedIdentity?: string | null; callerNumber?: string | null } = {},
) => {
  const form = new FormData();
  form.append("file", file);
  const qs = new URLSearchParams();
  if (opts.claimedIdentity) qs.set("claimed_identity", opts.claimedIdentity);
  if (opts.callerNumber) qs.set("caller_number", opts.callerNumber);
  const q = qs.toString();
  return request<AnalysisResult & { asr?: { backend: string; ok: boolean; text: string; reason: string | null } }>(
    `/api/analyze/audio${q ? `?${q}` : ""}`,
    { method: "POST", body: form },
  );
};

/** OCR a screenshot (fake notice, payment screenshot, QR) and score the text. */
export const analyzeImage = (
  file: File,
  opts: { claimedIdentity?: string | null; callerNumber?: string | null } = {},
) => {
  const form = new FormData();
  form.append("file", file);
  const qs = new URLSearchParams();
  if (opts.claimedIdentity) qs.set("claimed_identity", opts.claimedIdentity);
  if (opts.callerNumber) qs.set("caller_number", opts.callerNumber);
  const q = qs.toString();
  return request<AnalysisResult>(`/api/analyze/image${q ? `?${q}` : ""}`, {
    method: "POST",
    body: form,
  });
};

// ---------------------------------------------------------------------------
// Knowledge base
// ---------------------------------------------------------------------------

export interface KnowledgeHit {
  source: string;
  text: string;
  score: number;
  tags: string[];
  doc: string;
}

export const searchKnowledge = (q: string, k = 6) =>
  request<{ backend: string; degraded: string[]; results: KnowledgeHit[] }>(
    `/api/analyze/knowledge/search?q=${encodeURIComponent(q)}&k=${k}`,
  );

export const listDocuments = () =>
  request<{
    documents: { name: string; sections: { source: string; text: string; tags: string[] }[] }[];
  }>("/api/analyze/knowledge/docs");

// ---------------------------------------------------------------------------
// Health & model card
// ---------------------------------------------------------------------------

export interface Health {
  ok: boolean;
  contract_version: number;
  classifier: {
    backend: string;
    checkpoint: string;
    loaded: boolean;
    /** True when the active model is the best available (fine-tuned, or lexical
     *  because it won the measured comparison). False only for a real fallback. */
    serving_best: boolean;
    reason: string;
  };
  retrieval: { backend: string; chunks: number; documents: string[] };
  twin: { fitted: boolean; stages: string[]; support: Record<string, number> };
  coach: { lines: number };
  llm: { backend: string; model: string | null; configured: boolean };
  database?: { backend: string; persistent: boolean; url_configured: boolean };
  degraded: string[];
}

export const getHealth = () => request<Health>("/api/health");

// ---------------------------------------------------------------------------
// Knowledge assistant (retrieval-grounded Q&A)
// ---------------------------------------------------------------------------

export interface KnowledgeCitation {
  source: string;
  text: string;
  doc: string;
  score: number;
}

export interface KnowledgeAnswer {
  question: string;
  /** Prose answer when an LLM is configured; null => show the passages only. */
  answer: string | null;
  answer_source: string;
  grounded: boolean;
  retrieval_backend: string;
  llm_configured: boolean;
  citations: KnowledgeCitation[];
  degraded: string[];
}

export const askKnowledge = (question: string, k = 5) =>
  request<KnowledgeAnswer>("/api/analyze/knowledge/ask", {
    method: "POST",
    body: JSON.stringify({ question, k }),
  });

export interface BackendScore {
  macro_f1: number;
  weighted_f1: number;
}

export interface ModelCard {
  name: string;
  task: string;
  base_model: string;
  active_backend: string;
  training_data: Record<string, string>;
  /** Both backends scored on the same held-out archetypes. Empty until
   *  ml/eval_backends.py has been run. */
  evaluation?: {
    protocol: string;
    scores: Record<string, BackendScore>;
    selection: string;
  };
  limitations: string[];
  twin: Record<string, unknown>;
}

export const getModelCard = () => request<ModelCard>("/api/model/card");

// ---------------------------------------------------------------------------
// Live session
// ---------------------------------------------------------------------------

export interface SessionActionResult {
  frame: StateFrame;
  events: { kind: string; payload: Record<string, unknown>; t: number }[];
  outcome?: { state: string; reason: string | null };
}

export const startSession = (callerNumber?: string, guardianName?: string) =>
  request<StateFrame>("/api/session", {
    method: "POST",
    body: JSON.stringify({
      caller_number: callerNumber ?? null,
      guardian_name: guardianName ?? null,
    }),
  });

export const injectUtterance = (
  sessionId: string,
  text: string,
  speaker: "CALLER" | "VICTIM" = "CALLER",
  partial = false,
) =>
  request<SessionActionResult>(`/api/session/${sessionId}/utterance`, {
    method: "POST",
    body: JSON.stringify({ text, speaker, partial }),
  });

export const guardianAck = (sessionId: string, name?: string) =>
  request<SessionActionResult>(
    `/api/session/${sessionId}/guardian/ack${name ? `?name=${encodeURIComponent(name)}` : ""}`,
    { method: "POST" },
  );

export const attemptPayment = (sessionId: string, amount: number, payee?: string) =>
  request<SessionActionResult>(`/api/session/${sessionId}/payment/attempt`, {
    method: "POST",
    body: JSON.stringify({ amount_inr: amount, payee: payee ?? null }),
  });

export const cancelPayment = (sessionId: string) =>
  request<SessionActionResult>(`/api/session/${sessionId}/payment/cancel`, {
    method: "POST",
  });

export const approvePayment = (sessionId: string) =>
  request<SessionActionResult>(`/api/session/${sessionId}/payment/approve`, {
    method: "POST",
  });

export const endSession = (sessionId: string) =>
  request<SessionActionResult>(`/api/session/${sessionId}`, { method: "DELETE" });

/** Turn a live call into the same fused VerifyResult the Analyze page shows —
 *  Module 1 + 2 + 3 — so both journeys end in the identical investigation report. */
export const investigateSession = (sessionId: string, city?: string | null) =>
  request<VerifyResult>(
    `/api/session/${sessionId}/investigate${city ? `?city=${encodeURIComponent(city)}` : ""}`,
    { method: "POST" },
  );

export const socketUrl = (sessionId: string) =>
  `${API_BASE.replace(/^http/, "ws")}/api/session/ws/${sessionId}`;

// ---------------------------------------------------------------------------
// Evidence package (escalation artifact)
// ---------------------------------------------------------------------------

/** URL of the structured JSON evidence package. */
export const reportUrl = (sessionId: string) =>
  `${API_BASE}/api/session/${sessionId}/report`;

/** URL of the court-admissible PDF. The server sets Content-Disposition, so
 *  navigating here downloads the file. */
export const reportPdfUrl = (sessionId: string) =>
  `${API_BASE}/api/session/${sessionId}/report.pdf`;

export interface EvidencePackage {
  report_id: string;
  generated_at: string;
  incident: { type: string; peak_threat: number; final_level: string; peak_stage: string };
  call: { session_id: string; caller_number: string | null; duration_s: number };
  assessment: {
    claimed_identity: string | null;
    identity_trust_pct: number | null;
    caller_number_risk: number | null;
    caller_number_verdict: string | null;
  };
  evidence: { category: string; finding: string; detail: string; source: string | null }[];
  citations: string[];
  reporting_guidance: string[];
}

export const getReport = (sessionId: string) =>
  request<EvidencePackage>(`/api/session/${sessionId}/report`);

// ---------------------------------------------------------------------------
// Auth, users, case book & audit (Track 2 platform)
// ---------------------------------------------------------------------------

export interface AuthUser {
  id: number;
  email: string;
  role: "viewer" | "analyst" | "admin" | "owner";
  org_id: number | null;
  disabled: boolean;
  created_at: string | null;
}

export interface Organization {
  id: number;
  slug: string;
  name: string;
  created_at: string | null;
  members?: number;
  cases?: number;
}

export interface MeResponse {
  user: AuthUser;
  org: Organization | null;
  auth_enforced: boolean;
}

export const login = (email: string, password: string) =>
  request<{ token: string; user: AuthUser }>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });

export const getMe = () => request<MeResponse>("/api/auth/me");

export const listUsers = () => request<{ users: AuthUser[] }>("/api/auth/users");

export const createUser = (email: string, password: string, role: string, orgId?: number) =>
  request<{ user: AuthUser }>("/api/auth/users", {
    method: "POST",
    body: JSON.stringify({ email, password, role, org_id: orgId ?? null }),
  });

export const listOrgs = () =>
  request<{ organizations: Organization[] }>("/api/orgs");

export const createOrg = (name: string) =>
  request<{ organization: Organization }>("/api/orgs", {
    method: "POST",
    body: JSON.stringify({ name }),
  });

export const getCurrentOrg = () =>
  request<{ organization: Organization | null; is_owner: boolean }>("/api/orgs/current");

export interface CaseSummary {
  report_id: string;
  session_id: string;
  created_at: string | null;
  created_by: string | null;
  caller_number: string | null;
  incident_type: string | null;
  peak_threat: number | null;
  final_level: string | null;
}

export const listReports = () => request<{ reports: CaseSummary[] }>("/api/reports");

export const getSavedReport = (reportId: string) =>
  request<{ record: CaseSummary; package: EvidencePackage }>(`/api/reports/${reportId}`);

export const saveReport = (sessionId: string) =>
  request<{ record: CaseSummary; package: EvidencePackage }>(
    `/api/session/${sessionId}/report/save`,
    { method: "POST" },
  );

export interface AuditEvent {
  id: number;
  ts: string | null;
  actor: string | null;
  action: string;
  target: string | null;
  detail: string | null;
}

export const getAudit = (action?: string) =>
  request<{ events: AuditEvent[] }>(`/api/audit${action ? `?action=${action}` : ""}`);

// ---------------------------------------------------------------------------
// Module 2 — FIGAE (fraud intelligence & geospatial)
// ---------------------------------------------------------------------------

export interface IntelStats {
  total_cases: number;
  module1_cases: number;
  active_clusters: number;
  campaigns: number;
  high_risk_clusters: number;
  linked_entities: number;
  total_loss_inr: number;
  graph_nodes: number;
  graph_edges: number;
}

export interface Cluster {
  cluster_id: string;
  size: number;
  primary_scam: string;
  primary_scam_name: string;
  shared_phones: string[];
  shared_upi_ids: string[];
  shared_wallets: string[];
  states: string[];
  total_loss_inr: number;
  peak_threat: number;
  mean_threat: number;
  risk: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  risk_score: number;
  case_ids: string[];
  is_campaign: boolean;
}

export interface GraphNode {
  id: string;
  kind: string;
  label: string;
  cases: number | null;
  threat: number | null;
  cluster?: string | null;
}

export interface GraphEdge {
  source: string;
  target: string;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  truncated?: boolean;
  cluster_id?: string;
}

export interface Hotspot {
  name: string;
  level: string;
  cases: number;
  total_loss_inr: number;
  lat: number;
  lon: number;
  risk: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  top_scam: string | null;
}

/** One fraud case placed on the map — the granular layer under the hotspots.
 *  Dated and typed, so the interactive map can cluster and filter by scam type
 *  and by date. */
export interface ScamPoint {
  id: string;
  lat: number;
  lon: number;
  city: string | null;
  state: string | null;
  scam_type: string;
  scam_name: string;
  risk: "CALM" | "WATCH" | "ELEVATED" | "HIGH" | "CRITICAL" | string;
  amount_inr: number;
  reported_at: string;
}

export interface RiskFactor {
  factor: string;
  contribution: number;
  detail: string;
}

export interface InvestigationReport {
  cluster_id: string;
  generated_at: string;
  summary: {
    linked_cases: number;
    primary_scam: string;
    shared_phone_numbers: number;
    shared_upi_ids: number;
    shared_wallets: number;
    affected_states: string[];
    total_loss_inr: number;
    risk_level: string;
    risk_score: number;
    is_campaign: boolean;
  };
  evidence: {
    shared_phones: string[];
    shared_upi_ids: string[];
    shared_wallets: string[];
    case_ids: string[];
  };
  risk_factors: RiskFactor[];
  narrative: string;
  narrative_llm?: string;
  suggested_actions: string[];
  disclaimer: string;
}

export interface LinkPrediction {
  source: string;
  target: string;
  via: string[];
  confidence: number;
  relation: string;
}

export interface CentralityEntity {
  id: string;
  kind: string;
  value: string;
  cases: number;
  cluster: string | null;
}

export const getIntelStats = () => request<IntelStats>("/api/intel/stats");
export const getClusters = () => request<{ clusters: Cluster[] }>("/api/intel/clusters");
export const getClusterDetail = (id: string) =>
  request<{ cluster: Cluster; graph: GraphData; report: InvestigationReport }>(
    `/api/intel/clusters/${id}`,
  );
export const getPoints = () =>
  request<{ points: ScamPoint[]; scam_types: { id: string; name: string }[] }>(
    "/api/intel/points",
  );
export const getGeo = () =>
  request<{ states: Hotspot[]; districts: Hotspot[]; cities: Hotspot[] }>("/api/intel/geo");
export const getCentrality = () =>
  request<{ entities: CentralityEntity[] }>("/api/intel/centrality");
export const getLinkPredictions = () =>
  request<{ predictions: LinkPrediction[] }>("/api/intel/links");
export const getFullGraph = (limit = 300) =>
  request<GraphData>(`/api/intel/graph?limit=${limit}`);
export const searchIntel = (q: string) =>
  request<{
    query: string;
    kind?: string;
    matches: {
      kind: string;
      value: string;
      cases: string[];
      case_count: number;
      clusters: string[];
    }[];
  }>(`/api/intel/search?q=${encodeURIComponent(q)}`);

// ---------------------------------------------------------------------------
// Module 3 — CFSRP (citizen fraud shield)
// ---------------------------------------------------------------------------

export interface Helpline {
  name: string;
  value: string;
  action: string;
  detail: string;
  priority: string;
}

export interface Guidance {
  stage: string;
  threat_level: string;
  headline: string;
  actions: string[];
  coach_line: string | null;
  coach_why: string | null;
  sources: string[];
}

export interface EmergencyResponse {
  severity: "info" | "warn" | "urgent";
  title: string;
  checklist: string[];
  helplines: Helpline[];
  show_panic_banner: boolean;
}

export interface VerifyResult {
  verdict: Verdict;
  level: string;
  score: number;
  stage: string;
  summary: string;
  analysis: AnalysisResult;
  intel: {
    known_infrastructure: boolean;
    matched_entities: { kind: string; value: string; case_count: number }[];
    clusters: {
      cluster_id: string;
      primary_scam: string;
      size: number;
      risk: string;
      states: string[];
    }[];
  };
  guidance: Guidance;
  emergency: EmergencyResponse;
  nearby_hotspots: Hotspot[];
  /** Everything AegisAI pulled out of the evidence itself, so the citizen never
   *  has to type a number/UPI/email the message already contained. */
  extracted_entities?: ExtractedEntities;
  degraded: string[];
}

export interface ExtractedEntities {
  phones: string[];
  upi_ids: string[];
  emails: string[];
  websites: string[];
  bank_accounts?: string[];
  banks?: string[];
  authorities: string[];
  locations?: string[];
  scam_keywords?: string[];
  amounts: string[];
}

export interface VerifyRequestBody {
  text?: string;
  number?: string | null;
  upi?: string | null;
  claimed_identity?: string | null;
  city?: string | null;
  channel?: string;
}

export const getHelplines = () => request<{ helplines: Helpline[] }>("/api/shield/helplines");

export const shieldVerify = (body: VerifyRequestBody) =>
  request<VerifyResult>("/api/shield/verify", {
    method: "POST",
    body: JSON.stringify(body),
  });

export const shieldPreserve = (body: VerifyRequestBody) =>
  request<{ token: string; summary: Record<string, unknown>; result: VerifyResult }>(
    "/api/shield/preserve",
    { method: "POST", body: JSON.stringify(body) },
  );

export const getVault = (token: string) =>
  request<{ summary: Record<string, unknown>; result: VerifyResult; submitted_text: string }>(
    `/api/shield/vault/${token}`,
  );

export const complaintPdfUrl = (token: string) =>
  `${API_BASE}/api/shield/vault/${token}/complaint.pdf`;

export const getAwareness = () =>
  request<{
    trending_scams: { cluster_id: string; scam: string; size: number; risk: string; states: string[] }[];
    hotspot_states: Hotspot[];
  }>("/api/shield/awareness");
