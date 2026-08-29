/**
 * Home — the landing. The argument for AegisAI, told in the order a sceptical
 * reader needs it: the problem is multi-channel, the engine is one, here is
 * how it thinks, here it is thinking, here is why you can check it.
 *
 * Rules this page holds itself to, which are the same rules the product does:
 *
 * **Nothing on it is invented.** The live-call panel is not a mockup — every
 * value in it (stage, threat 88/HIGH, the manipulation weights, the coach
 * line, the 18-second forecast) is read out of `mock/stream.json` at t=36s,
 * the same recorded session the console plays, and the panel says so. The
 * platform figures come from `/api/intel/stats` at load. The two statistics
 * in the hero are attributed. There are no benchmark claims, because a
 * benchmark that has not been run is not a benchmark.
 *
 * **Colour still means something.** The threat ramp appears where a threat is
 * being described and nowhere else. The pipeline's three modules used to be
 * red / amber / green, which spent the ramp's most urgent colour on the word
 * "Detect" — decorative use of the exact colours that carry a reading two
 * screens away.
 *
 * **Motion is decorative only.** Every element is legible with JavaScript
 * disabled and with reduced motion set, and `armFailsafe` rescues any
 * entrance that stalls. A landing that needs animation to be readable fails
 * exactly the users most likely to need this one.
 *
 * This route lives outside the AppShell, so it carries its own header and
 * arms the reveal failsafe itself.
 */

import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  Activity,
  ArrowRight,
  Braces,
  FileText,
  Fingerprint,
  Image as ImageIcon,
  LifeBuoy,
  Link2,
  Mail,
  MessageSquare,
  Mic,
  Moon,
  Network,
  Package,
  Phone,
  QrCode,
  ScanLine,
  Search,
  ShieldCheck,
  Sun,
} from "lucide-react";
import { Logo, LogoMark } from "@/components/brand/Logo";
import { UserMenu } from "@/components/layout/UserMenu";
import { ThreatField } from "@/components/three/ThreatField";
import { STAGE_BLURB, STAGE_ORDER, pretty, stageColor } from "@/lib/stages";
import { gsap, ScrollTrigger, prefersReducedMotion, armFailsafe } from "@/lib/gsap";
import { useMagnetic } from "@/hooks/useMagnetic";
import { useTheme } from "@/context/ThemeContext";
import * as api from "@/lib/api";

/* --------------------------------------------------------------- content */

/** Where the attacker actually is. Deliberately not "channels we support" —
 *  the point of the section is that the surface is one surface. */
const SURFACE = [
  { icon: MessageSquare, label: "SMS" },
  { icon: Phone, label: "Voice calls" },
  { icon: Mail, label: "Email" },
  { icon: QrCode, label: "QR codes" },
  { icon: Link2, label: "Websites" },
  { icon: Fingerprint, label: "UPI IDs" },
  { icon: Package, label: "APKs" },
  { icon: ImageIcon, label: "Screenshots" },
  { icon: Mic, label: "Voice notes" },
  { icon: FileText, label: "PDFs" },
];

/** How the engine thinks, stage by stage. Each line says what that stage
 *  *decides*, not what it is called. */
const PIPELINE = [
  { step: "Understand", body: "Read the bytes. Decide what this actually is — not what it was labelled as." },
  { step: "Extract", body: "Pull out the numbers, UPI IDs, domains and claims nobody had to type in." },
  { step: "Investigate", body: "Run the agents that apply: URL intelligence, number checks, script matching, static APK analysis." },
  { step: "Correlate", body: "Look the entities up in the fraud graph. Isolated indicators become a known campaign or they don't." },
  { step: "Reason", body: "Fuse the evidence into one calibrated figure. Deterministic rules and a trained model — never the language model." },
  { step: "Explain", body: "Name every signal that moved the number, and cite the advisory behind each check." },
  { step: "Protect", body: "Turn the finding into the next action: what to say, what to freeze, who to call." },
];

/** The agent tiers. Names match `agents/registry.py`. */
const TIERS = [
  {
    tier: "Understand",
    icon: ScanLine,
    agents: ["Input classifier", "OCR / vision", "Entity extraction"],
    body: "Decides what the evidence is from its bytes, and pulls the indicators out of it.",
  },
  {
    tier: "Investigate",
    icon: Search,
    agents: ["Script match", "Stage classifier", "Trust passport", "Number intelligence"],
    body: "The specialists. Each one answers a narrow question it can be held to.",
  },
  {
    tier: "Correlate",
    icon: Network,
    agents: ["Graph correlation", "Cluster lookup", "Geospatial"],
    body: "Connects this case to every case before it — the part a single check cannot do.",
  },
  {
    tier: "Judge",
    icon: ShieldCheck,
    agents: ["Threat fusion", "Digital twin", "Explanation"],
    body: "Fuses the findings into one score, forecasts the next move, and writes down why.",
  },
];

/**
 * One frame of the recorded session, read out of `mock/stream.json` at
 * t = 36 s. Kept as literal values with the source named in the copy: a
 * landing page that invents a plausible-looking risk score is doing the exact
 * thing this product exists to detect.
 */
const DEMO_FRAME = {
  t: "00:36",
  caller: "+1-838-224-7719",
  stage: "ISOLATION",
  threat: 88,
  level: "HIGH",
  utterance:
    "Sir ruk jaiye. Ye investigation confidential hai. Aap kisi ko batayenge to "
    + "unko bhi accused list mein daalna padega.",
  tactics: [
    { label: "Fear", weight: 1.0 },
    { label: "Authority", weight: 0.56 },
    { label: "Isolation", weight: 0.28 },
  ],
  forecast: { next: "Verification demand", inSeconds: 18, paymentInSeconds: 54 },
  coach:
    "Say: “I don't discuss anything without my family present.” Then put the "
    + "phone down and go to another person in the house.",
};

/** Why a verdict reads the way it does — the shape of a real explanation. */
const WHY = [
  "Authority impersonation — a claimed identity that failed its own check",
  "Fear induction — a manufactured, immediate consequence",
  "Isolation — an instruction not to tell anyone",
  "Payment to an individual VPA, not an institutional one",
  "A procedure that does not exist in Indian law",
  "Two indicators already linked to a known campaign",
];

const MODULES = [
  {
    n: "01",
    verb: "Detect",
    name: "RSSIE",
    to: "/live",
    icon: Activity,
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
    body:
      "The citizen fraud shield. It turns that intelligence into instant, "
      + "plain-language protection — verify a threat, get stage-aware guidance "
      + "and emergency response, preserve evidence, and file a complaint.",
  },
];

/* The pitch, as data. Two lines; the second is the accent half. Splitting it
   here rather than walking text nodes at runtime keeps the markup something
   you can read, and means the animation has a stable list to stagger over. */
const HERO_PITCH: { text: string; accent: boolean }[] = [
  { text: "It knows what the scammer", accent: false },
  { text: "will say next.", accent: true },
];

/* ------------------------------------------------------------------ page */

export function Home() {
  const root = useRef<HTMLDivElement>(null);
  const { theme, toggle } = useTheme();
  const primaryCta = useMagnetic<HTMLAnchorElement>(0.3);
  const [stats, setStats] = useState<{ clusters: number; cases: number; entities: number } | null>(null);
  const [scrolled, setScrolled] = useState(false);
  const sentinelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    armFailsafe();
    void (async () => {
      const s = await api.getIntelStats();
      if (s.ok) {
        setStats({
          clusters: s.data.active_clusters,
          cases: s.data.total_cases,
          entities: s.data.linked_entities,
        });
      }
    })();
  }, []);

  // The header goes from transparent-over-hero to a settled bar.
  //
  // An IntersectionObserver on a sentinel rather than a scroll listener: the
  // observer is driven by the compositor and fires twice for the whole page
  // (once leaving the top, once returning), where a scroll handler runs on
  // every frame of every scroll to answer the same one-bit question.
  useEffect(() => {
    // Seeded from the current offset first: a reload restores scroll position
    // before the observer's first callback lands, and a bar that starts
    // transparent halfway down the page is a visible flash.
    setScrolled(window.scrollY > 24);
    const sentinel = sentinelRef.current;
    if (!sentinel) return;
    const io = new IntersectionObserver(
      ([entry]) => setScrolled(!entry.isIntersecting),
      { threshold: 0 },
    );
    io.observe(sentinel);
    return () => io.disconnect();
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

      // The pitch assembles itself. Each word swings up out of the page on
      // its own hinge — `rotateX` from below with the origin at its baseline,
      // pulled through a blur — so the line resolves into focus instead of
      // sliding in. `gsap.from` on purpose: the finished state is whatever
      // the stylesheet already says, so nothing here has to be undone, and
      // the words carry `data-reveal` so the failsafe can force them visible
      // if the tween is ever interrupted mid-flight.
      const words = gsap.utils.toArray<HTMLElement>("[data-hero-word]");
      const pitch = gsap.timeline({ delay: 0.12 });
      pitch.from(words, {
        opacity: 0,
        yPercent: 105,
        rotateX: -82,
        filter: "blur(10px)",
        transformOrigin: "50% 100% -12px",
        // Timed to land well inside the 2.5s reveal failsafe: the last word
        // settles at ~1.65s, so a slow frame or two never leaves the headline
        // to be rescued rather than animated.
        duration: 0.95,
        ease: "power4.out",
        stagger: 0.045,
      });

      // Then the promise half takes the charge: a bright pulse running word
      // by word and settling back to the accent. It is the sentence's claim,
      // so it is the thing that lights up.
      //
      // One numeric custom property drives it, rather than tweening `color`
      // and `textShadow` directly: the settled values are `var(--accent)` and
      // a `color-mix()`, neither of which GSAP's colour parser can read, so
      // tweening them would hand back a literal string instead of easing to
      // it. `--charge` is a plain 0..1 that the stylesheet turns into both
      // the brightness and the glow, and it stays theme-correct for free.
      const accent = gsap.utils.toArray<HTMLElement>("[data-accent-word]");
      const charge = (tl: gsap.core.Timeline) =>
        tl
          .to(accent, {
            "--charge": 1,
            duration: 0.24,
            ease: "power2.out",
            stagger: 0.07,
          })
          .to(
            accent,
            {
              "--charge": 0,
              duration: 0.7,
              ease: "power2.inOut",
              stagger: 0.07,
            },
            "<0.12",
          );
      charge(pitch);

      // And once settled it re-fires slowly, so a page left open keeps a
      // pulse without ever becoming the thing you are watching.
      charge(gsap.timeline({ repeat: -1, repeatDelay: 6.5, delay: 7 }));
      gsap.utils.toArray<HTMLElement>("[data-scroll-reveal]").forEach((el) => {
        gsap.from(el, {
          opacity: 0,
          y: 24,
          duration: 0.7,
          ease: "power3.out",
          scrollTrigger: { trigger: el, start: "top 88%", once: true },
        });
      });
      // The pipeline's connecting rail draws itself as the section arrives.
      // Path-drawing on one element, not a stagger of eight — the rail is the
      // narrative, the steps are just where it stops.
      const rail = document.querySelector<HTMLElement>("[data-rail]");
      if (rail) {
        gsap.fromTo(
          rail,
          { scaleY: 0 },
          {
            scaleY: 1,
            ease: "none",
            scrollTrigger: {
              trigger: rail.parentElement,
              start: "top 70%",
              end: "bottom 70%",
              scrub: 0.4,
            },
          },
        );
      }
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
      <a className="skiplink" href="#lmain">Skip to content</a>
      {/* Watched by the header's IntersectionObserver. 24px tall, at the very
          top of the document: once it leaves the viewport the page has moved
          far enough for the bar to settle. */}
      <div ref={sentinelRef} className="landing__sentinel" aria-hidden="true" />

      <header className="lhead" data-scrolled={scrolled || undefined}>
        <Link to="/" className="lhead__brand" aria-label="AegisAI home">
          <Logo size={22} />
        </Link>
        <nav className="lhead__nav" aria-label="Sections">
          <a href="#problem">Platform</a>
          <a href="#thinks">How it works</a>
          <a href="#capabilities">Capabilities</a>
          <a href="#research">Research</a>
          <a href="#security">Security</a>
        </nav>
        {/* §20/§21: the right-hand cluster is a Sign in / Get started pair for a
            visitor and the authenticated profile for everyone else. One
            component decides which, shared with the app shell, so the two
            surfaces cannot disagree about whether you are signed in. */}
        <div className="lhead__right">
          <button
            className="iconbtn"
            onClick={toggle}
            aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
          >
            {theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
          </button>
          <UserMenu tone="landing" />
        </div>
      </header>

      <main id="lmain" tabIndex={-1}>
        {/* ------------------------------------------------------ hero -- */}
        <section className="hero hero--landing">
          <ThreatField />
          <div className="hero__inner">
            {/* The name leads.
                A landing page's h1 is the product, not a slogan — a visitor who
                has never heard of this should be able to answer "what is it
                called and what is it" before reading a word of the pitch. The
                mark is set at 56px above the wordmark rather than beside it:
                inline, at this scale, it reads as a bullet point; stacked, it
                reads as a crest. */}
            <div className="brandlock" data-hero-reveal data-reveal>
              <LogoMark size={58} className="brandlock__mark" />
              <h1 className="brandlock__name">AegisAI</h1>
              <p className="brandlock__desc">
                Agentic AI for digital public safety
              </p>
            </div>

            {/* Still the pitch, still the most important sentence on the page —
                just no longer pretending to be the page's title.

                Split into words so the line can assemble itself rather than
                fade in as a block. The pieces are `aria-hidden` behind one
                `aria-label`: a screen reader gets the sentence, not fourteen
                fragments. It carries `data-reveal` but not `data-hero-reveal`
                — the word tween is its entrance, and stacking the generic
                block fade on top of it only muddies both. */}
            <p
              className="hero__title hero__title--xl herotitle"
              data-reveal
              aria-label={HERO_PITCH.map((l) => l.text).join(" ")}
            >
              {HERO_PITCH.map((line) => (
                <span className="herotitle__line" key={line.text} aria-hidden="true">
                  {line.text.split(" ").map((word, i) => (
                    <span
                      className={
                        line.accent ? "herotitle__word herotitle__word--accent" : "herotitle__word"
                      }
                      key={`${word}-${i}`}
                      data-hero-word
                      data-accent-word={line.accent || undefined}
                      data-reveal
                    >
                      {word}
                    </span>
                  ))}
                </span>
              ))}
            </p>
            <p className="hero__sub" data-hero-reveal data-reveal>
              AegisAI investigates digital threats before they become real-world damage.
              Multimodal evidence, a graph of intelligent agents, and reasoning you can
              audit line by line — turning a suspicious message or a live call into a
              verdict, the reasons behind it, and the next thing to do.
            </p>
            <div className="hero__cta" data-hero-reveal data-reveal>
              <Link ref={primaryCta} className="btn2 btn2--primary btn2--lg" to="/analyze">
                <ScanLine size={16} aria-hidden="true" /> Start an investigation
              </Link>
              <Link className="btn2 btn2--lg" to="/live">
                <Activity size={16} aria-hidden="true" /> Get live call protection
              </Link>
            </div>

            {/* The engine in five words, which is also the page's structure. */}
            <ol className="flow" data-hero-reveal data-reveal aria-label="How an investigation flows">
              {["Evidence", "Agents", "Correlation", "Risk", "Protection"].map((s, i) => (
                <li className="flow__node" key={s} style={{ ["--i" as string]: i }}>
                  <span className="flow__dot" aria-hidden="true" />
                  {s}
                </li>
              ))}
            </ol>

            <div className="hero__pills" data-hero-reveal data-reveal>
              <span>₹1,776 cr lost to digital arrest in 9 months of 2024</span>
              <span>1.14M cybercrime complaints in 2023</span>
            </div>
          </div>
          <span className="hero__scroll" aria-hidden="true">scroll</span>
        </section>

        {/* --------------------------------------------------- problem -- */}
        <section className="section" id="problem">
          <h2 className="section__title" data-scroll-reveal>
            Digital fraud stopped being a single-channel problem
          </h2>
          <p className="section__lede" data-scroll-reveal>
            One operation reaches a person by SMS, moves them to WhatsApp, sends a PDF
            that looks like a warrant, and collects on a UPI ID — and every tool built to
            stop it only ever looks at one of those. The attack is joined up. The defence
            has not been.
          </p>
          <ul className="surface" data-scroll-reveal>
            {SURFACE.map((s) => (
              <li className="surface__item" key={s.label}>
                <s.icon size={17} aria-hidden="true" />
                {s.label}
              </li>
            ))}
          </ul>
        </section>

        {/* -------------------------------------------------- solution -- */}
        <section className="section" id="capabilities">
          <h2 className="section__title" data-scroll-reveal>
            One investigation engine. Every digital threat.
          </h2>
          <p className="section__lede" data-scroll-reveal>
            Anything can become evidence. A screenshot, a transcript, a link, an APK, a
            voice note, a QR code — they all enter the same graph of agents and come out
            the same way: a score, the signals behind it, and what to do.
          </p>
          <div className="pipeline">
            {MODULES.map((m, i) => (
              <div className="pipestep" key={m.name} data-scroll-reveal>
                <div className="pipestep__inner">
                  <div className="pipestep__n mono">{m.n}</div>
                  <div className="pipestep__icon"><m.icon size={20} aria-hidden="true" /></div>
                  <div className="pipestep__verb">{m.verb}</div>
                  <div className="pipestep__name mono">{m.name}</div>
                  <p className="pipestep__body">{m.body}</p>
                  <Link className="pipestep__link" to={m.to}>
                    Open <ArrowRight size={13} aria-hidden="true" />
                  </Link>
                </div>
                {i < MODULES.length - 1 && (
                  <span className="pipestep__arrow" aria-hidden="true">→</span>
                )}
              </div>
            ))}
          </div>
        </section>

        {/* ---------------------------------------------- how it thinks -- */}
        <section className="section" id="thinks">
          <h2 className="section__title" data-scroll-reveal>
            How AegisAI thinks
          </h2>
          <p className="section__lede" data-scroll-reveal>
            Seven decisions, in order. Each one is a step a human investigator would take,
            and each one leaves a record you can read afterwards.
          </p>
          <ol className="think">
            <span className="think__rail" data-rail aria-hidden="true" />
            {PIPELINE.map((p, i) => (
              <li className="think__step" key={p.step} data-scroll-reveal>
                <span className="think__n mono">{String(i + 1).padStart(2, "0")}</span>
                <div>
                  <h3 className="think__name">{p.step}</h3>
                  <p className="think__body">{p.body}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>

        {/* ------------------------------------------------- agent graph -- */}
        <section className="section">
          <h2 className="section__title" data-scroll-reveal>
            A graph of agents, not one model with a big prompt
          </h2>
          <p className="section__lede" data-scroll-reveal>
            Each agent answers one narrow question it can be held to, records how long it
            took, and reports its own status. An agent that degrades is shown degraded —
            it is never quietly rounded up to success.
          </p>
          <div className="tiers">
            {TIERS.map((t, i) => (
              <div className="tier" key={t.tier} data-scroll-reveal>
                <div className="tier__head">
                  <span className="tier__icon"><t.icon size={17} aria-hidden="true" /></span>
                  <h3 className="tier__name">{t.tier}</h3>
                  <span className="tier__n mono">{String(i + 1).padStart(2, "0")}</span>
                </div>
                <p className="tier__body">{t.body}</p>
                <ul className="tier__agents">
                  {t.agents.map((a) => (
                    <li key={a}><Braces size={11} aria-hidden="true" /> {a}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </section>

        {/* --------------------------------------------------- live call -- */}
        <section className="section" id="live">
          <h2 className="section__title" data-scroll-reveal>
            And while the call is still happening
          </h2>
          <p className="section__lede" data-scroll-reveal>
            The panel below is one frame of the recorded session the console plays —
            thirty-six seconds into a digital-arrest call. Every value in it is read from
            that recording, not written for this page.
          </p>

          <div className="callcard" data-scroll-reveal>
            <div className="callcard__head">
              <span className="callcard__live">
                <span className="callcard__dot" aria-hidden="true" /> Live call
              </span>
              <span className="mono callcard__num">{DEMO_FRAME.caller}</span>
              <span className="mono callcard__t">{DEMO_FRAME.t}</span>
            </div>

            <div className="callcard__grid">
              <div className="callcard__left">
                <p className="label">Heard just now</p>
                <blockquote className="callcard__quote">“{DEMO_FRAME.utterance}”</blockquote>

                <p className="label" style={{ marginTop: "var(--s-4)" }}>Tactics detected</p>
                <ul className="tactics">
                  {DEMO_FRAME.tactics.map((t) => (
                    <li key={t.label}>
                      <span className="tactics__label">{t.label}</span>
                      <span className="tactics__track">
                        <i style={{ width: `${t.weight * 100}%` }} />
                      </span>
                    </li>
                  ))}
                </ul>
              </div>

              <div className="callcard__right">
                <div className="callcard__score">
                  <span className="callcard__num2 mono">{DEMO_FRAME.threat}</span>
                  <span className="chip chip--caps" data-risk={DEMO_FRAME.level}>{DEMO_FRAME.level}</span>
                </div>
                <p className="callcard__stage">
                  Stage: <strong>{pretty(DEMO_FRAME.stage)}</strong>
                </p>
                <p className="callcard__forecast">
                  Next likely: <strong>{DEMO_FRAME.forecast.next}</strong> in ~
                  {DEMO_FRAME.forecast.inSeconds}s · money moves in ~
                  {DEMO_FRAME.forecast.paymentInSeconds}s
                </p>
                <div className="callcard__coach">
                  <p className="label">What to say</p>
                  <p className="callcard__coachline">{DEMO_FRAME.coach}</p>
                  <p className="callcard__src">
                    From a curated, human-reviewed library. A model may rank these lines;
                    it never writes them.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* -------------------------------------------------- the arc ---- */}
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

        {/* ------------------------------------------------ correlation -- */}
        <section className="section">
          <div className="split">
            <div data-scroll-reveal>
              <h2 className="section__title">
                One number is a nuisance. Four are an organisation.
              </h2>
              <p className="section__lede">
                Every detection becomes a node. Numbers, UPI IDs, domains and wallets that
                keep reappearing together collapse into a single campaign with a risk
                score, a footprint across states, and a report an investigator can file —
                which is the difference between blocking a caller and dismantling a crew.
              </p>
              <Link className="btn2" to="/intel">
                Open the fraud graph <ArrowRight size={14} aria-hidden="true" />
              </Link>
            </div>
            <div className="statband statband--tall" data-scroll-reveal>
              <div className="stat">
                <div className="stat__n mono">{stats ? stats.cases : "—"}</div>
                <p className="stat__l">fraud cases in the live graph, clustered into campaigns</p>
              </div>
              <div className="stat">
                <div className="stat__n mono">{stats ? stats.clusters : "—"}</div>
                <p className="stat__l">active clusters, each risk-scored and mapped</p>
              </div>
              <div className="stat">
                <div className="stat__n mono">{stats ? stats.entities : "—"}</div>
                <p className="stat__l">linked entities — numbers, UPI IDs, wallets</p>
              </div>
              <div className="stat">
                <div className="stat__n mono">8</div>
                <p className="stat__l">speech-act stages the classifier names — not topics, acts</p>
              </div>
            </div>
          </div>
        </section>

        {/* ------------------------------------------------ explainable -- */}
        <section className="section" id="research">
          <div className="split split--rev">
            <div className="whycard" data-scroll-reveal>
              <p className="label">Why this reads 93</p>
              <ul className="whylist">
                {WHY.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
              <p className="whycard__foot">
                Each line cites the advisory behind it — traceable to a document, not to a
                model's confidence.
              </p>
            </div>
            <div data-scroll-reveal>
              <h2 className="section__title">A number nobody can check is not evidence</h2>
              <p className="section__lede">
                The language model explains, extracts and ranks. It never scores. The
                figure comes from a calibrated classifier, deterministic rules, and what
                the graph already knows — and every one of those contributions is named
                and weighted where you can see it.
              </p>
              <Link className="btn2" to="/model">
                Read the model card <ArrowRight size={14} aria-hidden="true" />
              </Link>
            </div>
          </div>
        </section>

        {/* -------------------------------------------------- security --- */}
        <section className="section" id="security">
          <h2 className="section__title" data-scroll-reveal>
            Built like a product, not a demo
          </h2>
          <div className="grid2 grid2--pairs">
            {[
              ["Every score carries its reasons", "A meter reading 91 with no explanation is a demo. This one names the signals that produced it and cites the document behind every check."],
              ["The coach never improvises", "Lines a frightened person is told to say come from a curated, human-reviewed library, delivered verbatim. A model may rank them; it never writes them."],
              ["Degradation is stated, never hidden", "When the fine-tuned classifier isn't loaded or retrieval falls back, the interface says so. A confident number built on nothing is worse than an honest gap."],
              ["Evidence is data, never instructions", "Text lifted out of a screenshot can contain an instruction aimed at us. It is quoted into the models as untrusted input and never followed."],
              ["Uploads are handled as hostile", "Files are validated by magic bytes, not extension. An APK is analysed statically in a network-less container and never executed."],
              ["Auditable by design", "Every verdict, cluster, and complaint is an exportable, cited package — built for the legal admissibility the brief demands."],
            ].map(([t, b]) => (
              <div className="card" data-scroll-reveal key={t}>
                <h3 className="card__title">{t}</h3>
                <p className="muted small">{b}</p>
              </div>
            ))}
          </div>
        </section>

        {/* -------------------------------------------------------- CTA -- */}
        <section className="section section--cta">
          <div className="cta" data-scroll-reveal>
            <h2 className="cta__title">Check something suspicious</h2>
            <p className="cta__body">
              It takes one paste. Nothing is stored unless you choose to save it.
            </p>
            <div className="row" style={{ justifyContent: "center" }}>
              <Link className="btn2 btn2--primary btn2--lg" to="/analyze">
                Start an investigation <ArrowRight size={15} aria-hidden="true" />
              </Link>
              <Link className="btn2 btn2--lg" to="/learn">Learn how these scams work</Link>
            </div>
          </div>
        </section>
      </main>

      <footer className="lfoot">
        <Logo size={18} />
        <p className="lfoot__note">
          AegisAI · Not a substitute for reporting fraud on{" "}
          <strong className="mono">1930</strong> or at{" "}
          <a href="https://cybercrime.gov.in" target="_blank" rel="noreferrer">
            cybercrime.gov.in
          </a>
          .
        </p>
      </footer>
    </div>
  );
}
