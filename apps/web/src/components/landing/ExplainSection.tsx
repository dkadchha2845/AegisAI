/**
 * "Don't just tell me it's dangerous. Show me why."
 *
 * A meter reading 88 with nothing behind it is a demo. This section is the
 * receipt: the claimed identity, the four checks that were run against it,
 * the document each one cites, and the sentence that follows from all of it.
 *
 * **Why the sources are on the page and not in a tooltip.** The product's
 * claim is legal admissibility — a verdict an investigator can file. A citation
 * that only appears on hover is a citation a printout does not have. Every
 * line here carries the document it came from, at the size the line is set in,
 * because that is what "auditable" has to mean to be worth saying.
 *
 * The checks reveal one at a time as the section arrives, each one striking
 * through the claim a little more, and the conclusion resolves last — the
 * order a reader would reach it in on their own.
 */

import { useEffect, useRef } from "react";
import { Check, FileText, X } from "lucide-react";
import { Link } from "react-router-dom";
import {
  gsap,
  split,
  fontsReady,
  DUR,
  EASE,
  reduced,
  refreshSoon,
} from "@/lib/landing-motion";
import { PASSPORT } from "@/components/landing/session";

/** What a reader gets to keep, beyond the number. */
const GUARANTEES = [
  {
    title: "Every score carries its reasons",
    body: "The contributions that produced the figure are itemised and weighted, and each one names the check it came from.",
  },
  {
    title: "Every check cites a document",
    body: "A TRAI numbering rule, an MHA advisory, an agency directory — traceable to a source, not to a model's confidence.",
  },
  {
    title: "Degradation is stated, never hidden",
    body: "When the fine-tuned classifier is not loaded, or retrieval falls back, the interface says so and tags the response.",
  },
  {
    title: "The whole package exports",
    body: "Verdict, evidence, citations and the graph context leave as one cited bundle an investigator can file.",
  },
];

export function ExplainSection() {
  const root = useRef<HTMLElement>(null);

  useEffect(() => {
    const el = root.current;
    if (!el || reduced()) return;
    let cancelled = false;
    const teardown: (() => void)[] = [];

    void fontsReady().then(() => {
      if (cancelled) return;
      const ctx = gsap.context(() => {
        const h = split(el.querySelector("[data-x-h2]"), "lines");
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

        /* The receipt assembles: the claim, then each failing check struck in
           turn, then the conclusion. A stagger rather than a scrub — this one
           wants to be read at reading speed, not at scroll speed. */
        const tl = gsap.timeline({
          scrollTrigger: { trigger: "[data-x-receipt]", start: "top 78%", once: true },
        });
        tl.from("[data-x-claim]", { opacity: 0, y: 20, filter: "blur(10px)", duration: DUR.reveal, ease: EASE.out })
          .from(
            "[data-x-check]",
            { opacity: 0, x: -26, filter: "blur(8px)", duration: DUR.reveal, stagger: 0.14, ease: EASE.out },
            "-=0.35",
          )
          .from("[data-x-trust] i", { scaleX: 0, transformOrigin: "left", duration: DUR.slow, ease: EASE.out }, "-=0.7")
          .from("[data-x-verdict]", { opacity: 0, y: 22, filter: "blur(10px)", duration: DUR.slow, ease: EASE.out }, "-=0.3");

        gsap.from("[data-x-g]", {
          opacity: 0,
          y: 26,
          filter: "blur(9px)",
          duration: DUR.reveal,
          stagger: 0.1,
          ease: EASE.out,
          scrollTrigger: { trigger: "[data-x-grid]", start: "top 86%", once: true },
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
    <section className="lp-section" id="explain" ref={root}>
      <div className="lp-shell">
        <p className="lp-eyebrow">
          <span className="lp-eyebrow__n">08</span> Explainability
        </p>
        <h2 className="lp-h2" data-x-h2>
          Don't just tell me it's dangerous. <em>Show me why.</em>
        </h2>

        <div className="lp-receipt" data-x-receipt>
          <div className="lp-receipt__claim" data-x-claim>
            <p className="lp-label">Claimed identity</p>
            <p className="lp-receipt__who">{PASSPORT.claimed}</p>
            <div className="lp-receipt__trust">
              <span className="lp-label">Trust after checks</span>
              <span className="lp-receipt__bar" data-x-trust>
                <i style={{ ["--w" as string]: `${PASSPORT.trust}%` }} />
              </span>
              <b className="lp-mono">{PASSPORT.trust}%</b>
            </div>
          </div>

          <ul className="lp-receipt__checks">
            {PASSPORT.checks.map((c) => (
              <li key={c.name} data-x-check>
                <span className="lp-receipt__x" aria-hidden="true">
                  <X size={12} strokeWidth={2.6} />
                </span>
                <div>
                  <b>{c.name}</b>
                  <em>{c.detail}</em>
                  <span className="lp-receipt__src lp-mono">
                    <FileText size={10} aria-hidden="true" /> {c.source}
                  </span>
                </div>
              </li>
            ))}
          </ul>

          <p className="lp-receipt__verdict" data-x-verdict>
            Four checks, four sources, four failures. <em>This caller is not who they
            say they are</em> — and the sentence you just read is the one the report
            carries, with those four citations attached to it.
          </p>
        </div>

        <div className="lp-guar" data-x-grid>
          {GUARANTEES.map((g) => (
            <article className="lp-card lp-guar__card" key={g.title} data-x-g>
              <span className="lp-guar__tick" aria-hidden="true">
                <Check size={13} strokeWidth={2.6} />
              </span>
              <h3 className="lp-card__title">{g.title}</h3>
              <p className="lp-card__body">{g.body}</p>
            </article>
          ))}
        </div>

        <p className="lp-note">
          <Link className="lp-link" to="/model">
            Read the model card
          </Link>{" "}
          — what the classifier was trained on, how it was evaluated, and what it is
          known to be bad at.
        </p>
      </div>
    </section>
  );
}
