/**
 * The scam arc as a timeline (G-02) — the seven stages in order, which ones
 * this conversation reached and when, and where it is now.
 *
 * BENIGN is a contract label but not a step in the arc, so it is not drawn;
 * a conversation that reached no scam stage says so rather than showing an
 * empty ladder that reads like a clean result.
 *
 * A pure renderer (invariant 2): which stages were reached, at what
 * confidence and when, all arrive from the contract (a live frame's
 * `stage`, an investigation's stage findings). Nothing is inferred here.
 *
 * Async data gets the three states every component shares: a skeleton while
 * loading, an error with retry, and an empty state.
 */

import { STAGES, type Stage } from "@/types/contract";
import { EmptyState, ErrorState, Skeleton } from "./States";

const ARC: Stage[] = STAGES.filter((s) => s !== "BENIGN");

export function stageLabel(stage: string): string {
  const words = stage.toLowerCase().split("_");
  return words.map((w, i) => (i === 0 ? w[0].toUpperCase() + w.slice(1) : w)).join(" ");
}

export interface StageVisit {
  stage: Stage;
  /** When it was first reached: ISO-8601, or seconds into the call. */
  at?: string | number | null;
  /** The classifier's confidence when it was reached, 0–1. */
  confidence?: number | null;
}

interface Props {
  /** Stages reached, in the order they were first reached. */
  visits: StageVisit[];
  /** Where the conversation is now; omitted for a finished investigation. */
  current?: Stage | null;
  loading?: boolean;
  error?: string | null;
  onRetry?: () => void;
  /** Makes each reached stage a button — to jump to its turn, say. */
  onSelect?: (stage: Stage) => void;
}

function when(at: string | number | null | undefined): string | null {
  if (at === null || at === undefined) return null;
  if (typeof at === "number") return `${Math.round(at)} s`;
  const d = new Date(at);
  return Number.isNaN(d.getTime()) ? at : d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function StageTimeline({ visits, current, loading, error, onRetry, onSelect }: Props) {
  if (loading) return <Skeleton lines={4} label="Loading the stage timeline" />;
  if (error) return <ErrorState inline title="The stage timeline could not be loaded" detail={error} onRetry={onRetry} />;

  const reached = new Map<Stage, StageVisit>();
  for (const v of visits) if (v.stage !== "BENIGN" && !reached.has(v.stage)) reached.set(v.stage, v);
  if (reached.size === 0) {
    return (
      <EmptyState
        inline
        title="No scam stage reached"
        body="None of this conversation was classified as a step of a scam. That is not a guarantee — the verdict says how sure it is."
      />
    );
  }

  return (
    <ol className="stl" aria-label="Scam stages">
      {ARC.map((stage, i) => {
        const visit = reached.get(stage);
        const state = stage === current ? "current" : visit ? "reached" : "ahead";
        const time = when(visit?.at);
        const body = (
          <>
            <span className="stl__dot" aria-hidden="true" />
            <span className="stl__name">{stageLabel(stage)}</span>
            {visit && (
              <span className="stl__meta mono">
                {time}
                {time && typeof visit.confidence === "number" ? " · " : ""}
                {typeof visit.confidence === "number" ? `${Math.round(visit.confidence * 100)}%` : ""}
              </span>
            )}
            <span className="vh">
              {state === "current" ? ", current stage" : state === "reached" ? ", reached" : ", not reached"}
            </span>
          </>
        );
        return (
          <li key={stage} className="stl__step" data-state={state} aria-current={state === "current" ? "step" : undefined}>
            <span className="stl__index mono" aria-hidden="true">{i + 1}</span>
            {onSelect && visit ? (
              <button type="button" className="stl__btn" onClick={() => onSelect(stage)}>
                {body}
              </button>
            ) : (
              <span className="stl__btn">{body}</span>
            )}
          </li>
        );
      })}
    </ol>
  );
}
