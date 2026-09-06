/**
 * The last screen, and the footer.
 *
 * The page gets quieter here on purpose. The background field is dimmed by a
 * wash, the type is the largest it has been since the hero, and there is one
 * primary action. Everything the page has been showing converges into the
 * single sentence that says what to do about it.
 *
 * The footer carries the one piece of information this product must never
 * imply it replaces: the national helpline and the national portal. A
 * capstone that positions itself as a substitute for reporting fraud would be
 * doing harm; saying so plainly, in the footer of every page, is the cheapest
 * possible correction.
 *
 * The platform figures come from `/api/intel/stats` at load. If that request
 * fails — offline, or the API down — the figures render as em dashes rather
 * than as zeros. A zero is a claim; a dash is an absence.
 */

import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, ScanLine } from "lucide-react";
import { Logo } from "@/components/brand/Logo";
import { useMagnetic } from "@/hooks/useMagnetic";
import {
  gsap,
  split,
  fontsReady,
  DUR,
  EASE,
  reduced,
  refreshSoon,
} from "@/lib/landing-motion";
import * as api from "@/lib/api";

export function ClosingSection() {
  const root = useRef<HTMLElement>(null);
  const cta = useMagnetic<HTMLAnchorElement>(0.34);
  const [stats, setStats] = useState<{ clusters: number; cases: number; entities: number } | null>(
    null,
  );

  useEffect(() => {
    let live = true;
    void (async () => {
      const s = await api.getIntelStats();
      if (live && s.ok) {
        setStats({
          clusters: s.data.active_clusters,
          cases: s.data.total_cases,
          entities: s.data.linked_entities,
        });
      }
    })();
    return () => {
      live = false;
    };
  }, []);

  useEffect(() => {
    const el = root.current;
    if (!el || reduced()) return;
    let cancelled = false;
    const teardown: (() => void)[] = [];

    void fontsReady().then(() => {
      if (cancelled) return;
      const ctx = gsap.context(() => {
        const h = split(el.querySelector("[data-c-h2]"), "lines");
        const tl = gsap.timeline({
          scrollTrigger: { trigger: el, start: "top 68%", once: true },
        });
        tl.from(h.lines, {
          yPercent: 118,
          opacity: 0,
          filter: "blur(14px)",
          duration: DUR.cinema,
          ease: EASE.out,
          stagger: 0.1,
          onComplete: () => h.revert(),
        })
          .from("[data-c-sub]", { opacity: 0, y: 22, filter: "blur(9px)", duration: DUR.reveal }, "-=1.1")
          .from("[data-c-act] > *", { opacity: 0, y: 18, duration: DUR.reveal, stagger: 0.1 }, "-=0.5")
          .from("[data-c-stat]", { opacity: 0, y: 14, duration: DUR.quick, stagger: 0.08 }, "-=0.4");

        // The wash that quietens the background under this section, tied to
        // the scroll so the page dims as it arrives rather than at a threshold.
        gsap.fromTo(
          "[data-c-veil]",
          { opacity: 0 },
          {
            opacity: 1,
            ease: "none",
            scrollTrigger: { trigger: el, start: "top bottom", end: "top 40%", scrub: 0.5 },
          },
        );
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
    <>
      <section className="lp-section lp-close" ref={root}>
        <div className="lp-close__veil" data-c-veil aria-hidden="true" />
        <div className="lp-shell lp-shell--narrow lp-close__inner">
          <h2 className="lp-h2 lp-h2--big" data-c-h2>
            Don't wait for the threat <em>to become damage.</em>
          </h2>
          <p className="lp-close__sub" data-c-sub>
            Paste a message, a link or a number and watch the investigation run. Nothing
            is stored unless you choose to save it.
          </p>
          <div className="lp-close__act" data-c-act>
            <Link ref={cta} className="lp-btn lp-btn--primary" to="/analyze">
              <ScanLine size={16} aria-hidden="true" /> Start an investigation
            </Link>
            <Link className="lp-btn lp-btn--ghost" to="/live">
              Get live call protection <ArrowRight size={15} aria-hidden="true" />
            </Link>
          </div>

          <dl className="lp-close__stats">
            <div data-c-stat>
              <dt className="lp-mono">{stats ? stats.cases : "—"}</dt>
              <dd>cases in the live graph, clustered into campaigns</dd>
            </div>
            <div data-c-stat>
              <dt className="lp-mono">{stats ? stats.clusters : "—"}</dt>
              <dd>active clusters, each risk-scored and mapped</dd>
            </div>
            <div data-c-stat>
              <dt className="lp-mono">{stats ? stats.entities : "—"}</dt>
              <dd>linked entities — numbers, handles, domains</dd>
            </div>
          </dl>
        </div>
      </section>

      <footer className="lp-foot">
        <div className="lp-shell lp-foot__inner">
          <div className="lp-foot__brand">
            <Logo size={19} />
            <p>
              Agentic AI for digital public safety. A final-year capstone and research
              project — built to be checked, not to be believed.
            </p>
          </div>

          <nav className="lp-foot__nav" aria-label="Footer">
            <div>
              <p className="lp-label">Platform</p>
              <Link to="/analyze">Analyze</Link>
              <Link to="/live">Live protection</Link>
              <Link to="/intel">Fraud intel</Link>
            </div>
            <div>
              <p className="lp-label">Research</p>
              <Link to="/model">Model card</Link>
              <Link to="/learn">How these scams work</Link>
            </div>
            <div>
              <p className="lp-label">Help now</p>
              <a href="tel:1930">Call 1930</a>
              <a href="https://cybercrime.gov.in" target="_blank" rel="noreferrer">
                cybercrime.gov.in
              </a>
            </div>
          </nav>
        </div>

        <div className="lp-shell lp-foot__note">
          <p>
            AegisAI is not a substitute for reporting fraud on{" "}
            <strong className="lp-mono">1930</strong> or at{" "}
            <a href="https://cybercrime.gov.in" target="_blank" rel="noreferrer">
              cybercrime.gov.in
            </a>
            . If money has already moved, report it there first — the first few hours are
            what decide whether it can be recalled.
          </p>
        </div>
      </footer>
    </>
  );
}
