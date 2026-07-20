import { useEffect, useRef } from "react";
import { gsap, prefersReducedMotion } from "@/lib/gsap";
import { useCountUp } from "@/hooks/useCountUp";
import type {
  CoachSuggestion,
  CoercionState,
  ManipulationMap as MMap,
  TrustPassport as Passport,
} from "@/types/contract";

/* ------------------------------------------------------------------ *
 * Manipulation Map — cumulative tactic pressure.
 * Bars only ever grow, which is the point: it is a record of what the
 * caller has already done, not a live meter that can walk itself back.
 * ------------------------------------------------------------------ */

const TACTICS: Array<[keyof MMap, string]> = [
  ["authority", "Authority"],
  ["fear", "Fear"],
  ["isolation", "Isolation"],
  ["urgency", "Urgency"],
  ["compliance", "Compliance"],
];

export function ManipulationMap({ map }: { map: MMap }) {
  return (
    <div className="mmap">
      <span className="label">Manipulation map</span>
      <ul className="mmap__list">
        {TACTICS.map(([key, label]) => {
          const v = map[key];
          return (
            <li className="mmap__row" key={key}>
              <span className="mmap__label">{label}</span>
              <span className="mmap__track" aria-hidden="true">
                <i
                  className="mmap__fill"
                  data-active={v > 0.02 || undefined}
                  style={{ transform: `scaleX(${v})` }}
                />
              </span>
              <span className="mmap__val mono">{Math.round(v * 100)}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * Coercion sparkline — victim stress over time.
 * Drawn as a plain polyline: a filled area chart would compete with the
 * threat meter for attention, and this is a supporting signal.
 * ------------------------------------------------------------------ */

export function CoercionSparkline({ coercion }: { coercion: CoercionState | null }) {
  const pts = coercion?.history ?? [];
  const w = 100;
  const h = 30;
  const path =
    pts.length < 2
      ? ""
      : pts
          .map((v, i) => {
            const x = (i / (pts.length - 1)) * w;
            const y = h - (Math.min(100, Math.max(0, v)) / 100) * h;
            return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
          })
          .join(" ");

  const value = coercion?.index ?? 0;
  const numRef = useCountUp(value, 0, 0.4);

  return (
    <div className="spark">
      <div className="spark__head">
        <span className="label">Coercion index</span>
        <span className="spark__val mono" ref={numRef}>
          0
        </span>
      </div>
      <svg viewBox={`0 0 ${w} ${h}`} className="spark__svg" preserveAspectRatio="none">
        <path d={path} className="spark__line" />
      </svg>
      {coercion && (
        <span className="spark__trend" data-trend={coercion.trend}>
          {coercion.trend}
        </span>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * Trust Passport — the countdown from 97% to 3%.
 * Each failed check slides in as evidence lands, so the number falling is
 * visibly *caused* by something rather than just animating.
 * ------------------------------------------------------------------ */

export function TrustPassport({ passport }: { passport: Passport | null }) {
  const pct = passport?.final_trust_pct ?? 100;
  const numRef = useCountUp(pct, 0, 0.7);
  const listRef = useRef<HTMLUListElement>(null);
  const seen = useRef(0);

  useEffect(() => {
    const n = passport?.checks.length ?? 0;
    if (n <= seen.current || !listRef.current || prefersReducedMotion) {
      seen.current = n;
      return;
    }
    const rows = Array.from(listRef.current.children).slice(seen.current) as HTMLElement[];
    seen.current = n;
    const tween = gsap.fromTo(
      rows,
      { opacity: 0, x: -10 },
      { opacity: 1, x: 0, duration: 0.45, ease: "power3.out", stagger: 0.07 },
    );
    return () => {
      tween.kill();
    };
  }, [passport?.checks.length]);

  return (
    <div className="passport">
      <div className="passport__head">
        <span className="label">Trust passport</span>
        <span className="passport__pct mono" data-low={pct < 25 || undefined}>
          <span ref={numRef}>100</span>%
        </span>
      </div>
      {passport?.claimed_identity && (
        <p className="passport__claim">
          claims to be <strong>{passport.claimed_identity}</strong>
        </p>
      )}
      <ul className="passport__checks" ref={listRef}>
        {passport?.checks.map((c) => (
          <li className="passport__check" key={c.name} data-verdict={c.verdict}>
            <span className="passport__mark" aria-hidden="true">
              {c.verdict === "FAIL" ? "✕" : c.verdict === "PASS" ? "✓" : "?"}
            </span>
            <span className="passport__name">{c.name}</span>
            <span className="passport__detail">{c.detail}</span>
            {c.source && <span className="passport__source mono">{c.source}</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * Coach card — retrieved advice, never generated.
 * Re-mounts on line change (keyed by caller) so the entrance replays.
 * ------------------------------------------------------------------ */

export function CoachCard({ coach }: { coach: CoachSuggestion | null }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!coach || !ref.current || prefersReducedMotion) return;
    const tween = gsap.fromTo(
      ref.current,
      { opacity: 0, y: 12 },
      { opacity: 1, y: 0, duration: 0.45, ease: "power3.out" },
    );
    return () => {
      tween.kill();
    };
  }, [coach]);

  if (!coach) return null;

  return (
    <div className="coach" ref={ref} data-urgency={coach.urgency}>
      <span className="label">Say this now</span>
      <p className="coach__line">{coach.line}</p>
      <p className="coach__why">{coach.why}</p>
    </div>
  );
}
