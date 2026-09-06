/**
 * The architecture, drawn as an architecture.
 *
 * A core at the top, four tiers of specialists beneath it, and one verdict at
 * the bottom that all four feed. The tiers light up in order as the section
 * passes, so the diagram is read the way the system runs rather than all at
 * once — and hovering a tier dims the others, which is the only way a
 * four-way fan-out stays legible when every line is on at the same time.
 *
 * **Why not one model with a big prompt.** That is the claim of the section
 * and it is worth being precise about: each agent answers one narrow question
 * it can be held to, records how long it took, and reports its own status. An
 * agent that degrades is *shown* degraded. The alternative — a single model
 * asked to do all of it — cannot tell you which part of its answer failed,
 * which makes it unauditable, which makes it inadmissible.
 *
 * The tier and agent names are the ones in `agents/registry.py` and the
 * inherited analyzer modules. They are not a plausible-sounding list.
 *
 * Geometry: one table of viewBox coordinates, read by both the SVG edges and
 * the absolutely-positioned DOM cards, exactly as in the hero. Below 900px
 * the diagram stops being a diagram and becomes four cards in a column — the
 * lines carry no information a stacked reading order does not.
 */

import { useEffect, useRef } from "react";
import { Network, ScanLine, Search, ShieldCheck } from "lucide-react";
import {
  gsap,
  split,
  fontsReady,
  DUR,
  EASE,
  reduced,
  refreshSoon,
} from "@/lib/landing-motion";

const W = 1200;
const H = 580;
const CORE = { x: 600, y: 54 };
const VERDICT = { x: 600, y: 532 };
const CARD_TOP = 180;
const CARD_BOTTOM = 393;

const TIERS = [
  {
    id: "understand",
    tier: "Understand",
    icon: ScanLine,
    x: 165,
    body: "Decides what the evidence is from its bytes, and pulls the indicators out of it.",
    agents: ["Input classifier", "OCR / vision", "Entity extraction"],
  },
  {
    id: "investigate",
    tier: "Investigate",
    icon: Search,
    x: 455,
    body: "The specialists. Each one answers a narrow question it can be held to.",
    agents: ["Script match", "Stage classifier", "Trust passport", "Number intelligence"],
  },
  {
    id: "correlate",
    tier: "Correlate",
    icon: Network,
    x: 745,
    body: "Connects this case to every case before it — the part a single check cannot do.",
    agents: ["Graph correlation", "Cluster lookup", "Geospatial"],
  },
  {
    id: "judge",
    tier: "Judge",
    icon: ShieldCheck,
    x: 1035,
    body: "Fuses the findings into one score, forecasts the next move, writes down why.",
    agents: ["Threat fusion", "Digital twin", "Explanation"],
  },
] as const;

/** Core → tier, and tier → verdict, as cubics that leave and arrive
 *  vertically. A straight line between two boxes at different x reads as a
 *  connector; a curve that leaves downward reads as flow. */
const down = (from: { x: number; y: number }, to: { x: number; y: number }) =>
  `M ${from.x} ${from.y} C ${from.x} ${(from.y + to.y) / 2}, ${to.x} ${(from.y + to.y) / 2}, ${to.x} ${to.y}`;

export function AgentsSection() {
  const root = useRef<HTMLElement>(null);

  useEffect(() => {
    const el = root.current;
    if (!el || reduced()) return;
    let cancelled = false;
    const teardown: (() => void)[] = [];

    void fontsReady().then(() => {
      if (cancelled) return;
      const ctx = gsap.context(() => {
        const h = split(el.querySelector("[data-a-h2]"), "lines");
        gsap.from(h.lines, {
          yPercent: 116,
          opacity: 0,
          filter: "blur(12px)",
          duration: DUR.slow,
          ease: EASE.out,
          stagger: 0.09,
          scrollTrigger: { trigger: el, start: "top 72%", once: true },
          onComplete: () => h.revert(),
        });
        gsap.from("[data-a-lede]", {
          opacity: 0,
          y: 22,
          filter: "blur(8px)",
          duration: DUR.reveal,
          ease: EASE.out,
          scrollTrigger: { trigger: "[data-a-lede]", start: "top 88%", once: true },
        });

        /* The system comes up in the order it runs: core, then each tier with
           its own feed line and its own agents, then the verdict all four
           reach. Scrubbed against the diagram's own travel through the
           viewport, so scrolling back up takes it apart again. */
        const tl = gsap.timeline({
          scrollTrigger: {
            trigger: "[data-a-stage]",
            start: "top 78%",
            end: "bottom 62%",
            scrub: 0.7,
          },
        });

        tl.from("[data-a-core]", { scale: 0.55, opacity: 0, duration: 0.5, ease: "back.out(1.6)", transformOrigin: "50% 50%" });

        TIERS.forEach((t, i) => {
          tl.from(`[data-a-feed="${t.id}"]`, { drawSVG: "0% 0%", duration: 0.5, ease: "power2.inOut" }, `>-${i === 0 ? 0.1 : 0.3}`)
            .from(`[data-a-card="${t.id}"]`, { opacity: 0, y: 26, filter: "blur(10px)", duration: 0.5, ease: EASE.out }, "<0.15")
            .from(`[data-a-card="${t.id}"] li`, { opacity: 0, x: -12, duration: 0.3, stagger: 0.06, ease: EASE.out }, "<0.15")
            .from(`[data-a-out="${t.id}"]`, { drawSVG: "0% 0%", duration: 0.45, ease: "power2.inOut" }, "<0.2");
        });

        tl.from("[data-a-verdict]", { scale: 0.6, opacity: 0, duration: 0.5, ease: "back.out(1.6)", transformOrigin: "50% 50%" }, ">-0.2");

        // Once it is up, one packet at a time runs core → tier → verdict, so
        // the diagram keeps a pulse without ever asking to be watched.
        gsap.to("[data-a-feed], [data-a-out]", {
          strokeOpacity: 0.85,
          duration: 0.8,
          ease: "sine.inOut",
          stagger: { each: 0.22, repeat: -1, yoyo: true },
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
    <section className="lp-section" id="agents" ref={root}>
      <div className="lp-shell">
        <p className="lp-eyebrow">
          <span className="lp-eyebrow__n">04</span> Capabilities
        </p>
        <h2 className="lp-h2" data-a-h2>
          One threat. <em>Many agents.</em>
        </h2>
        <p className="lp-lede" data-a-lede>
          Not one model with a large prompt. Thirteen specialists, each answering a
          question it can be held to, each timing itself and reporting its own status —
          because a single opaque answer cannot tell you which part of it failed.
        </p>

        <div className="lp-arch" data-a-stage>
          <svg className="lp-arch__svg" viewBox={`0 0 ${W} ${H}`} fill="none" preserveAspectRatio="none">
            {TIERS.map((t) => (
              <path
                key={`f-${t.id}`}
                className="lp-arch__edge"
                data-a-feed={t.id}
                d={down({ x: CORE.x, y: CORE.y + 44 }, { x: t.x, y: CARD_TOP })}
              />
            ))}
            {TIERS.map((t) => (
              <path
                key={`o-${t.id}`}
                className="lp-arch__edge lp-arch__edge--out"
                data-a-out={t.id}
                d={down({ x: t.x, y: CARD_BOTTOM }, { x: VERDICT.x, y: VERDICT.y - 34 })}
              />
            ))}
          </svg>

          <div className="lp-arch__layer">
            <div
              className="lp-arch__core"
              data-a-core
              style={{ left: `${(CORE.x / W) * 100}%`, top: `${(CORE.y / H) * 100}%` }}
            >
              <b>AEGIS CORE</b>
              <span>orchestration · tracing · degradation</span>
            </div>

            {TIERS.map((t) => (
              <article
                className="lp-arch__card"
                key={t.id}
                data-a-card={t.id}
                style={{ left: `${(t.x / W) * 100}%`, top: `${(CARD_TOP / H) * 100}%` }}
              >
                <header>
                  <span className="lp-arch__icon">
                    <t.icon size={15} strokeWidth={1.7} aria-hidden="true" />
                  </span>
                  <h3>{t.tier}</h3>
                </header>
                <p>{t.body}</p>
                <ul>
                  {t.agents.map((a) => (
                    <li key={a}>{a}</li>
                  ))}
                </ul>
              </article>
            ))}

            <div
              className="lp-arch__verdict"
              data-a-verdict
              style={{ left: `${(VERDICT.x / W) * 100}%`, top: `${(VERDICT.y / H) * 100}%` }}
            >
              <b>One verdict</b>
              <span>score · reasons · next action</span>
            </div>
          </div>
        </div>

        <p className="lp-note">
          <strong>Every agent ships with a benign-input test.</strong> Metadata that a
          legitimate caller might legitimately have must never be able to manufacture a
          scam on its own, so soft signals stay in weighted fusion instead of becoming
          dispositive rules.
        </p>
      </div>
    </section>
  );
}
