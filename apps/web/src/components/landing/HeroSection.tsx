/**
 * Arrival.
 *
 * The first screen has to answer "what is this" before anyone decides whether
 * to keep scrolling, so the composition is deliberately asymmetric: the claim
 * on the left at a size that leaves no doubt it is the point, the system
 * itself running on the right. Centred hero type over a centred graphic is
 * the default of every SaaS template, and it puts the two most important
 * things on the page in a fight for the same optical centre.
 *
 * **The entrance.** Eyebrow, then the headline line by line out of its own
 * mask, then the sub, then the actions, then the flow strip. Each stage
 * overlaps the one before by a third — the page assembles rather than
 * marching. The accent clause charges once as it lands and then again every
 * seven seconds, quietly, so a page left open on a second monitor still has a
 * pulse without ever becoming the thing you are watching.
 *
 * **The exit is the interesting half.** Scrolling out of the hero is scrubbed:
 * the headline column rises and defocuses while the network scales up and its
 * ring pushes outward, so leaving the hero reads as moving *into* the system
 * rather than past a banner. Nothing is pinned to do it — a scrub on
 * `transform`, `opacity` and `filter` against the section's own exit costs
 * three composited properties and cannot desynchronise from the scroll the
 * way a pin can.
 *
 * The two figures at the bottom are attributed, and they are the only
 * statistics in the hero. A number without a source on a page about verifying
 * claims would be the page contradicting itself.
 */

import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import { ArrowDown, ScanLine } from "lucide-react";
import { HeroNetwork } from "@/components/landing/HeroNetwork";
import { useMagnetic } from "@/hooks/useMagnetic";
import {
  gsap,
  split,
  fontsReady,
  playWhenVisible,
  DUR,
  EASE,
  reduced,
  refreshSoon,
} from "@/lib/landing-motion";

/** The claim, as lines. Authored as lines rather than measured at runtime so
 *  the break is a typographic decision and not a consequence of the viewport:
 *  "before it becomes" must not be orphaned from "damage". */
const HEADLINE = [
  { text: "Digital threats,", accent: false },
  { text: "investigated before", accent: false },
  { text: "they become damage.", accent: true },
];

export function HeroSection({ booted }: { booted: boolean }) {
  const root = useRef<HTMLElement>(null);
  const cta = useMagnetic<HTMLAnchorElement>(0.32);

  useEffect(() => {
    const el = root.current;
    if (!el || !booted) return;
    const still = reduced();
    let cancelled = false;
    /** Everything the effect creates asynchronously, so unmount can undo it
     *  whether or not the font promise has resolved yet. */
    const teardown: (() => void)[] = [];

    // The exit scrub does not depend on the split, so it is built straight
    // away — a visitor who scrolls before the font lands still gets it.
    const ctx = gsap.context(() => {
      if (still) return;
      gsap
        .timeline({
          scrollTrigger: { trigger: el, start: "top top", end: "bottom top", scrub: 0.6 },
        })
        .to("[data-hero-col]", { yPercent: -22, opacity: 0, filter: "blur(9px)", ease: "none" }, 0)
        .to("[data-hero-visual]", { scale: 1.24, opacity: 0.18, ease: "none" }, 0)
        .to("[data-hero-scroll]", { opacity: 0, duration: 0.2, ease: "none" }, 0);
    }, el);

    if (still) return () => ctx.revert();

    void fontsReady().then(() => {
      if (cancelled) return;
      const intro = gsap.context(() => {
        const lines = split(el.querySelector("[data-hero-h1]"), "lines");
        const tl = gsap.timeline({
          paused: true,
          defaults: { ease: EASE.out },
          // Once the entrance has played the split has no further job, and
          // leaving it in place would freeze the headline's line breaks at
          // whatever width it was first measured at.
          onComplete: () => lines.revert(),
        });

        tl.from("[data-hero-eyebrow]", { opacity: 0, y: 14, duration: DUR.quick })
          .from(
            lines.lines,
            { yPercent: 118, opacity: 0, filter: "blur(14px)", duration: DUR.cinema, stagger: 0.11 },
            "-=0.18",
          )
          .from("[data-hero-sub]", { opacity: 0, y: 22, filter: "blur(9px)", duration: DUR.reveal }, "-=1.05")
          .from("[data-hero-act] > *", { opacity: 0, y: 18, duration: DUR.reveal, stagger: 0.08 }, "-=0.62")
          .from("[data-hero-flow] li", { opacity: 0, y: 12, duration: DUR.quick, stagger: 0.055 }, "-=0.5")
          .from("[data-hero-figs] > *", { opacity: 0, y: 12, duration: DUR.quick, stagger: 0.08 }, "-=0.35")
          .from("[data-hero-scroll]", { opacity: 0, duration: DUR.quick }, "-=0.2");

        /* The accent clause takes the charge as it settles, then re-fires on
           a long loop. One numeric custom property drives both the brightness
           and the glow: the settled values are `var(--lp-accent)` and a
           `color-mix()`, neither of which GSAP's colour parser can read, so
           tweening them directly would hand back a literal string instead of
           easing toward it. */
        const charge = (t: gsap.core.Timeline) =>
          t
            .to("[data-hero-charge]", { "--charge": 1, duration: 0.3, ease: "power2.out" })
            .to("[data-hero-charge]", { "--charge": 0, duration: 0.9, ease: "power2.inOut" }, ">-0.12");
        charge(tl);
        charge(gsap.timeline({ repeat: -1, repeatDelay: 6.5, delay: 7.5 }));

        teardown.push(playWhenVisible(tl));
      }, el);
      teardown.push(() => intro.revert());
      refreshSoon();
    });

    return () => {
      cancelled = true;
      teardown.forEach((fn) => fn());
      ctx.revert();
    };
  }, [booted]);

  return (
    <section className="lp-hero" ref={root} id="top">
      <div className="lp-hero__grid">
        <div className="lp-hero__col" data-hero-col>
          <p className="lp-hero__eyebrow" data-hero-eyebrow>
            <span className="lp-hero__live" aria-hidden="true" />
            <b>AegisAI ·</b> Agentic digital public safety
          </p>

          <h1 className="lp-hero__h1" data-hero-h1>
            {HEADLINE.map((l) => (
              <span className="lp-hero__hline" key={l.text}>
                {l.accent ? <em data-hero-charge>{l.text}</em> : l.text}
              </span>
            ))}
          </h1>

          <p className="lp-hero__sub" data-hero-sub>
            Multimodal evidence, autonomous agents, threat intelligence and
            reasoning you can audit — turning a suspicious message or a live
            call into a verdict, the signals behind it, and the next thing to do.
          </p>

          <div className="lp-hero__act" data-hero-act>
            <Link ref={cta} className="lp-btn lp-btn--primary" to="/analyze">
              <ScanLine size={16} aria-hidden="true" /> Start an investigation
            </Link>
            <a className="lp-btn lp-btn--ghost" href="#investigation">
              Explore the system
            </a>
          </div>

          {/* The page's structure, stated in five words before it is walked
              through in twelve sections. */}
          <ol className="lp-hero__flow" data-hero-flow aria-label="How an investigation flows">
            {["Evidence", "Agents", "Correlation", "Risk", "Protection"].map((s, i) => (
              <li key={s} style={{ ["--i" as string]: i }}>
                <span aria-hidden="true" />
                {s}
              </li>
            ))}
          </ol>

          <div className="lp-hero__figs" data-hero-figs>
            <p>
              <b className="lp-mono">₹1,776 cr</b> lost to digital-arrest fraud in the
              first nine months of 2024
            </p>
            <p>
              <b className="lp-mono">1.14M</b> cybercrime complaints filed in India in 2023
            </p>
          </div>
        </div>

        <div className="lp-hero__visual" data-hero-visual>
          <HeroNetwork />
        </div>
      </div>

      <a className="lp-hero__scroll" href="#problem" data-hero-scroll>
        <span>Scroll</span>
        <ArrowDown size={13} aria-hidden="true" />
      </a>
    </section>
  );
}
