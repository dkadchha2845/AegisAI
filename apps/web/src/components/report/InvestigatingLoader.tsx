/**
 * InvestigatingLoader — the honest "KAVACH is investigating…" checklist.
 *
 * Shared by both journeys (Analyze and end-of-call Live Protection) so the
 * moment before the report looks identical everywhere. The wording describes
 * what KAVACH is doing *for the user*, never which model is running. The steps
 * are paced client-side over the single real request; the caller drives
 * `stepIndex` and never marks a step done before the response can back it up.
 */

import { Loader2 } from "lucide-react";

/** The ordered checklist. Exported so the caller's pacing loop and the visible
 *  ticks stay in lock-step. */
export const INVESTIGATION_STEPS = [
  "Reading your evidence",
  "Looking for scam patterns",
  "Checking the known-scam database",
  "Looking for similar fraud cases",
  "Checking nearby scam activity",
  "Preparing your recommendations",
];

export function InvestigatingLoader({ stepIndex }: { stepIndex: number }) {
  return (
    <div className="card">
      <h2 className="card__title">
        <Loader2 size={16} className="spin" /> KAVACH is investigating…
      </h2>
      <ul className="investigate-steps">
        {INVESTIGATION_STEPS.map((label, i) => {
          const state = i < stepIndex ? "done" : i === stepIndex ? "active" : "pending";
          return (
            <li key={label} data-state={state}>
              {state === "active" ? <span className="spinner" /> : null}
              <span>{label}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
