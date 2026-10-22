/**
 * The agent trace (G-04) — one row per agent: status, latency, findings; each
 * row opens to show what the agent found, the features it contributed and why
 * it failed, if it did.
 *
 * Lifted from the row the Investigate page drew inline, with its rule kept:
 * an agent that degraded, skipped or errored is shown exactly as loudly as one
 * that succeeded — hiding a shortfall is the failure `degraded` exists to
 * prevent. Every value is a contract field rendered verbatim (invariant 2),
 * including the adversarial verifier's verdict on a finding when there is one
 * (T-17). The graph view of the same trace is T-49.
 */

import { ChevronRight } from "lucide-react";
import { useId, useState } from "react";
import type { AgentResult, Finding } from "@/types/contract";
import { EmptyState, ErrorState, SkeletonRows } from "./States";

function toneOf(status: string): string | undefined {
  if (status === "ok") return "ok";
  if (status === "degraded") return "warn";
  if (status === "error") return "bad";
  return undefined;
}

const VERDICT_TONE: Record<string, string> = { UPHELD: "ok", DOWNGRADED: "warn", REJECTED: "bad" };

interface Props {
  results: AgentResult[];
  loading?: boolean;
  error?: string | null;
  onRetry?: () => void;
}

export function AgentTrace({ results, loading, error, onRetry }: Props) {
  if (loading) return <SkeletonRows rows={5} cols={4} />;
  if (error) return <ErrorState inline title="The agent trace could not be loaded" detail={error} onRetry={onRetry} />;
  if (results.length === 0) {
    return <EmptyState inline title="No agent has reported yet" body="Each agent appears here as it finishes, with what it found." />;
  }
  return (
    <ul className="atr" aria-label="Agents">
      {results.map((r, i) => (
        <AgentTraceRow key={`${r.agent}-${i}`} result={r} />
      ))}
    </ul>
  );
}

function AgentTraceRow({ result }: { result: AgentResult }) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const count = result.findings.length;
  const features = Object.entries(result.features);
  return (
    <li className="atr__row" data-status={result.status}>
      <button
        type="button"
        className="atr__head"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((v) => !v)}
      >
        <ChevronRight size={14} className="atr__chev" aria-hidden="true" />
        <span className="atr__name mono">{result.agent}</span>
        <span className="chip" data-tone={toneOf(result.status)}>{result.status}</span>
        <span className="atr__meta mono">{result.latency_ms} ms</span>
        <span className="atr__meta">
          {count} finding{count === 1 ? "" : "s"}
        </span>
      </button>
      <div id={panelId} className="atr__panel" hidden={!open}>
        <p className="atr__line small muted">
          <span className="mono">v{result.version}</span> · confidence {Math.round(result.confidence * 100)}%
          {result.provenance.length > 0 && <> · from {result.provenance.join(", ")}</>}
        </p>
        {result.error && <p className="fieldmsg fieldmsg--bad">{result.error}</p>}
        {count > 0 && (
          <ul className="atr__findings">
            {result.findings.map((f, i) => (
              <FindingRow key={`${f.label}-${i}`} finding={f} />
            ))}
          </ul>
        )}
        {features.length > 0 && (
          <dl className="kv atr__features">
            {features.map(([k, v]) => (
              <div key={k} className="atr__feature">
                <dt className="mono">{k}</dt>
                <dd className="mono">{v}</dd>
              </div>
            ))}
          </dl>
        )}
      </div>
    </li>
  );
}

function FindingRow({ finding }: { finding: Finding }) {
  const v = finding.verification;
  return (
    <li className="atr__finding">
      <span className="mono">{finding.label}</span>
      {finding.value && <span className="atr__value">{finding.value}</span>}
      <span className="atr__meta mono">{Math.round(finding.confidence * 100)}% · {finding.source}</span>
      {v && (
        <span className="chip" data-tone={VERDICT_TONE[v.verdict]} title={`${v.challenger}: ${v.reason}`}>
          {v.verdict.toLowerCase()}
        </span>
      )}
      {finding.detail && <span className="atr__detail small muted">{finding.detail}</span>}
      {v && v.verdict !== "UPHELD" && (
        <span className="atr__detail small">
          A7 {v.verdict.toLowerCase()} this ({Math.round(v.confidence_before * 100)}% → {Math.round(v.confidence_after * 100)}%): {v.reason}
        </span>
      )}
    </li>
  );
}
