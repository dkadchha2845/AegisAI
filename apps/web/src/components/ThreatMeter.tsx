import { useEffect, useRef } from "react";
import { gsap, prefersReducedMotion } from "@/lib/gsap";
import { useCountUp } from "@/hooks/useCountUp";
import type { ThreatState } from "@/types/contract";

/**
 * The threat gauge.
 *
 * A 240° arc rather than a full ring: an open arc reads as a measurement
 * scale, a closed ring reads as a progress donut, and this is not progress.
 *
 * Three things are animated independently, which is what makes it feel wired
 * to the data rather than to a CSS transition:
 *   - the arc length (stroke-dashoffset), tweened by GSAP
 *   - the numeral, counted by useCountUp writing directly to the DOM
 *   - the hue, driven by --threat-color which the app sets on <html>
 *
 * The shake fires on the *event*, not on the score crossing a number here.
 * See App.tsx — thresholds belong to the backend.
 */

const R = 84;
const SWEEP = 240; // degrees
const CIRC = 2 * Math.PI * R;
const ARC_LEN = (CIRC * SWEEP) / 360;

interface Props {
  threat: ThreatState | null;
}

export function ThreatMeter({ threat }: Props) {
  const score = threat?.score ?? 0;
  const level = threat?.level ?? "CALM";

  const arcRef = useRef<SVGCircleElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const numRef = useCountUp(score, 0, 0.5);

  useEffect(() => {
    const el = arcRef.current;
    if (!el) return;
    const offset = ARC_LEN * (1 - score / 100);
    if (prefersReducedMotion) {
      el.style.strokeDashoffset = String(offset);
      return;
    }
    const tween = gsap.to(el, {
      strokeDashoffset: offset,
      duration: 0.55,
      ease: "power3.out",
      overwrite: true,
    });
    return () => {
      tween.kill();
    };
  }, [score]);

  return (
    <div className="meter" ref={wrapRef} data-level={level}>
      <svg viewBox="0 0 200 200" className="meter__svg" aria-hidden="true">
        {/* Track */}
        <circle
          cx="100"
          cy="100"
          r={R}
          className="meter__track"
          strokeDasharray={`${ARC_LEN} ${CIRC}`}
          transform="rotate(150 100 100)"
        />
        {/* Value */}
        <circle
          ref={arcRef}
          cx="100"
          cy="100"
          r={R}
          className="meter__value"
          strokeDasharray={`${ARC_LEN} ${CIRC}`}
          strokeDashoffset={ARC_LEN}
          transform="rotate(150 100 100)"
        />
        {/* Tick marks every 10 — the detail that sells "instrument". */}
        {Array.from({ length: 11 }, (_, i) => {
          const a = (150 + (SWEEP * i) / 10) * (Math.PI / 180);
          const major = i % 5 === 0;
          const r1 = R + 9;
          const r2 = R + (major ? 17 : 13);
          return (
            <line
              key={i}
              x1={100 + Math.cos(a) * r1}
              y1={100 + Math.sin(a) * r1}
              x2={100 + Math.cos(a) * r2}
              y2={100 + Math.sin(a) * r2}
              className={major ? "meter__tick meter__tick--major" : "meter__tick"}
            />
          );
        })}
      </svg>

      <div className="meter__readout">
        <span className="meter__score mono" ref={numRef}>
          0
        </span>
        <span className="meter__level">{level}</span>
      </div>
    </div>
  );
}

/** The named reasons behind the score. A meter without these is a demo. */
export function ThreatDrivers({ threat }: Props) {
  if (!threat?.drivers.length) return null;
  return (
    <ul className="drivers">
      {threat.drivers.map((d) => (
        <li className="drivers__row" key={d.label}>
          <span className="drivers__bar" aria-hidden="true">
            <i style={{ transform: `scaleX(${Math.min(1, d.contribution)})` }} />
          </span>
          <span className="drivers__label">{d.label}</span>
          <span className="drivers__detail">{d.detail}</span>
        </li>
      ))}
    </ul>
  );
}
