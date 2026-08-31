/**
 * Why this is technically credible.
 *
 * Eight technologies, and for each one what it is actually doing here and
 * what it is not allowed to do. That second half is the section: a logo wall
 * says "we used these", a limitation says "we understand these", and only one
 * of those is evidence of engineering.
 *
 * It is built as a selector rather than a grid of cards — pick a technology
 * and the panel beside it changes — because eight paragraphs laid out at once
 * is a wall of text, and the reader only wants the one they are sceptical
 * about. Keyboard-operable, with the panel announced on change.
 */

import { useEffect, useRef, useState } from "react";
import {
  gsap,
  split,
  fontsReady,
  DUR,
  EASE,
  reduced,
  refreshSoon,
} from "@/lib/landing-motion";

interface Tech {
  id: string;
  name: string;
  role: string;
  /** The honest half. Every entry has one. */
  limit: string;
}

const TECH: Tech[] = [
  {
    id: "agentic",
    name: "Agentic AI",
    role: "Thirteen specialists behind one orchestrator, each with a version string, a declared feature set, a timing record and its own degradation path.",
    limit: "Orchestration adds failure modes a monolith does not have. Every agent therefore reports its own status, and a degraded agent is shown degraded rather than rounded up to success.",
  },
  {
    id: "multimodal",
    name: "Multimodal AI",
    role: "Text, speech, images, documents and installers enter through one classifier that decides what a file is from its bytes rather than its extension.",
    limit: "OCR on a compressed screenshot of a screenshot is unreliable, and the pipeline treats low-confidence extraction as low-confidence evidence instead of quietly promoting it.",
  },
  {
    id: "llm",
    name: "Language models",
    role: "Extraction, ranking and the written explanation of a verdict. They turn a set of signals into a sentence a frightened person can act on.",
    limit: "They never produce the score. A number a generative model felt like emitting cannot be calibrated and cannot be defended when it is wrong.",
  },
  {
    id: "rag",
    name: "Retrieval",
    role: "Advisories, playbooks and the coaching library are retrieved and cited, so every claim in an explanation points at a document.",
    limit: "Retrieved text is untrusted data. It is quoted into prompts as evidence and never followed as instruction — the same rule that applies to a scammer's own screenshot.",
  },
  {
    id: "graph",
    name: "Knowledge graphs",
    role: "Numbers, handles, domains, installers and cases as one graph, clustered into campaigns with a risk score and a geographic footprint.",
    limit: "Co-occurrence is not proof of a shared operator. Cluster membership is evidence with a weight, not a verdict, and the report says which is which.",
  },
  {
    id: "ml",
    name: "Machine learning",
    role: "A fine-tuned transformer classifies the manipulation stage of an utterance, and a calibrated fusion model turns the agents' findings into one figure.",
    limit: "Hindi and Hinglish are strong; short English inputs are borderline, and the aggregate score is what rewards accumulated pressure over many turns rather than any single line.",
  },
  {
    id: "intel",
    name: "Threat intelligence",
    role: "Numbering-plan rules, agency directories, registrar and certificate data, and published advisories, checked at request time with cached fallbacks.",
    limit: "Every one of those is a live dependency, so every one has a fallback that still answers and records a tag saying it was used.",
  },
  {
    id: "xai",
    name: "Explainable AI",
    role: "Itemised, weighted contributions behind every figure, each naming the check that produced it and the document that check cites.",
    limit: "An explanation is a description of the model's inputs, not a proof of its reasoning. It is offered so a human can disagree with it — which is the point.",
  },
];

export function ResearchSection() {
  const root = useRef<HTMLElement>(null);
  const [active, setActive] = useState(TECH[0].id);
  const tech = TECH.find((t) => t.id === active) ?? TECH[0];

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
        gsap.from("[data-r-item]", {
          opacity: 0,
          x: -22,
          filter: "blur(8px)",
          duration: DUR.quick,
          stagger: 0.055,
          ease: EASE.out,
          scrollTrigger: { trigger: "[data-r-list]", start: "top 84%", once: true },
        });
        gsap.from("[data-r-panel]", {
          opacity: 0,
          x: 26,
          filter: "blur(10px)",
          duration: DUR.reveal,
          ease: EASE.out,
          scrollTrigger: { trigger: "[data-r-panel]", start: "top 84%", once: true },
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

  /* The panel's contents change on selection, so they get their own small
     entrance — without it the swap is a jump cut in the middle of a page that
     never cuts. Reduced motion skips it and the text simply changes. */
  const panelRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = panelRef.current;
    if (!el || reduced()) return;
    const tween = gsap.fromTo(
      el.querySelectorAll("[data-r-swap]"),
      { opacity: 0, y: 10, filter: "blur(6px)" },
      { opacity: 1, y: 0, filter: "blur(0px)", duration: DUR.quick, stagger: 0.06, ease: EASE.out },
    );
    return () => {
      tween.kill();
    };
  }, [active]);

  return (
    <section className="lp-section" id="research" ref={root}>
      <div className="lp-shell">
        <p className="lp-eyebrow">
          <span className="lp-eyebrow__n">09</span> Research
        </p>
        <h2 className="lp-h2" data-r-h2>
          Eight technologies, and <em>what each one is not allowed to do.</em>
        </h2>

        <div className="lp-tech">
          <ul className="lp-tech__list" data-r-list>
            {TECH.map((t) => (
              <li key={t.id} data-r-item>
                <button
                  type="button"
                  className="lp-tech__btn"
                  aria-pressed={t.id === active}
                  onClick={() => setActive(t.id)}
                  onMouseEnter={() => setActive(t.id)}
                  onFocus={() => setActive(t.id)}
                >
                  <span className="lp-tech__dot" aria-hidden="true" />
                  {t.name}
                </button>
              </li>
            ))}
          </ul>

          <div className="lp-tech__panel lp-card" data-r-panel ref={panelRef} aria-live="polite">
            <h3 className="lp-h3" data-r-swap>
              {tech.name}
            </h3>
            <p className="lp-label lp-tech__lbl" data-r-swap>
              What it does here
            </p>
            <p className="lp-tech__body" data-r-swap>
              {tech.role}
            </p>
            <p className="lp-label lp-tech__lbl" data-r-swap>
              What it is not allowed to do
            </p>
            <p className="lp-tech__body lp-tech__limit" data-r-swap>
              {tech.limit}
            </p>
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
