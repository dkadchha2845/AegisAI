/**
 * The whole system, in one shape.
 *
 * Eight stations on one track, and a light that travels it as you scroll.
 * Everything the page has argued in eleven sections, assembled into the
 * single object it actually is — which is the job of a penultimate section:
 * not to introduce anything, but to let the reader see the thing whole.
 *
 * The track is horizontal on a desktop and vertical on a phone, and the
 * travelling light is the same tween either way — it is a `clip-path` on one
 * absolutely-positioned overlay of the same track, so the "lit" portion is
 * the identical drawing rather than a second one that has to be kept in
 * sync.
 */

import { useEffect, useRef } from "react";
import {
  gsap,
  split,
  fontsReady,
  DUR,
  EASE,
  reduced,
  refreshSoon,
} from "@/lib/landing-motion";

const STATIONS = [
  { n: "01", name: "Input", body: "Anything: a link, a screenshot, an installer, a call." },
  { n: "02", name: "Understand", body: "What is this, from its bytes — not from its label." },
  { n: "03", name: "Investigate", body: "The agents that apply, each answering one question." },
  { n: "04", name: "Correlate", body: "Look the entities up. Indicators become a campaign, or they don't." },
  { n: "05", name: "Reason", body: "Weighted fusion. No single soft signal is dispositive." },
  { n: "06", name: "Score", body: "One calibrated figure on a five-step ramp." },
  { n: "07", name: "Explain", body: "Every contribution named, every check cited." },
  { n: "08", name: "Protect", body: "What to say, what to freeze, who to call." },
] as const;

export function SystemSection() {
  const root = useRef<HTMLElement>(null);

  useEffect(() => {
    const el = root.current;
    if (!el || reduced()) return;
    let cancelled = false;
    const teardown: (() => void)[] = [];

    void fontsReady().then(() => {
      if (cancelled) return;
      const ctx = gsap.context(() => {
        const h = split(el.querySelector("[data-s-h2]"), "lines");
        gsap.from(h.lines, {
          yPercent: 116,
          opacity: 0,
          filter: "blur(12px)",
          duration: DUR.slow,
          ease: EASE.out,
          stagger: 0.09,
          scrollTrigger: { trigger: el, start: "top 74%", once: true },
          onComplete: () => h.revert(),
        });

        /* The light runs the track against the section's own travel. Two
           layers of the same markup, the top one revealed by moving its clip:
           the lit stations are literally the same drawing, so they cannot
           drift out of alignment at any breakpoint. */
        const horizontal = window.matchMedia("(min-width: 861px)").matches;
        gsap.fromTo(
          "[data-s-lit]",
          { clipPath: horizontal ? "inset(0 100% 0 0)" : "inset(0 0 100% 0)" },
          {
            clipPath: "inset(0 0 0 0)",
            ease: "none",
            scrollTrigger: {
              trigger: "[data-s-track]",
              start: "top 76%",
              end: "bottom 56%",
              scrub: 0.6,
              invalidateOnRefresh: true,
            },
          },
        );

        gsap.from("[data-s-station]", {
          opacity: 0,
          y: 24,
          filter: "blur(8px)",
          duration: DUR.reveal,
          stagger: 0.07,
          ease: EASE.out,
          scrollTrigger: { trigger: "[data-s-track]", start: "top 84%", once: true },
        });
      }, el);
      teardown.push(() => ctx.revert());
      // Triggers built after the route's own refresh; see `refreshSoon`.
      refreshSoon();
    });

    return () => {
      cancelled = true;
      teardown.forEach((fn) => fn());
    };
  }, []);

  return (
    <section className="lp-section" id="system" ref={root}>
      <div className="lp-shell">
        <p className="lp-eyebrow">
          <span className="lp-eyebrow__n">10</span> The system
        </p>
        <h2 className="lp-h2" data-s-h2>
          Eight steps, <em>one continuous system.</em>
        </h2>

        <div className="lp-sys" data-s-track>
          {/* The track, drawn twice. The lower copy is the unlit state; the
              upper copy is the same thing in the accent, revealed by clip. */}
          <ol className="lp-sys__row">
            {STATIONS.map((s) => (
              <li className="lp-sys__station" key={s.n} data-s-station>
                <span className="lp-sys__dot" aria-hidden="true" />
                <span className="lp-sys__n lp-mono">{s.n}</span>
                <b>{s.name}</b>
                <em>{s.body}</em>
              </li>
            ))}
          </ol>
          <ol className="lp-sys__row lp-sys__row--lit" data-s-lit aria-hidden="true">
            {STATIONS.map((s) => (
              <li className="lp-sys__station" key={s.n}>
                <span className="lp-sys__dot" />
                <span className="lp-sys__n lp-mono">{s.n}</span>
                <b>{s.name}</b>
                <em>{s.body}</em>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </section>
  );
}
