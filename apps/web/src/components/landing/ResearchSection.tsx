/**
 * Why this is technically credible.
 *
 * Eight technologies, and for each one what it is actually doing here and
 * what it is not allowed to do. That second half is the section: a logo wall
 * says "we used these", a limitation says "we understand these", and only one
 * of those is evidence of engineering.
 *
 * **Read by scrolling.** The eight are stacked panels; a sidebar stays on
 * screen beside them, marks the one in view, fills as the reader goes, and
 * jumps to any of them on click. It replaced a hover selector that showed one
 * paragraph at a time and gave no sense of where the reader was in the eight.
 * The sidebar is a reading of the scroll position (one ScrollTrigger per
 * panel), not an animation, so it works under reduced motion too.
 *
 * **Figures are read, not typed.** Where the running system can report a
 * number — how many agents are registered, which classifier is serving and
 * what it measured, how large the retrieval corpus and the intelligence store
 * are — the panel reads it from `/api/health` at load and says so. Where it
 * cannot, the panel shows no figure rather than a remembered one.
 *
 * **Every claim was checked against the code** on 2026-10-21. The previous copy
 * said a fine-tuned transformer classifies the stage (the lexical model serves
 * — the transformer failed the leak-free gate), that fusion is calibrated (it
 * is not yet), that threat intelligence reads registrar and certificate data
 * (nothing does), and that there are thirteen agents (there are eight).
 */

import { useEffect, useRef, useState } from "react";
import {
  gsap,
  ScrollTrigger,
  split,
  fontsReady,
  DUR,
  EASE,
  reduced,
  refreshSoon,
} from "@/lib/landing-motion";
import type { Health } from "@/lib/api";
import { useLiveHealth } from "@/components/landing/live";

interface Figure {
  value: string;
  caption: string;
}

interface Tech {
  id: string;
  name: string;
  role: string;
  /** The honest half. Every entry has one. */
  limit: string;
  /** What the running system can say about it, if anything. */
  figure?: (h: Health) => Figure | null;
}

const TECH: Tech[] = [
  {
    id: "agentic",
    name: "Agentic AI",
    role: "Specialist agents in four stages behind one orchestrator, each with a version string, a timing record and its own degradation path.",
    limit: "Orchestration adds failure modes a monolith does not have. Every agent therefore reports its own status, and a degraded agent is shown degraded rather than rounded up to success.",
    figure: (h) => {
      if (!h.agents) return null;
      const n = Object.values(h.agents.agents).reduce((a, l) => a + l.length, 0);
      return { value: `${n} agents`, caption: `registered in ${h.agents.stages.length} stages: ${h.agents.stages.join(" → ")}` };
    },
  },
  {
    id: "multimodal",
    name: "Multimodal AI",
    role: "Text, speech and images enter through one classifier that decides what a file is from its bytes rather than its extension, then go to the reader that handles them — OCR for images, Whisper for audio.",
    limit: "When a reader is not installed, the answer says so — ocr:unavailable, asr:unavailable — instead of returning a confident verdict on an empty read.",
  },
  {
    id: "llm",
    name: "Language models",
    role: "The written explanation of a finished verdict: three plain sentences that turn the signals behind a score into something a frightened person can act on.",
    limit: "Its instructions forbid it to change, dispute or re-derive the score. A number a generative model felt like emitting could not be calibrated, and could not be defended when it is wrong.",
    figure: (h) => ({
      value: h.llm.backend,
      caption: h.llm.configured ? "explainer backend, configured" : "explainer backend, not configured",
    }),
  },
  {
    id: "rag",
    name: "Retrieval",
    role: "Advisories and scam playbooks are retrieved and cited, so a finding can point at the passage it rests on.",
    limit: "It can only cite what is in the corpus. A scam pattern nobody has written up yet has nothing to cite.",
    figure: (h) => ({
      value: `${h.retrieval.chunks} passages`,
      caption: `from ${h.retrieval.documents.length} curated documents · ${h.retrieval.backend} retrieval`,
    }),
  },
  {
    id: "graph",
    name: "Knowledge graphs",
    role: "Phone numbers, UPI handles, wallets and cases as one graph, clustered into campaigns with a risk score and a footprint across states.",
    limit: "Co-occurrence is not proof of a shared operator: cluster membership is evidence with a weight, not a verdict. The cases in the demo store are synthetic.",
    figure: (h) =>
      h.intel
        ? { value: `${h.intel.clusters} campaigns`, caption: `over ${h.intel.cases} cases and ${h.intel.entities} linked identifiers · synthetic demo store` }
        : null,
  },
  {
    id: "ml",
    name: "Machine learning",
    role: "A stage classifier labels which stage of the scam script each line is at, and fusion turns the agents' findings into one figure. What serves is whatever passes a leak-free promotion gate.",
    limit: "The fine-tuned transformer failed that gate — its published score had been measured on its own training data — so the lexical model serves. Fusion is not yet calibrated, and short English inputs are borderline.",
    figure: (h) => {
      const f1 = h.classifier.comparison?.[h.classifier.backend]?.macro_f1;
      return {
        value: f1 != null ? `macro-F1 ${f1.toFixed(3)}` : h.classifier.backend,
        caption: `${h.classifier.backend} classifier serving${h.classifier.reason ? ` — ${h.classifier.reason}` : ""}`,
      };
    },
  },
  {
    id: "intel",
    name: "Threat intelligence",
    role: "Numbering-plan rules, a reported-number list, and the trust passport's checks of what a claimed agency would and would not do — all local, with no live lookup in the request path.",
    limit: "The reported-number list shipped here is a small, clearly synthetic sample; a deployment would sync it from the DoT/TRAI and NCRB feeds.",
  },
  {
    id: "xai",
    name: "Explainable AI",
    role: "Itemised, weighted contributions behind every figure, each naming the check that produced it and, where one exists, the document it cites.",
    limit: "An explanation is a description of the model's inputs, not a proof of its reasoning. It is offered so a human can disagree with it — which is the point.",
    figure: (h) => ({ value: `${h.coach.lines} lines`, caption: "in the human-reviewed coaching library — a model may rank them, never write them" }),
  },
];

/** Where a panel lands when chosen: clear of the bar, with room to breathe. */
const LAND = 110;

export function ResearchSection() {
  const root = useRef<HTMLElement>(null);
  const health = useLiveHealth();
  const [active, setActive] = useState(0);

  /* --- which panel is being read --------------------------------------
     A reading of the scroll position, so it runs under reduced motion too:
     nothing here moves anything. */
  useEffect(() => {
    const el = root.current;
    if (!el) return;
    const panels = gsap.utils.toArray<HTMLElement>("[data-r-panel]", el);
    const column = el.querySelector<HTMLElement>(".lp-tech__panels");
    if (!column || !panels.length) return;
    // The reading line sits just below where a chosen panel lands, in pixels
    // rather than as a share of the screen: a panel picked from the sidebar
    // must be the one the sidebar then marks, whatever the screen height.
    const LINE = LAND + 80;
    // The current panel is the last one whose top has crossed the line. One
    // trigger over the whole column, asked on every update, rather than one
    // per panel told only when it is entered: those left the sidebar stale in
    // the gap between two panels and after a long jump.
    const read = () => {
      let i = 0;
      panels.forEach((p, k) => {
        if (p.getBoundingClientRect().top <= LINE) i = k;
      });
      setActive(i);
    };
    const trigger = ScrollTrigger.create({
      trigger: column,
      start: `top ${LINE}px`,
      end: `bottom ${LINE}px`,
      onUpdate: read,
      onToggle: read,
      onRefresh: read,
    });
    refreshSoon();
    return () => trigger.kill();
  }, []);

  /* On a narrow screen the sidebar is a strip that scrolls sideways; keep the
     current one in it. Horizontal only — scrolling the page from here would
     fight the reader. */
  useEffect(() => {
    const list = root.current?.querySelector<HTMLElement>(".lp-tech__list");
    const btn = list?.querySelectorAll<HTMLElement>(".lp-tech__btn")[active];
    if (!list || !btn || list.scrollWidth <= list.clientWidth) return;
    // From rectangles, not `offsetLeft`: each item keeps the transform its
    // entrance left on it, which makes the item the button's offset parent
    // and `offsetLeft` a constant 0.
    const left = list.scrollLeft + btn.getBoundingClientRect().left - list.getBoundingClientRect().left - 24;
    list.scrollTo({ left, behavior: reduced() ? "auto" : "smooth" });
  }, [active]);

  /* --- the entrance ---------------------------------------------------- */
  useEffect(() => {
    const el = root.current;
    if (!el || reduced()) return;
    let cancelled = false;
    const teardown: (() => void)[] = [];

    void fontsReady().then(() => {
      if (cancelled) return;
      const ctx = gsap.context(() => {
        const h = split(el.querySelector("[data-r-h2]"), "lines");
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
        gsap.from("[data-r-lede]", {
          opacity: 0,
          y: 22,
          filter: "blur(8px)",
          duration: DUR.reveal,
          ease: EASE.out,
          scrollTrigger: { trigger: "[data-r-lede]", start: "top 88%", once: true },
        });
        gsap.from("[data-r-item]", {
          opacity: 0,
          x: -18,
          duration: DUR.quick,
          stagger: 0.05,
          ease: EASE.out,
          scrollTrigger: { trigger: "[data-r-side]", start: "top 84%", once: true },
        });
        gsap.utils.toArray<HTMLElement>("[data-r-panel]").forEach((p) => {
          gsap.from(p, {
            opacity: 0,
            y: 30,
            filter: "blur(8px)",
            duration: DUR.reveal,
            ease: EASE.out,
            clearProps: "filter,transform",
            scrollTrigger: { trigger: p, start: "top 88%", once: true },
          });
        });
      }, el);
      teardown.push(() => ctx.revert());
      refreshSoon();
    });

    return () => {
      cancelled = true;
      teardown.forEach((fn) => fn());
    };
  }, []);

  const goTo = (i: number) => {
    const p = root.current?.querySelectorAll<HTMLElement>("[data-r-panel]")[i];
    if (!p) return;
    window.scrollTo({
      top: p.getBoundingClientRect().top + window.scrollY - LAND,
      behavior: reduced() ? "auto" : "smooth",
    });
  };

  return (
    <section className="lp-section" id="research" ref={root}>
      <div className="lp-shell">
        <p className="lp-eyebrow">
          <span className="lp-eyebrow__n">09</span> Research
        </p>
        <h2 className="lp-h2" data-r-h2>
          Eight technologies, and <em>what each one is not allowed to do.</em>
        </h2>
        <p className="lp-lede" data-r-lede>
          Scroll through them. Where the running system can report a figure, it is
          read from it as this page loads — not typed into the page.
        </p>

        <div className="lp-tech">
          <nav className="lp-tech__side" data-r-side aria-label="Technologies">
            <div className="lp-tech__progress" aria-hidden="true">
              <i style={{ ["--p" as string]: (active + 1) / TECH.length }} />
            </div>
            <ol className="lp-tech__list">
              {TECH.map((t, i) => (
                <li key={t.id} data-r-item>
                  <button
                    type="button"
                    className="lp-tech__btn"
                    data-state={i < active ? "done" : i === active ? "active" : undefined}
                    aria-current={i === active ? "true" : undefined}
                    onClick={() => goTo(i)}
                  >
                    <span className="lp-tech__n lp-mono">{String(i + 1).padStart(2, "0")}</span>
                    {t.name}
                  </button>
                </li>
              ))}
            </ol>
            <p className="lp-tech__status lp-mono">
              <span data-live={health ? "" : undefined} aria-hidden="true" />
              {health ? "Figures read live from /api/health" : "Live figures unavailable — the API did not answer"}
            </p>
          </nav>

          <div className="lp-tech__panels">
            {TECH.map((t, i) => {
              const fig = health && t.figure ? t.figure(health) : null;
              return (
                <article
                  key={t.id}
                  className="lp-tech__panel lp-card"
                  data-r-panel
                  data-active={i === active || undefined}
                  id={`tech-${t.id}`}
                >
                  <header className="lp-tech__phead">
                    <span className="lp-tech__pn lp-mono">
                      {String(i + 1).padStart(2, "0")} / {String(TECH.length).padStart(2, "0")}
                    </span>
                    <h3 className="lp-h3">{t.name}</h3>
                  </header>

                  {fig && (
                    <div className="lp-tech__fig">
                      <b className="lp-mono">{fig.value}</b>
                      <span>{fig.caption}</span>
                      <em className="lp-mono">live</em>
                    </div>
                  )}

                  <div className="lp-tech__cols">
                    <div>
                      <p className="lp-label lp-tech__lbl">What it does here</p>
                      <p className="lp-tech__body">{t.role}</p>
                    </div>
                    <div>
                      <p className="lp-label lp-tech__lbl">What it is not allowed to do</p>
                      <p className="lp-tech__body lp-tech__limit">{t.limit}</p>
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        </div>

        <p className="lp-note">
          <strong>No claim without a measurement.</strong> Latency that has not been
          measured is not called real-time, and a capability that has not been evaluated
          is not advertised. Where a figure exists, this page says where it came from.
        </p>
      </div>
    </section>
  );
}
