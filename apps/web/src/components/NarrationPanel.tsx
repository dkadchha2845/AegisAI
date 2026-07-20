/**
 * Narration — what the system is doing, in the words a person would use.
 *
 * This exists because a wall of meters is not an explanation. Someone looking
 * at the console for the first time can see that a number is 78 and rising
 * without having any idea what the machine thinks is happening or why it
 * decided that.
 *
 * The text is a contract field (`StateFrame.narration`), not local copy. Two
 * implementations of "what's happening" would drift apart exactly like two
 * implementations of the threat maths, except the disagreement would be in
 * prose and nobody would notice until a judge read the panel and the meter in
 * the same glance.
 *
 * The recorded fixture predates the field, so when it is absent this falls
 * back to a locally-derived sentence — clearly marked, because a derived
 * narration is a description of the frame rather than an account of the
 * engine's reasoning.
 */

import type { StateFrame } from "@/types/contract";
import { pretty } from "@/lib/stages";

export function NarrationPanel({ frame }: { frame: StateFrame | null }) {
  if (!frame) {
    return (
      <>
        <p className="label">What's happening</p>
        <p className="narration__detail">Waiting for the first frame.</p>
      </>
    );
  }

  const narration = frame.narration;

  if (narration) {
    return (
      <>
        <p className="label">What's happening</p>
        <div className="narration">
          <div className="narration__head">{narration.headline}</div>
          <p className="narration__detail">{narration.detail}</p>
          {narration.sources.length > 0 && (
            <div className="narration__src">↳ {narration.sources.join(" · ")}</div>
          )}
        </div>
      </>
    );
  }

  return (
    <>
      <p className="label">What's happening</p>
      <div className="narration">
        <div className="narration__head">{derivedHeadline(frame)}</div>
        <p className="narration__detail">{derivedDetail(frame)}</p>
        <div className="narration__src faint">
          Derived from the frame — this stream predates the narration field, so
          this describes the state rather than the engine's reasoning.
        </div>
      </div>
    </>
  );
}

function derivedHeadline(frame: StateFrame): string {
  const stage = frame.stage?.current;
  if (!stage) return "Listening.";
  if (stage === "BENIGN") return "Nothing alarming in this call so far.";
  return `Caller is in ${pretty(stage).toLowerCase()}.`;
}

function derivedDetail(frame: StateFrame): string {
  const parts: string[] = [];
  const threat = frame.threat;
  if (threat) {
    parts.push(`Threat is ${threat.score.toFixed(0)}/100 (${threat.level}).`);
    if (threat.drivers.length) {
      parts.push(
        `Biggest contributor: ${threat.drivers[0].label.toLowerCase()} — ${threat.drivers[0].detail}.`,
      );
    }
  }
  const forecast = frame.forecast;
  if (forecast) {
    parts.push(
      `The twin expects ${pretty(forecast.next_stage).toLowerCase()} next (${Math.round(
        forecast.probability * 100,
      )}%).`,
    );
    if (forecast.eta_to_payment_s != null) {
      parts.push(
        `If nobody intervenes, money moves in about ${Math.round(forecast.eta_to_payment_s)}s.`,
      );
    }
  }
  if (frame.guardian.state === "ALERTING") {
    parts.push("The guardian has been alerted and has not acknowledged yet.");
  }
  if (frame.payment.state === "HELD") {
    parts.push("A payment is being held pending review.");
  }
  return parts.join(" ") || "No signals yet.";
}
