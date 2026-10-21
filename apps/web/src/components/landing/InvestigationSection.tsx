/**
 * One investigation, running, while you scroll.
 *
 * The page's centrepiece and its only long pin. Seven stages — evidence in,
 * entities out, agents, threat intelligence, correlation, risk, verdict —
 * each with its own panel, driven by a single scrubbed timeline. Scroll speed
 * is playback speed, so a reader can stop on a stage and read it, or run the
 * whole thing in two seconds, and neither is wrong.
 *
 * **Why this is pinned when nothing else on the page is.** Every other
 * section can be understood from a still frame. This one is a *sequence* —
 * the claim is that seven decisions happen in an order and each one uses what
 * the last one produced — and a sequence needs the frame to hold still while
 * it plays. It is the one place the cost of a pin buys something the reader
 * could not otherwise see.
 *
 * **Why the panels are stacked rather than swapped.** All seven are in the
 * DOM from the start, absolutely positioned in the same box, and the timeline
 * moves opacity and blur. React never re-renders during the scroll: the
 * scrubbed timeline owns the DOM, which is the only way this stays at 60fps
 * on a laptop that is also running the dev server.
 *
 * **Handheld and reduced motion get the same content unpinned.** A pinned,
 * scrubbed section on a phone fights the browser's own address-bar resize —
 * every collapse re-measures the pin and the section jumps. So under 768px,
 * and for anyone who asked for less movement, the seven stages become an
 * ordinary vertical sequence. Same seven panels, same copy, no pin.
 *
 * **The rail is a reading of the timeline, not a second animation.** It used
 * to be: GSAP scrubbed each step's opacity while the stylesheet also
 * transitioned it, so the highlight trailed the panel it belonged to, and the
 * fill grew linearly while the step icons are unevenly spaced, so it reached
 * the last icon only as the pin released. Now the timeline reports which stage
 * is current, each step carries `data-state` (done, active, upcoming) and the
 * stylesheet owns how those look; the fill is driven stage by stage to each
 * icon's measured centre. The steps are buttons — choose one and the page
 * scrolls to that stage.
 *
 * Every value in every panel comes from the recorded session in
 * `landing/session.ts`. See that file's note.
 */

import { useEffect, useRef } from "react";
import {
  Braces,
  FileSearch,
  GitBranch,
  Gauge,
  Radar,
  ScanLine,
  ShieldCheck,
} from "lucide-react";
import {
  gsap,
  ScrollTrigger,
  split,
  fontsReady,
  landingMedia,
  reduced,
  DUR,
  EASE,
  refreshSoon,
} from "@/lib/landing-motion";
import { FRAME_36, NUMBER_INTEL, PASSPORT, TRAJECTORY } from "@/components/landing/session";

/** The seven decisions, in order. `what` is what the stage *decides*, not
 *  what it is called — a reader who only reads the left rail should still
 *  come away knowing how the engine thinks. */
const STAGES = [
  {
    id: "in",
    icon: ScanLine,
    name: "Evidence enters",
    what: "Read the bytes. Decide what this actually is, not what it was labelled as.",
  },
  {
    id: "extract",
    icon: Braces,
    name: "Entities extracted",
    what: "Pull out the numbers, identities and claims nobody had to type in.",
  },
  {
    id: "agents",
    icon: FileSearch,
    name: "Agents investigate",
    what: "Each specialist answers one narrow question it can be held to, and times itself.",
  },
  {
    id: "intel",
    icon: Radar,
    name: "Threat intelligence",
    what: "Check the claimed identity against the registries and advisories that would know.",
  },
  {
    id: "graph",
    icon: GitBranch,
    name: "Correlation",
    what: "Look the entities up in the fraud graph. Isolated indicators become a campaign, or they don't.",
  },
  {
    id: "risk",
    icon: Gauge,
    name: "Risk",
    what: "Fuse the evidence into one calibrated figure. Deterministic rules and a trained model — never the language model.",
  },
  {
    id: "verdict",
    icon: ShieldCheck,
    name: "Explain and protect",
    what: "Name every signal that moved the number, then say the next thing to do.",
  },
] as const;

type StepState = "done" | "active" | "upcoming";

/** Mark every step relative to the current one. */
function markSteps(steps: HTMLElement[], current: number) {
  steps.forEach((s, i) => {
    const state: StepState = i < current ? "done" : i === current ? "active" : "upcoming";
    if (s.dataset.state !== state) s.dataset.state = state;
    if (state === "active") s.setAttribute("aria-current", "step");
    else s.removeAttribute("aria-current");
  });
}

export function InvestigationSection() {
  const root = useRef<HTMLElement>(null);
  /** Scrolls to a stage. Replaced by the effect with whatever the current
   *  layout needs: a position inside the pin, or the panel itself. */
  const jump = useRef<(i: number) => void>(() => {});

  useEffect(() => {
    const el = root.current;
    if (!el) return;
    let cancelled = false;
    const teardown: (() => void)[] = [];

    void fontsReady().then(() => {
      if (cancelled) return;

      /* The headline is the same in every branch. */
      const intro = gsap.context(() => {
        if (reduced()) return;
        const h = split(el.querySelector("[data-i-h2]"), "lines");
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
        gsap.from("[data-i-lede]", {
          opacity: 0,
          y: 22,
          filter: "blur(8px)",
          duration: DUR.reveal,
          ease: EASE.out,
          scrollTrigger: { trigger: "[data-i-lede]", start: "top 88%", once: true },
        });
      }, el);
      teardown.push(() => intro.revert());

      /* Reduced motion never pins. The stylesheet releases the panels from
         their absolute stack and the seven stages become an ordinary
         document — the same content, in the same order, with nothing to
         wait for. This branch is checked before `landingMedia` because the
         preference is an attribute as well as a media query, and GSAP's
         `matchMedia` can only see the query. */
      if (reduced()) {
        el.querySelector("[data-i-stage]")?.setAttribute("data-mode", "flow");
        const panels = gsap.utils.toArray<HTMLElement>("[data-i-panel]", el);
        jump.current = (i) => scrollToEl(panels[i]);
        return;
      }

      teardown.push(
        landingMedia(el, ({ pinnable }) => {
          const panels = gsap.utils.toArray<HTMLElement>("[data-i-panel]");
          const steps = gsap.utils.toArray<HTMLElement>("[data-i-step]");

          /* --- too small to pin: an ordinary sequence ------------------
             Two reasons, and the second is the one that bites. A pinned,
             scrubbed section on a phone fights the browser's own address-bar
             resize — every collapse re-measures the pin and the section jumps
             under the reader's thumb. And a pinned frame is *fixed*: on a
             short viewport the bottom of the stage is not scrolled to, it is
             unreachable. Below the two-column layout, or below 640px of
             height, the seven stages become a document instead. */
          if (!pinnable) {
            el.querySelector("[data-i-stage]")?.setAttribute("data-mode", "flow");
            steps.forEach((s) => s.removeAttribute("data-state"));
            // The pinned branch measures the track; a layout that has just
            // left it must not keep those numbers.
            el.querySelector<HTMLElement>("[data-i-track]")?.removeAttribute("style");
            jump.current = (i) => scrollToEl(panels[i]);
            panels.forEach((p) => {
              gsap.from(p, {
                opacity: 0,
                y: 26,
                filter: "blur(10px)",
                duration: DUR.reveal,
                ease: EASE.out,
                scrollTrigger: { trigger: p, start: "top 84%", once: true },
              });
            });
            return;
          }

          el.querySelector("[data-i-stage]")?.setAttribute("data-mode", "pinned");

          /* --- the rail's geometry ------------------------------------
             The track runs from the first step's icon to the last one's, and
             the fill stops on each icon in turn. Both are measured, because
             the steps are as tall as their copy and the copy differs. Read
             again on every refresh, so a resize or a font swap re-aims it. */
          const list = el.querySelector<HTMLElement>("[data-i-steps]");
          const track = el.querySelector<HTMLElement>("[data-i-track]");
          const fill = el.querySelector<HTMLElement>("[data-i-rail]");
          const iconCentre = (i: number) => {
            const icon = steps[i]?.querySelector<HTMLElement>("[data-i-icon]");
            if (!icon || !list) return 0;
            const a = icon.getBoundingClientRect();
            return a.top + a.height / 2 - list.getBoundingClientRect().top;
          };
          const span = () => Math.max(1, iconCentre(steps.length - 1) - iconCentre(0));
          /** How far down the track step `i`'s icon sits, 0..1. */
          const at = (i: number) => (iconCentre(i) - iconCentre(0)) / span();
          const placeTrack = () => {
            if (!track || !list) return;
            track.style.top = `${iconCentre(0)}px`;
            track.style.height = `${span()}px`;
          };
          placeTrack();
          ScrollTrigger.addEventListener("refreshInit", placeTrack);

          /* --- desktop: the pin -------------------------------------- */
          const OUT = 0.28;      /* previous panel leaves */
          const IN_AT = 0.15;    /* next panel arrives */
          const ITEMS_AT = 0.25; /* its contents follow it */

          let current = -1;
          const tl = gsap.timeline({
            scrollTrigger: {
              trigger: "[data-i-pin]",
              start: "top top",
              // Roughly two thirds of a screen per stage: brisk enough that
              // nobody feels trapped, slow enough to read a panel without
              // stopping. Measured against the stage count so adding one does
              // not silently make every stage faster.
              end: () => `+=${STAGES.length * 62}%`,
              pin: true,
              scrub: 0.55,
              anticipatePin: 1,
              invalidateOnRefresh: true,
            },
            // The current stage is a reading of the playhead: stage i becomes
            // current the moment its panel starts to arrive. Written only when
            // it changes, so a scroll costs one comparison per frame.
            onUpdate: () => {
              const t = tl.time();
              let next = 0;
              for (let i = 1; i < STAGES.length; i++) if (t >= i + IN_AT) next = i;
              if (next !== current) {
                current = next;
                markSteps(steps, current);
              }
            },
          });
          markSteps(steps, 0);

          /* One stage per unit of timeline, and every tween placed against
             that unit's label.

             The first draft appended a dwell tween after each stage instead —
             which grew the timeline's total length as it was built, so the
             labels (at absolute times 0..6) drifted further out of step with
             the playhead at every stage. By stage four the outgoing panel was
             being faded while the incoming one was still staggering in, and
             the section spent most of its scroll showing neither. Absolute
             positions inside a fixed-length unit cannot drift. */
          if (fill) gsap.set(fill, { scaleY: 0 });

          panels.forEach((panel, i) => {
            const label = `s${i}`;
            tl.addLabel(label, i);

            if (i === 0) {
              // The first panel is already on screen when the pin engages. A
              // scrubbed `from` would render its start state at progress 0 and
              // the section would open on an empty stage — the one frame a
              // reader is guaranteed to see.
              gsap.set(panel, { opacity: 1, filter: "blur(0px)", yPercent: 0 });
              return;
            }

            // Out with the last, in with the next, overlapping by half — the
            // stage is never empty and never shows two panels at full strength.
            tl.to(panels[i - 1], { opacity: 0, filter: "blur(12px)", yPercent: -6, duration: OUT }, label);
            tl.fromTo(
              panel,
              { opacity: 0, filter: "blur(12px)", yPercent: 6 },
              { opacity: 1, filter: "blur(0px)", yPercent: 0, duration: 0.35 },
              `${label}+=${IN_AT}`,
            );

            // The fill travels from the last icon to this one while the panel
            // arrives, and lands on the icon as the stage becomes current.
            if (fill) {
              tl.fromTo(
                fill,
                { scaleY: () => at(i - 1) },
                { scaleY: () => at(i), duration: 0.35, ease: "power1.inOut", immediateRender: false },
                label,
              );
            }

            // Each panel's own contents arrive a beat after the panel does, so
            // a stage reads as something being assembled rather than as a
            // slide being shown. Sized to finish inside the unit: the longest
            // panel is five items, which lands at +0.81 of 1.
            const items = panel.querySelectorAll("[data-i-item]");
            if (items.length) {
              tl.from(
                items,
                { opacity: 0, y: 14, duration: 0.28, stagger: 0.07, ease: EASE.out },
                `${label}+=${ITEMS_AT}`,
              );
            }
          });

          // Dwell on the verdict rather than releasing the pin the instant
          // its last line lands — this is the panel the section exists to
          // show. Placed at the end of the final unit, so the hold is added to
          // the timeline rather than overlapping the stage it follows.
          tl.to({}, { duration: 0.5 }, STAGES.length);

          // Choosing a step scrolls to the moment its panel has fully arrived.
          jump.current = (i) => {
            const st = tl.scrollTrigger;
            if (!st) return;
            const t = i === 0 ? 0 : i + IN_AT + 0.4;
            window.scrollTo({
              top: st.start + ((st.end - st.start) * t) / tl.duration(),
              behavior: reduced() ? "auto" : "smooth",
            });
          };

          const cleanupTrack = () => ScrollTrigger.removeEventListener("refreshInit", placeTrack);

          // The risk figure counts through the recorded trajectory rather
          // than to it. Driven off the same scrub so it cannot desynchronise
          // from the stage it belongs to.
          // `fromTo`, with the markup rendering the figure the call ends on:
          // an unpinned or reduced-motion reader must see where the
          // trajectory arrived, not where it started.
          const score = el.querySelector<HTMLElement>("[data-i-score]");
          if (score) {
            const obj = { n: TRAJECTORY[0].score };
            tl.fromTo(
              obj,
              { n: TRAJECTORY[0].score },
              {
                n: TRAJECTORY[TRAJECTORY.length - 1].score,
                duration: 1,
                ease: "none",
                onUpdate: () => {
                  score.textContent = obj.n.toFixed(0);
                },
              },
              "s5",
            );
          }
          return cleanupTrack;
        }),
      );
      // Triggers built after the route's own refresh; see `refreshSoon`. The
      // pin above is why that function exists: it inserts several viewports of
      // spacer, moving every section below this one.
      refreshSoon();
    });

    return () => {
      cancelled = true;
      teardown.forEach((fn) => fn());
    };
  }, []);

  return (
    <section className="lp-section lp-section--flush" id="investigation" ref={root}>
      <div className="lp-shell">
        <p className="lp-eyebrow">
          <span className="lp-eyebrow__n">03</span> How it works
        </p>
        <h2 className="lp-h2" data-i-h2>
          Watch one investigation <em>actually run.</em>
        </h2>
        <p className="lp-lede" data-i-lede>
          Seven decisions, in order, each one using what the last one produced. Every
          value below is read from the recorded digital-arrest session the live console
          plays — the same 104 seconds, the same numbers.
        </p>
      </div>

      <div className="lp-pin" data-i-pin>
        {/* `flow` is the markup's default and the effect opts *in* to
            `pinned`. The pinned mode hides six of the seven panels in CSS, so
            defaulting to it means any failure that stops the effect running —
            a thrown import, a browser we did not test — leaves six sections of
            content invisible. Defaulting to the document, and upgrading to the
            cinema only once something is definitely driving it, fails open. */}
        <div className="lp-shell lp-inv" data-i-stage data-mode="flow">
          {/* --- the rail -------------------------------------------
              A list of buttons: each step says where it is in the sequence
              and takes you there. */}
          <ol className="lp-inv__steps" data-i-steps aria-label="Investigation stages">
            <span className="lp-inv__rail" data-i-track aria-hidden="true">
              <i data-i-rail />
            </span>
            {STAGES.map((s, i) => (
              <li className="lp-inv__step" key={s.id} data-i-step>
                <button type="button" className="lp-inv__stepbtn" onClick={() => jump.current(i)}>
                  <span className="lp-inv__icon" data-i-icon>
                    <s.icon size={15} strokeWidth={1.7} aria-hidden="true" />
                  </span>
                  <span className="lp-inv__stxt">
                    <b>
                      <span className="lp-inv__n lp-mono">{String(i + 1).padStart(2, "0")}</span>
                      {s.name}
                    </b>
                    <em>{s.what}</em>
                  </span>
                </button>
              </li>
            ))}
          </ol>

          {/* --- the panels ----------------------------------------- */}
          <div className="lp-inv__stage">
            <Panel id="in" title="Input" meta="input_classifier · 41 ms">
              <div className="lp-inv__wire" data-i-item>
                <p className="lp-label">Inbound</p>
                <p className="lp-inv__quote">Voice call · {FRAME_36.caller}</p>
              </div>
              <p className="lp-inv__line" data-i-item>
                Classified from its bytes, not its label: an audio stream, so it is routed
                to the streaming pipeline rather than the single-shot analyser.
              </p>
              <ul className="lp-inv__tags" data-i-item>
                <li>audio/stream</li>
                <li>hi-IN + en-IN</li>
                <li>consent recorded</li>
              </ul>
            </Panel>

            <Panel id="extract" title="Entities" meta="entity extraction">
              <p className="lp-inv__line" data-i-item>
                Nobody typed any of these in. They were pulled out of the first nine
                seconds of speech.
              </p>
              <ul className="lp-inv__ents">
                <li data-i-item>
                  <span className="lp-label">Number</span>
                  <b className="lp-mono">{NUMBER_INTEL.number}</b>
                </li>
                <li data-i-item>
                  <span className="lp-label">Claimed identity</span>
                  <b>{PASSPORT.claimed}</b>
                </li>
                <li data-i-item>
                  <span className="lp-label">Case reference</span>
                  <b className="lp-mono">CBI/2026/4471</b>
                </li>
              </ul>
            </Panel>

            <Panel id="agents" title="Agents" meta="4 dispatched · all reporting">
              <ul className="lp-inv__agents">
                {[
                  ["Number intelligence", "FAIL", "risk 40 — international routing"],
                  ["Trust passport", "FAIL", "4 of 4 checks failed"],
                  ["Script match", "HIT", "86% similar to a known isolation script"],
                  ["Stage classifier", "OK", "ISOLATION at 88% confidence"],
                ].map(([name, verdict, detail]) => (
                  <li key={name} data-i-item>
                    <b>{name}</b>
                    <span className="lp-inv__verdict" data-v={verdict}>{verdict}</span>
                    <em>{detail}</em>
                  </li>
                ))}
              </ul>
              <p className="lp-inv__foot" data-i-item>
                An agent that degrades is shown degraded. It is never quietly rounded up
                to success.
              </p>
            </Panel>

            <Panel id="intel" title="Threat intelligence" meta={`trust ${PASSPORT.trust}%`}>
              <p className="lp-inv__line" data-i-item>
                The caller claims to be <b>{PASSPORT.claimed}</b>. Four checks, four
                sources, four failures.
              </p>
              <ul className="lp-inv__checks">
                {PASSPORT.checks.map((c) => (
                  <li key={c.name} data-i-item>
                    <b>{c.name}</b>
                    <em>{c.detail}</em>
                    <span className="lp-inv__src lp-mono">{c.source}</span>
                  </li>
                ))}
              </ul>
            </Panel>

            <Panel id="graph" title="Correlation" meta="fraud graph">
              <p className="lp-inv__line" data-i-item>
                The number is not new. It already sits in a cluster with the identity
                claim, the payment handle and four earlier cases.
              </p>
              <ul className="lp-inv__ents">
                <li data-i-item>
                  <span className="lp-label">Linked domains</span>
                  <b className="lp-mono">3</b>
                </li>
                <li data-i-item>
                  <span className="lp-label">Linked UPI handles</span>
                  <b className="lp-mono">2</b>
                </li>
                <li data-i-item>
                  <span className="lp-label">Earlier investigations</span>
                  <b className="lp-mono">4</b>
                </li>
              </ul>
              <p className="lp-inv__foot" data-i-item>
                One number is a nuisance. Four that keep reappearing together are an
                organisation.
              </p>
            </Panel>

            <Panel id="risk" title="Risk" meta="calibrated fusion">
              <div className="lp-inv__score" data-i-item>
                <span className="lp-inv__scoren lp-mono" data-i-score>
                  {TRAJECTORY[TRAJECTORY.length - 1].score.toFixed(0)}
                </span>
                <span className="lp-inv__scorel">
                  through the call
                  <b>0:00 → 1:44</b>
                </span>
              </div>
              <p className="lp-inv__line" data-i-item>
                The real trajectory from the recording, including the two places it goes
                down — a stage transition resets part of the stage term, and hiding that
                would make the curve prettier and the product less honest.
              </p>
              <ul className="lp-inv__traj" data-i-item>
                {TRAJECTORY.map((p) => (
                  <li key={p.t} style={{ ["--h" as string]: `${p.score}%` }}>
                    <i data-risk={p.level} />
                    <span className="lp-mono">{p.score}</span>
                  </li>
                ))}
              </ul>
            </Panel>

            <Panel id="verdict" title="Verdict" meta="explanation + protection">
              <div className="lp-inv__vhead" data-i-item>
                <span className="lp-inv__vscore lp-mono">{FRAME_36.score}</span>
                <span className="chip chip--caps" data-risk={FRAME_36.level}>
                  {FRAME_36.level}
                </span>
                <span className="lp-inv__vstage">Stage: {FRAME_36.stage}</span>
              </div>
              <p className="lp-inv__line" data-i-item>
                Next likely move: <b>{FRAME_36.forecast.next}</b> in about{" "}
                {FRAME_36.forecast.inSeconds}s — money moves in about{" "}
                {FRAME_36.forecast.paymentInSeconds}s.
              </p>
              <blockquote className="lp-inv__coach" data-i-item>
                “{FRAME_36.coach.line}”
                <cite>{FRAME_36.coach.after}</cite>
              </blockquote>
              <p className="lp-inv__foot" data-i-item>
                From a curated, human-reviewed library. A model may rank these lines; it
                never writes them.
              </p>
            </Panel>
          </div>
        </div>
      </div>
    </section>
  );
}

/** One stage's panel. Same frame every time, different contents — the frame
 *  is what makes seven different compositions read as one instrument. */
function Panel({
  id,
  title,
  meta,
  children,
}: {
  id: string;
  title: string;
  meta: string;
  children: React.ReactNode;
}) {
  return (
    <article className="lp-inv__panel" data-i-panel data-panel={id}>
      <header className="lp-inv__phead">
        <h3>{title}</h3>
        <span className="lp-mono">{meta}</span>
      </header>
      <div className="lp-inv__pbody">{children}</div>
    </article>
  );
}

/** Scroll a panel into view below the fixed bar. */
function scrollToEl(el: HTMLElement | undefined) {
  if (!el) return;
  window.scrollTo({
    top: el.getBoundingClientRect().top + window.scrollY - 96,
    behavior: reduced() ? "auto" : "smooth",
  });
}
