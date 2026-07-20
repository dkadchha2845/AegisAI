/**
 * Home — the explanation of what this is, for someone who arrived cold.
 *
 * Structured as the argument rather than as a feature list: here is the arc a
 * scam call follows, here is what the system does at each point in it, here
 * is what it costs to be wrong in each direction. The features are a
 * consequence of that argument, so they come last.
 *
 * Motion is scroll-driven via GSAP ScrollTrigger and is decorative only —
 * every element is readable with JavaScript disabled and with
 * prefers-reduced-motion set, because a landing page that requires animation
 * to be legible fails for exactly the users most likely to need this product.
 */

import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, ScanLine, Activity } from "lucide-react";
import { ThreatField } from "@/components/three/ThreatField";
import { STAGE_BLURB, STAGE_ORDER, pretty, stageColor } from "@/lib/stages";
import { gsap, ScrollTrigger, prefersReducedMotion } from "@/lib/gsap";
import { useHealth } from "@/hooks/useHealth";

export function Home() {
  const root = useRef<HTMLDivElement>(null);
  const health = useHealth();

  useEffect(() => {
    if (prefersReducedMotion) return;
    const ctx = gsap.context(() => {
      // Targeted by attribute, not by `.hero__inner > *`. The failsafe in
      // lib/gsap.ts rescues elements marked [data-reveal]; a selector-based
      // tween over unmarked children is invisible to it, and when the ticker
      // stalled mid-entrance the headline and both CTAs stayed at opacity 0
      // with nothing to recover them.
      gsap.from("[data-hero-reveal]", {
        opacity: 0,
        y: 24,
        duration: 0.9,
        ease: "power3.out",
        stagger: 0.09,
      });

      // Each arc step arrives as you reach it. `once: true` matters — a step
      // that re-animates every time you scroll past it reads as a glitch.
      gsap.utils.toArray<HTMLElement>("[data-scroll-reveal]").forEach((el) => {
        gsap.from(el, {
          opacity: 0,
          y: 22,
          duration: 0.65,
          ease: "power3.out",
          scrollTrigger: { trigger: el, start: "top 88%", once: true },
        });
      });
    }, root);

    // Re-measure after the first paint. The stat band fills in from
    // /api/health and the hero font swaps in, both of which change the page
    // height after the triggers computed their start positions — leaving
    // sections below the fold that never fire. Cheap, and it removes a whole
    // class of "why is that section blank" bugs.
    const refresh = requestAnimationFrame(() => ScrollTrigger.refresh());

    return () => {
      cancelAnimationFrame(refresh);
      ctx.revert();
      // ScrollTrigger instances outlive the context on route change unless
      // killed; stale triggers pointing at unmounted DOM throw on the next
      // scroll.
      ScrollTrigger.getAll().forEach((t) => t.kill());
    };
  }, []);

  return (
    <div ref={root}>
      <section className="hero">
        <ThreatField />
        <div className="hero__inner">
          <span className="hero__eyebrow" data-hero-reveal data-reveal>
            Real-time scam-call defence · Hinglish
          </span>
          <h1 className="hero__title" data-hero-reveal data-reveal>
            It knows what the scammer <em>will say next</em>.
          </h1>
          <p className="hero__sub" data-hero-reveal data-reveal>
            PRESAGE listens to a call as it happens, names the manipulation stage
            in progress, and forecasts how long until money moves. Then it does
            something about it — coaching the person on the line, alerting a
            trusted contact, and holding the payment.
          </p>
          <div className="hero__cta" data-hero-reveal data-reveal>
            <Link className="btn2 btn2--primary" to="/analyzer">
              <ScanLine size={16} /> Check something suspicious
            </Link>
            <Link className="btn2" to="/console">
              <Activity size={16} /> Watch a live call
            </Link>
          </div>
        </div>
        <span className="hero__scroll">scroll</span>
      </section>

      <section className="section">
        <h2 className="section__title" data-scroll-reveal>
          Every one of these calls follows the same seven steps
        </h2>
        <p className="section__lede" data-scroll-reveal>
          That is the entire premise. A scam call is not improvised — it is a
          script with a fixed structure, because the structure is what works.
          Once you can name the step in progress, you can predict the next one,
          and predicting the next one is what buys the time to intervene.
        </p>

        <div className="arc">
          {STAGE_ORDER.filter((s) => s !== "BENIGN").map((stage, i) => (
            <div
              className="arcstep"
              key={stage}
              data-scroll-reveal
              style={{ ["--stage-color" as string]: stageColor(stage) }}
            >
              <span className="arcstep__n mono">{String(i + 1).padStart(2, "0")}</span>
              <div>
                <span className="arcstep__label">{pretty(stage)}</span>
                <p className="arcstep__body">{STAGE_BLURB[stage]}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="section">
        <h2 className="section__title" data-scroll-reveal>
          Being wrong costs different amounts in each direction
        </h2>
        <p className="section__lede" data-scroll-reveal>
          A missed scam is the obvious harm. The subtler one is crying wolf on a
          genuine bank call — that is how someone learns to dismiss the alert,
          and a system people dismiss protects nobody. So the corpus is half
          legitimate calls that use the same vocabulary, and the benign class is
          deliberately the broadest one in the taxonomy.
        </p>

        <div className="statband">
          <div className="stat" data-scroll-reveal>
            <div className="stat__n">8</div>
            <p className="stat__l">
              speech-act stages, not topics. Every extra class costs recall on
              the two that matter.
            </p>
          </div>
          <div className="stat" data-scroll-reveal>
            <div className="stat__n">320</div>
            <p className="stat__l">
              labelled synthetic calls — 200 scam, 120 benign — split by whole
              held-out archetype, never by utterance.
            </p>
          </div>
          <div className="stat" data-scroll-reveal>
            <div className="stat__n">
              {health.data?.retrieval.chunks ?? "—"}
            </div>
            <p className="stat__l">
              cited advisory sections behind the verdicts. Every claim resolves
              to a source you can read.
            </p>
          </div>
          <div className="stat" data-scroll-reveal>
            <div className="stat__n">1930</div>
            <p className="stat__l">
              India's cybercrime helpline. Reporting in the first few hours is
              what gets money frozen.
            </p>
          </div>
        </div>
      </section>

      <section className="section">
        <h2 className="section__title" data-scroll-reveal>
          Three things that make it a product rather than a demo
        </h2>
        <div className="grid2">
          <div className="card" data-scroll-reveal>
            <h3 className="card__title">Every score carries its reasons</h3>
            <p className="muted small">
              A meter reading 91 with no explanation is a demo. This one names
              the signals that produced it, weights them, and cites the document
              behind each mechanical check — so "why?" always has an answer.
            </p>
          </div>
          <div className="card" data-scroll-reveal>
            <h3 className="card__title">The coach never improvises</h3>
            <p className="muted small">
              The lines a frightened person is told to say come from a curated,
              human-reviewed library and are delivered verbatim. A language
              model may rank them; it never writes them.
            </p>
          </div>
          <div className="card" data-scroll-reveal>
            <h3 className="card__title">Degradation is stated, never hidden</h3>
            <p className="muted small">
              When the fine-tuned classifier is not loaded, or retrieval falls
              back to lexical search, the interface says so. A confident number
              built on nothing is worse than an honest gap.
            </p>
          </div>
        </div>

        <div className="row" style={{ marginTop: "var(--s-6)" }} data-scroll-reveal>
          <Link className="btn2 btn2--primary" to="/dashboard">
            Open the dashboard <ArrowRight size={15} />
          </Link>
          <Link className="btn2" to="/model">
            Read the model card
          </Link>
        </div>
      </section>
    </div>
  );
}
