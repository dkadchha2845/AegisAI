/**
 * How the number is made.
 *
 * Six signals travel inward, merge, and come out as one calibrated figure with
 * its contributions itemised underneath. The convergence is the argument: not
 * one of those six is conclusive on its own, and the section says so in as
 * many words, because "any one of these means scam" is precisely the design
 * that turns a legitimate caller with an unusual number into a fraud alert.
 *
 * **Why the score is not a circular progress ring.** A ring says "percentage
 * complete". This is not a percentage of anything — it is a calibrated risk
 * figure on a five-step ramp, and the ramp is the thing worth drawing. So the
 * readout is the figure, the ramp position, and the contributions that add up
 * to it; the shape carries the same information the console's meter does.
 *
 * **The invariant this section exists to state.** The language model explains,
 * extracts and ranks. It never scores. The figure comes from a calibrated
 * classifier, deterministic rules and what the graph already knows — and each
 * of those contributions is named and weighted where a reader can check it.
 *
 * The six signals and the three contributions are the real ones from the
 * recorded session's frame at t=36. See `landing/session.ts`.
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
import { DRIVERS, FRAME_36 } from "@/components/landing/session";

const W = 1000;
const H = 460;
const CX = W / 2;
const CY = H / 2;

/** Six signals, each with where it came from. Positions are hand-placed
 *  rather than generated: an even ring would read as a wheel, and the point
 *  is that these arrive from unrelated directions. */
const SIGNALS = [
  { id: "authority", label: "Authority impersonation", detail: "trust passport 3%", x: 118, y: 74 },
  { id: "fear", label: "Fear induction", detail: "manipulation map 1.00", x: 96, y: 232 },
  { id: "isolation", label: "Isolation instruction", detail: "manipulation map 0.28", x: 150, y: 386 },
  { id: "routing", label: "International routing", detail: "number intel FAIL", x: 882, y: 78 },
  { id: "script", label: "Known script", detail: "86% similarity", x: 904, y: 236 },
  { id: "graph", label: "Graph correlation", detail: "2 indicators, 1 cluster", x: 850, y: 390 },
] as const;

export function DecisionSection() {
  const root = useRef<HTMLElement>(null);

  useEffect(() => {
    const el = root.current;
    if (!el) return;
    let cancelled = false;
    const teardown: (() => void)[] = [];

    void fontsReady().then(() => {
      if (cancelled) return;
      const ctx = gsap.context(() => {
        if (!reduced()) {
          const h = split(el.querySelector("[data-d-h2]"), "lines");
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
          gsap.from("[data-d-lede]", {
            opacity: 0,
            y: 22,
            filter: "blur(8px)",
            duration: DUR.reveal,
            ease: EASE.out,
            scrollTrigger: { trigger: "[data-d-lede]", start: "top 88%", once: true },
          });

          /* The convergence, scrubbed: signals appear, their lines find the
             engine, then each signal travels its own line inward and is
             absorbed. Every chip moves toward the same point, which is the
             whole visual claim. */
          const tl = gsap.timeline({
            scrollTrigger: {
              trigger: "[data-d-stage]",
              start: "top 76%",
              end: "bottom 58%",
              scrub: 0.7,
            },
          });

          tl.from("[data-d-sig]", {
            opacity: 0,
            scale: 0.7,
            filter: "blur(10px)",
            duration: 0.5,
            stagger: 0.07,
            ease: EASE.out,
          })
            .from("[data-d-edge]", { drawSVG: "0% 0%", duration: 0.5, stagger: 0.05, ease: "power2.inOut" }, "-=0.3")
            .from("[data-d-engine]", { scale: 0.55, opacity: 0, duration: 0.6, ease: "back.out(1.5)", transformOrigin: "50% 50%" }, "-=0.35")
            // Declared before anything references it. A position string naming
            // a label that does not exist yet makes GSAP invent one at the
            // current end — which then moves when the label is really added,
            // and the tweens placed against the first meaning stay where they
            // were. Two different "converge"s is not a thing to debug twice.
            .addLabel("converge", ">-0.1");

          // Each chip travels to the engine along its own vector. `xPercent`
          // is not usable here — the distance differs per chip — so the
          // offsets are computed from the same coordinate table the SVG uses.
          SIGNALS.forEach((s, i) => {
            tl.to(
              `[data-d-sig="${s.id}"]`,
              {
                x: () => ((CX - s.x) / W) * (el.querySelector("[data-d-stage]") as HTMLElement).clientWidth,
                y: () => ((CY - s.y) / H) * (el.querySelector("[data-d-stage]") as HTMLElement).clientHeight,
                opacity: 0,
                scale: 0.65,
                filter: "blur(6px)",
                duration: 0.7,
                ease: "power2.in",
              },
              `converge+=${i * 0.06}`,
            );
          });

          // The figure resolves as the last chip lands.
          // `fromTo`, and the markup renders the *settled* figure: a reader
          // with reduced motion, or one whose GSAP never ran, must see 88
          // rather than the zero the count-up would have started from.
          const score = el.querySelector<HTMLElement>("[data-d-score]");
          if (score) {
            const obj = { n: 0 };
            tl.fromTo(
              obj,
              { n: 0 },
              {
                n: FRAME_36.score,
                duration: 0.9,
                ease: "power2.out",
                onUpdate: () => {
                  score.textContent = obj.n.toFixed(0);
                },
              },
              "converge+=0.25",
            );
          }
          // The fill is revealed by moving its clip, not by scaling it: the
          // ramp is a gradient, and a squashed gradient puts the wrong colour
          // under the reading.
          tl.from("[data-d-ramp] i", { clipPath: "inset(0 100% 0 0)", duration: 0.7, ease: "power2.out" }, "converge+=0.3")
            .from("[data-d-level]", { opacity: 0, scale: 0.7, duration: 0.35, ease: "back.out(2)" }, "converge+=0.6");

          gsap.from("[data-d-driver]", {
            opacity: 0,
            x: -24,
            filter: "blur(8px)",
            duration: DUR.reveal,
            stagger: 0.12,
            ease: EASE.out,
            scrollTrigger: { trigger: "[data-d-drivers]", start: "top 84%", once: true },
          });
          gsap.from("[data-d-bar] i", {
            scaleX: 0,
            transformOrigin: "left",
            duration: DUR.slow,
            stagger: 0.12,
            ease: EASE.out,
            scrollTrigger: { trigger: "[data-d-drivers]", start: "top 84%", once: true },
          });
        }
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
    <section className="lp-section" id="decides" ref={root}>
      <div className="lp-shell">
        <p className="lp-eyebrow">
          <span className="lp-eyebrow__n">05</span> Reasoning
        </p>
        <h2 className="lp-h2" data-d-h2>
          Six weak signals. <em>One conclusion.</em>
        </h2>
        <p className="lp-lede" data-d-lede>
          Not one of these is conclusive on its own, and that is deliberate. A caller
          with an international number is not a criminal; a message mentioning a parcel
          is not a scam. Make any single signal dispositive and you have built a machine
          that accuses innocent people. They stay in weighted fusion instead.
        </p>

        <div className="lp-fuse" data-d-stage aria-hidden="true">
          <svg className="lp-fuse__svg" viewBox={`0 0 ${W} ${H}`} fill="none" preserveAspectRatio="none">
            {SIGNALS.map((s) => (
              <line
                key={s.id}
                className="lp-fuse__edge"
                data-d-edge
                x1={s.x}
                y1={s.y}
                x2={CX}
                y2={CY}
              />
            ))}
          </svg>

          <div className="lp-fuse__layer">
            {SIGNALS.map((s) => (
              <div
                className="lp-fuse__sig"
                key={s.id}
                data-d-sig={s.id}
                style={{ left: `${(s.x / W) * 100}%`, top: `${(s.y / H) * 100}%` }}
              >
                <b>{s.label}</b>
                <em className="lp-mono">{s.detail}</em>
              </div>
            ))}

            <div className="lp-fuse__engine" data-d-engine>
              <p className="lp-label">Calibrated fusion</p>
              <div className="lp-fuse__read">
                <span className="lp-fuse__score lp-mono" data-d-score>
                  {FRAME_36.score}
                </span>
                <span className="chip chip--caps" data-risk={FRAME_36.level} data-d-level>
                  {FRAME_36.level}
                </span>
              </div>
              {/* The ramp, not a percentage ring: five steps, and the marker
                  sits where this reading falls on them. */}
              <div className="lp-fuse__ramp" data-d-ramp>
                <i style={{ ["--w" as string]: `${FRAME_36.score}%` }} />
              </div>
              <p className="lp-fuse__scale lp-mono">
                <span>calm</span>
                <span>watch</span>
                <span>elevated</span>
                <span>high</span>
                <span>critical</span>
              </p>
            </div>
          </div>
        </div>

        <div className="lp-split" data-d-drivers>
          <div>
            <h3 className="lp-h3" data-d-driver>
              What actually moved it
            </h3>
            <ul className="lp-drivers">
              {DRIVERS.map((d) => (
                <li key={d.label} data-d-driver>
                  <div className="lp-drivers__row">
                    <b>{d.label}</b>
                    <span className="lp-mono">+{d.contribution.toFixed(2)}</span>
                  </div>
                  <span className="lp-drivers__bar" data-d-bar>
                    <i style={{ ["--w" as string]: `${d.contribution * 100}%` }} />
                  </span>
                  <em>{d.detail}</em>
                </li>
              ))}
            </ul>
          </div>
          <div className="lp-card lp-invariant" data-d-driver>
            <p className="lp-label">The rule this engine is built on</p>
            <p className="lp-invariant__line">
              The language model explains, extracts and ranks. <em>It never scores.</em>
            </p>
            <p className="lp-card__body">
              The figure comes from a calibrated classifier, deterministic rules and what
              the fraud graph already knows. A generative model is asked to write the
              explanation of that figure — never to produce it — because a number a model
              felt like emitting cannot be calibrated, cannot be audited, and cannot be
              defended when it is wrong.
            </p>
            <p className="lp-card__body">
              When the fine-tuned classifier is not loaded and a lexical fallback is
              serving instead, the interface says so. A confident number built on nothing
              is worse than an honest gap.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
