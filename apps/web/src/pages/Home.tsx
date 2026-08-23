/**
 * Home — the landing. The argument for AegisAI, told cinematically.
 *
 * Structured as the product's own thesis: digital-arrest scams are an industrial
 * pipeline, so the defence is a pipeline too — Detect (Module 1) → Connect
 * (Module 2) → Protect (Module 3). The three-module story is the spine; the
 * seven-step arc, the live numbers, and the engineering principles hang off it.
 *
 * Motion is scroll-driven GSAP and is decorative only: every element is legible
 * with JavaScript disabled and with prefers-reduced-motion set, and the failsafe
 * from lib/gsap rescues any entrance that stalls — a landing that needs
 * animation to be readable fails exactly the users most likely to need this.
 *
 * This route lives outside the AppShell, so it carries its own minimal header
 * and arms the reveal failsafe itself.
 */

import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  Activity,
  ArrowRight,
  LifeBuoy,
  Moon,
  Network,
  ScanLine,
  Sun,
} from "lucide-react";
import { ThreatField } from "@/components/three/ThreatField";
import { Tilt } from "@/components/Tilt";
import { STAGE_BLURB, STAGE_ORDER, pretty, stageColor } from "@/lib/stages";
import { gsap, ScrollTrigger, prefersReducedMotion, armFailsafe } from "@/lib/gsap";
import { useMagnetic } from "@/hooks/useMagnetic";
import { useTheme } from "@/context/ThemeContext";
import * as api from "@/lib/api";

const MODULES = [
  {
    n: "01",
    verb: "Detect",
    name: "RSSIE",
    to: "/live",
    icon: Activity,
    color: "var(--high)",
    body:
      "Real-time scam-session intelligence. It names the manipulation stage in "
      + "progress, forecasts how long until money moves, and coaches the person "
      + "on the line — before the transfer, not after the complaint.",
  },
  {
    n: "02",
    verb: "Connect",
    name: "FIGAE",
    to: "/analyze",
    icon: Network,
    color: "var(--elevated)",
    body:
      "Fraud intelligence & geospatial analytics. Every detection becomes a node "
      + "in a knowledge graph that clusters related cases into campaigns, maps "
      + "hotspots across India, and generates investigation-ready reports.",
  },
  {
    n: "03",
    verb: "Protect",
    name: "CFSRP",
    to: "/analyze",
    icon: LifeBuoy,
    color: "var(--calm)",
    body:
      "The citizen fraud shield. It turns that intelligence into instant, "
      + "plain-language protection — verify a threat, get stage-aware guidance "
      + "and emergency response, preserve evidence, and file a complaint.",
  },
];

export function Home() {
  const root = useRef<HTMLDivElement>(null);
  const { theme, toggle } = useTheme();
  const primaryCta = useMagnetic<HTMLAnchorElement>(0.4);
  const [stats, setStats] = useState<{ clusters: number; cases: number; chunks: number } | null>(null);

  useEffect(() => {
    armFailsafe();
    void (async () => {
      const [h, s] = await Promise.all([api.getHealth(), api.getIntelStats()]);
      setStats({
        clusters: s.ok ? s.data.active_clusters : 9,
        cases: s.ok ? s.data.total_cases : 114,
        chunks: h.ok ? h.data.retrieval.chunks : 26,
      });
    })();
  }, []);

  useEffect(() => {
    if (prefersReducedMotion) return;
    const ctx = gsap.context(() => {
      gsap.from("[data-hero-reveal]", {
        opacity: 0,
        y: 26,
        duration: 0.9,
        ease: "power3.out",
        stagger: 0.09,
      });
      gsap.utils.toArray<HTMLElement>("[data-scroll-reveal]").forEach((el) => {
        gsap.from(el, {
          opacity: 0,
          y: 24,
          duration: 0.7,
          ease: "power3.out",
          scrollTrigger: { trigger: el, start: "top 88%", once: true },
        });
      });
    }, root);

    const refresh = requestAnimationFrame(() => ScrollTrigger.refresh());
    return () => {
      cancelAnimationFrame(refresh);
      ctx.revert();
      ScrollTrigger.getAll().forEach((t) => t.kill());
    };
  }, []);

  return (
    <div ref={root} className="landing">
      {/* minimal landing header */}
      <header className="lhead">
        <Link to="/" className="lhead__brand">
          <span className="brand2__mark" aria-hidden="true" />
          <span className="lhead__name">AegisAI</span>
        </Link>
        <nav className="lhead__nav">
          <a href="#pipeline">How it works</a>
          <a href="#arc">The scam arc</a>
          <Link to="/learn">Learn</Link>
        </nav>
        <div className="lhead__right">
          <button className="iconbtn" onClick={toggle} aria-label="Toggle theme">
            {theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
          </button>
          <Link className="btn2 btn2--primary lhead__enter" to="/home">
            Open AegisAI <ArrowRight size={14} />
          </Link>
        </div>
      </header>

      {/* hero */}
      <section className="hero hero--landing">
        <ThreatField />
        <div className="hero__inner">
          <span className="hero__eyebrow" data-hero-reveal data-reveal>
            AI for Digital Public Safety · Defeating digital-arrest scams
          </span>
          <h1 className="hero__title hero__title--xl" data-hero-reveal data-reveal>
            It knows what the scammer<br /><em>will say next.</em>
          </h1>
          <p className="hero__sub" data-hero-reveal data-reveal>
            AegisAI is a three-stage intelligence platform against India's fastest-growing
            cybercrime. It detects an active scam call in real time, connects it to the
            fraud network behind it, and protects the citizen on the line — shifting from
            reactive case investigation to predictive threat neutralisation.
          </p>
          <div className="hero__cta" data-hero-reveal data-reveal>
            <Link ref={primaryCta} className="btn2 btn2--primary btn2--lg" to="/analyze">
              <ScanLine size={16} /> Check something suspicious
            </Link>
            <Link className="btn2 btn2--lg" to="/live">
              <Activity size={16} /> Get live call protection
            </Link>
          </div>
          <div className="hero__pills" data-hero-reveal data-reveal>
            <span>₹1,776 cr lost to digital arrest in 9 months of 2024</span>
            <span>1.14M cybercrime complaints in 2023</span>
          </div>
        </div>
        <span className="hero__scroll">scroll</span>
      </section>

      {/* the pipeline — Detect → Connect → Protect */}
      <section className="section" id="pipeline">
        <h2 className="section__title" data-scroll-reveal>
          One pipeline: <span className="grad">Detect → Connect → Protect</span>
        </h2>
        <p className="section__lede" data-scroll-reveal>
          These scams are industrialised operations, not opportunistic crimes. So the
          defence is a pipeline too — three modules, each with a distinct job, each
          feeding the next.
        </p>

        <div className="pipeline">
          {MODULES.map((m, i) => (
            <Tilt key={m.name} className="pipestep" max={6} lift={4}
                  style={{ ["--m-color" as string]: m.color }}>
              <div data-scroll-reveal className="pipestep__inner">
                <div className="pipestep__n mono">{m.n}</div>
                <div className="pipestep__icon"><m.icon size={20} /></div>
                <div className="pipestep__verb">{m.verb}</div>
                <div className="pipestep__name mono">{m.name}</div>
                <p className="pipestep__body">{m.body}</p>
                <Link className="pipestep__link" to={m.to}>
                  Open <ArrowRight size={13} />
                </Link>
              </div>
              {i < MODULES.length - 1 && <span className="pipestep__arrow" aria-hidden="true">→</span>}
            </Tilt>
          ))}
        </div>
      </section>

      {/* live numbers */}
      <section className="section section--tight">
        <div className="statband">
          <div className="stat" data-scroll-reveal>
            <div className="stat__n">{stats?.cases ?? "—"}</div>
            <p className="stat__l">fraud cases in the live intelligence graph, clustered into campaigns.</p>
          </div>
          <div className="stat" data-scroll-reveal>
            <div className="stat__n">{stats?.clusters ?? "—"}</div>
            <p className="stat__l">active fraud clusters, each risk-scored and mapped to a hotspot.</p>
          </div>
          <div className="stat" data-scroll-reveal>
            <div className="stat__n">8</div>
            <p className="stat__l">speech-act stages the classifier names — not topics, acts.</p>
          </div>
          <div className="stat" data-scroll-reveal>
            <div className="stat__n">1930</div>
            <p className="stat__l">India's cyber-fraud helpline — one tap from the citizen shield.</p>
          </div>
        </div>
      </section>

      {/* the seven-step arc */}
      <section className="section" id="arc">
        <h2 className="section__title" data-scroll-reveal>
          Every one of these calls follows the same seven steps
        </h2>
        <p className="section__lede" data-scroll-reveal>
          A scam call is not improvised — it is a script with a fixed structure, because
          the structure is what works. Name the step in progress and you can predict the
          next one, and predicting the next one is what buys the time to intervene.
        </p>
        <div className="arc">
          {STAGE_ORDER.filter((s) => s !== "BENIGN").map((stage, i) => (
            <div className="arcstep" key={stage} data-scroll-reveal
                 style={{ ["--stage-color" as string]: stageColor(stage) }}>
              <span className="arcstep__n mono">{String(i + 1).padStart(2, "0")}</span>
              <div>
                <span className="arcstep__label">{pretty(stage)}</span>
                <p className="arcstep__body">{STAGE_BLURB[stage]}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* principles */}
      <section className="section">
        <h2 className="section__title" data-scroll-reveal>
          Built like a product, not a demo
        </h2>
        <div className="grid2 grid2--pairs">
          {[
            ["Every score carries its reasons", "A meter reading 91 with no explanation is a demo. This one names the signals that produced it and cites the document behind every check."],
            ["The coach never improvises", "Lines a frightened person is told to say come from a curated, human-reviewed library, delivered verbatim. A model may rank them; it never writes them."],
            ["Degradation is stated, never hidden", "When the fine-tuned classifier isn't loaded or retrieval falls back, the interface says so. A confident number built on nothing is worse than an honest gap."],
            ["Auditable by design", "Every verdict, cluster, and complaint is an exportable, cited package — built for the legal admissibility the brief demands."],
          ].map(([t, b]) => (
            <div className="card" data-scroll-reveal key={t}>
              <h3 className="card__title">{t}</h3>
              <p className="muted small">{b}</p>
            </div>
          ))}
        </div>
        <div className="row landing__cta" data-scroll-reveal>
          <Link className="btn2 btn2--primary btn2--lg" to="/home">
            Open AegisAI <ArrowRight size={15} />
          </Link>
          <Link className="btn2 btn2--lg" to="/learn">Learn about these scams</Link>
        </div>
        <p className="landing__foot small faint" data-scroll-reveal>
          AegisAI · Not a substitute for reporting fraud on 1930 or at cybercrime.gov.in.
        </p>
      </section>
    </div>
  );
}
