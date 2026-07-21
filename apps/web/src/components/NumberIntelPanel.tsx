import { useEffect, useRef } from "react";
import { gsap, prefersReducedMotion } from "@/lib/gsap";
import { useCountUp } from "@/hooks/useCountUp";
import type { NumberIntel } from "@/types/contract";

/* ------------------------------------------------------------------ *
 * Number Intelligence — the metadata half of the verdict.
 *
 * Deliberately built from the same markup as the Trust Passport: same
 * PASS/FAIL/UNKNOWN rows, same citation footnotes. The one inversion is the
 * headline number — `risk` counts *up* toward danger where trust counts down —
 * so it wears `data-high` instead of `data-low`. Reusing the passport classes
 * is not laziness: the two panels answer the same shape of question ("can I
 * trust this caller, and why"), and rendering them identically is what tells a
 * viewer they are the same kind of evidence.
 * ------------------------------------------------------------------ */

export function NumberIntelPanel({ intel }: { intel: NumberIntel | null }) {
  const risk = intel?.risk ?? 0;
  const numRef = useCountUp(risk, 0, 0.6);
  const listRef = useRef<HTMLUListElement>(null);
  const seen = useRef(0);

  useEffect(() => {
    const n = intel?.checks.length ?? 0;
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
  }, [intel?.checks.length]);

  return (
    <div className="passport">
      <div className="passport__head">
        <span className="label">Number intelligence</span>
        <span className="passport__pct mono" data-high={risk >= 55 || undefined}>
          <span ref={numRef}>0</span>
          <span className="passport__risk-unit"> risk</span>
        </span>
      </div>
      {intel?.number && (
        <p className="passport__claim">
          caller ID <strong>{intel.number}</strong>
        </p>
      )}
      <ul className="passport__checks" ref={listRef}>
        {intel?.checks.map((c) => (
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
