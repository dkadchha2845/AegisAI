/**
 * Home — the landing.
 *
 * One continuous argument, told in the order a sceptical reader needs it:
 * arrival, the problem, what counts as evidence, an investigation actually
 * running, the agents that run it, how six weak signals become one
 * conclusion, what the graph knows that no single check can, protection while
 * the call is still happening, how the number is made, why you can check it,
 * what it is built out of, the whole system in one shape, and then the one
 * thing to do about it.
 *
 * ---------------------------------------------------------------------------
 * THE RULES THIS PAGE HOLDS ITSELF TO — they are the product's rules
 * ---------------------------------------------------------------------------
 *
 * **Nothing on it is invented.** Every number on this page is either read out
 * of `mock/stream.json` — the same recorded digital-arrest session the live
 * console plays, named wherever it is used — or fetched from
 * `/api/intel/stats` at load, or a cited public statistic. The threat
 * trajectory in the risk section is the real sequence from that recording
 * (6.3 → 38.7 → 61.6 → 72 → 88 → 97), not a curve drawn because it looked
 * dramatic. A landing page that invents a plausible risk score is doing the
 * exact thing this product exists to detect.
 *
 * **Colour still means something.** The threat ramp appears in four places —
 * the pinned investigation's verdict, the fusion conclusion, the live call and
 * the risk engine — because those are the four places a threat is being
 * reported. Everywhere else the page is graphite and one blue.
 *
 * **Motion is never load-bearing.** Every section is legible with JavaScript
 * disabled, with GSAP failed, and with reduced motion set. Entrances are
 * `gsap.from`, so the settled state is whatever the stylesheet already says;
 * `armFailsafe()` force-reveals anything still hidden after 2.5s; and the
 * reduced-motion branch of every section is a static, complete composition
 * rather than a degraded one.
 *
 * This route renders outside the AppShell, so it carries its own chrome.
 */

import { useEffect, useState } from "react";
import { Atmosphere } from "@/components/landing/Atmosphere";
import { LandingNav } from "@/components/landing/LandingNav";
import { Preloader, shouldBoot } from "@/components/landing/Preloader";
import { HeroSection } from "@/components/landing/HeroSection";
import { ProblemSection } from "@/components/landing/ProblemSection";
import { EvidenceSection } from "@/components/landing/EvidenceSection";
import { InvestigationSection } from "@/components/landing/InvestigationSection";
import { AgentsSection } from "@/components/landing/AgentsSection";
import { DecisionSection } from "@/components/landing/DecisionSection";
import { GraphSection } from "@/components/landing/GraphSection";
import { LiveCallSection } from "@/components/landing/LiveCallSection";
import { ExplainSection } from "@/components/landing/ExplainSection";
import { ResearchSection } from "@/components/landing/ResearchSection";
import { SystemSection } from "@/components/landing/SystemSection";
import { ClosingSection } from "@/components/landing/ClosingSection";
import { armFailsafe, ScrollTrigger } from "@/lib/landing-motion";
import "@/styles/landing.css";

export function Home() {
  /** The veil decides synchronously whether it is playing, so there is never
   *  a frame of overlay for a visitor who is not getting one. */
  const [booting, setBooting] = useState(shouldBoot);

  useEffect(() => {
    armFailsafe();
    // Twelve sections of scroll-triggered work measure a document whose height
    // is still settling while fonts swap and the stats request lands. One
    // refresh after the first paint, and one on the load event, is the
    // difference between triggers that fire where they were authored and
    // triggers that fire a screen early.
    const raf = requestAnimationFrame(() => ScrollTrigger.refresh());
    const onLoad = () => ScrollTrigger.refresh();
    window.addEventListener("load", onLoad);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("load", onLoad);
    };
  }, []);

  return (
    <div className="lp">
      <a className="skiplink" href="#lp-main">Skip to content</a>
      {booting && <Preloader onDone={() => setBooting(false)} />}
      <Atmosphere />
      <LandingNav />

      <main className="lp-main" id="lp-main" tabIndex={-1}>
        <HeroSection booted={!booting} />
        <ProblemSection />
        <EvidenceSection />
        <InvestigationSection />
        <AgentsSection />
        <DecisionSection />
        <GraphSection />
        <LiveCallSection />
        <ExplainSection />
        <ResearchSection />
        <SystemSection />
        <ClosingSection />
      </main>
    </div>
  );
}
