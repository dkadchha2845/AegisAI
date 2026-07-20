import { useEffect, useRef } from "react";
import { gsap, prefersReducedMotion } from "@/lib/gsap";
import type { Forecast } from "@/types/contract";

/**
 * The Digital Twin readout — beat 3, and the component the demo is built around.
 *
 * Design intent: this must not look like another status field. It is the one
 * element on screen making a *claim about the future*, so it gets the accent
 * colour (which nothing else uses), a countdown that visibly runs down, and a
 * confirmation state when the prediction lands.
 *
 * The countdown ticks locally between frames. Backend frames arrive every few
 * seconds; a number that only moves when a frame lands looks broken, so the
 * chip interpolates and re-syncs on each frame.
 */

const LABEL: Record<string, string> = {
  GREETING: "Greeting",
  AUTHORITY_CLAIM: "Authority claim",
  FEAR_INDUCTION: "Fear induction",
  ISOLATION: "Isolation",
  VERIFICATION_DEMAND: "Credential demand",
  PAYMENT_SETUP: "Payment setup",
  PAYMENT_EXECUTION: "Payment execution",
  BENIGN: "Benign",
};

interface Props {
  forecast: Forecast | null;
  /** Bumped by App when a FORECAST_HIT event arrives. */
  hitSeq: number;
}

export function ForecastChip({ forecast, hitSeq }: Props) {
  const rootRef = useRef<HTMLDivElement>(null);
  const etaRef = useRef<HTMLSpanElement>(null);
  const eta = forecast?.eta_s ?? 0;

  // Local countdown between frames.
  useEffect(() => {
    const el = etaRef.current;
    if (!el || !forecast) return;
    const obj = { v: eta };
    if (prefersReducedMotion) {
      el.textContent = `${Math.max(0, Math.round(obj.v))}s`;
      return;
    }
    const tween = gsap.to(obj, {
      v: 0,
      duration: Math.max(0.1, eta),
      ease: "none",
      onUpdate: () => {
        el.textContent = `${Math.max(0, Math.round(obj.v))}s`;
      },
    });
    return () => {
      tween.kill();
    };
  }, [eta, forecast]);

  // Confirmation flash when the twin calls it right.
  useEffect(() => {
    if (!hitSeq || !rootRef.current || prefersReducedMotion) return;
    const tl = gsap.timeline();
    tl.fromTo(
      rootRef.current,
      { scale: 1 },
      { scale: 1.05, duration: 0.16, ease: "power2.out" },
    ).to(rootRef.current, { scale: 1, duration: 0.4, ease: "elastic.out(1, 0.5)" });
    return () => {
      tl.kill();
    };
  }, [hitSeq]);

  if (!forecast) {
    return (
      <div className="forecast forecast--idle">
        <span className="label">Digital Twin</span>
        <p className="forecast__idle">No escalation predicted</p>
      </div>
    );
  }

  const pct = Math.round(forecast.probability * 100);

  return (
    <div className="forecast" ref={rootRef} data-hit={forecast.last_prediction_correct || undefined}>
      <div className="forecast__head">
        <span className="label">Digital Twin — forecast</span>
        {forecast.last_prediction_correct && (
          <span className="forecast__hit">✓ last call correct</span>
        )}
      </div>

      <div className="forecast__body">
        <span className="forecast__next">{LABEL[forecast.next_stage] ?? forecast.next_stage}</span>
        <span className="forecast__meta mono">
          in <span ref={etaRef}>{Math.round(eta)}s</span> · {pct}%
        </span>
      </div>

      {/* Confidence as a bar, because a bare percentage is easy to disbelieve. */}
      <span className="forecast__conf" aria-hidden="true">
        <i style={{ transform: `scaleX(${forecast.probability})` }} />
      </span>

      {forecast.eta_to_payment_s != null && (
        <p className="forecast__payment mono">
          money moves in ~{Math.round(forecast.eta_to_payment_s)}s
        </p>
      )}
    </div>
  );
}
