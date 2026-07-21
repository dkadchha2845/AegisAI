/**
 * Typed client for the PRESAGE API.
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

async function request<T>(path: string, init?: RequestInit): Promise<ApiResult<T>> {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers:
        init?.body instanceof FormData
          ? init?.headers
          : { "content-type": "application/json", ...(init?.headers ?? {}) },
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
  classifier: { backend: string; checkpoint: string; loaded: boolean };
  retrieval: { backend: string; chunks: number; documents: string[] };
  twin: { fitted: boolean; stages: string[]; support: Record<string, number> };
  coach: { lines: number };
  llm: { backend: string; model: string | null; configured: boolean };
  degraded: string[];
}

export const getHealth = () => request<Health>("/api/health");

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
