/**
 * Protection while the call is still happening.
 *
 * The claim every other section builds toward: this is not post-hoc forensics
 * on a complaint filed after the money left. The panel is the recorded
 * digital-arrest session, driven by the scroll — waveform, transcript, tactic
 * meters, threat figure and the coaching line all advance together through the
 * four frames the page quotes, because in the real console they advance
 * together too.
 *
 * **Everything here is transcribed, not written.** The Hinglish is verbatim
 * from `mock/stream.json`, including the code-switching, because that is what
 * these calls actually sound like and the model's strongest measured
 * performance is on exactly this. Sanitising it into English would
 * misrepresent both the threat and the system.
 *
 * **The waveform is the one purely decorative element on the page**, and it is
 * marked as such: it is a plausible envelope, not an FFT of the recording, so
 * it is aria-hidden and the copy never refers to it as data. Everything beside
 * it is a reading.
 */

import { useEffect, useRef } from "react";
import { PhoneCall, TriangleAlert } from "lucide-react";
import {
  gsap,
  split,
  fontsReady,
  DUR,
  EASE,
  reduced,
  refreshSoon,
} from "@/lib/landing-motion";
import { FRAME_36, TRAJECTORY, UTTERANCES, prettyStage } from "@/components/landing/session";

/** Bar count for the waveform. Enough to read as speech, few enough that the
 *  repeating timeline is a dozen tweens rather than a hundred. */
const BARS = 44;

export function LiveCallSection() {
  const root = useRef<HTMLElement>(null);

  useEffect(() => {
    const el = root.current;
    if (!el) return;
    let cancelled = false;
    const teardown: (() => void)[] = [];

    void fontsReady().then(() => {
      if (cancelled) return;
      const ctx = gsap.context(() => {
        if (reduced()) return;

        const h = split(el.querySelector("[data-l-h2]"), "lines");
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
        gsap.from("[data-l-lede]", {
          opacity: 0,
          y: 22,
          filter: "blur(8px)",
          duration: DUR.reveal,
          ease: EASE.out,
          scrollTrigger: { trigger: "[data-l-lede]", start: "top 88%", once: true },
        });
        gsap.from("[data-l-panel]", {
          opacity: 0,
          y: 40,
          filter: "blur(14px)",
          duration: DUR.slow,
          ease: EASE.out,
          scrollTrigger: { trigger: "[data-l-panel]", start: "top 84%", once: true },
        });

        /* The waveform. One timeline, seeded per bar, running while the panel
           is anywhere near the viewport and paused when it is not — a
           44-tween loop running three screens away is pure heat. */
        const bars = gsap.utils.toArray<HTMLElement>("[data-l-bar]");
        const wave = gsap.timeline({ repeat: -1, yoyo: true, paused: true });
        wave.to(bars, {
          scaleY: () => 0.25 + Math.random() * 0.95,
          duration: 0.34,
          ease: "sine.inOut",
          stagger: { each: 0.014, from: "center" },
        });
        gsap.utils.toArray<HTMLElement>("[data-l-panel]").forEach((panel) => {
          gsap.timeline({
            scrollTrigger: {
              trigger: panel,
              start: "top bottom",
              end: "bottom top",
              onToggle: ({ isActive }) => (isActive ? wave.play() : wave.pause()),
            },
          });
        });

        /* The call advances with the scroll. Four transcript beats, the tactic
           meters filling behind them and the figure climbing with them —
           one timeline, so they cannot drift apart. */
        const tl = gsap.timeline({
          scrollTrigger: {
            trigger: "[data-l-panel]",
            start: "top 68%",
            end: "bottom 42%",
            scrub: 0.6,
          },
        });

        const lines = gsap.utils.toArray<HTMLElement>("[data-l-line]");
        lines.forEach((line, i) => {
          tl.from(line, { opacity: 0, y: 18, filter: "blur(8px)", duration: 0.5, ease: EASE.out }, i * 0.55);
          tl.to(line, { opacity: 0.4, duration: 0.3 }, (i + 1) * 0.55 + 0.2);
        });
        // The last line stays lit: it is the frame everything else reports on.
        tl.to(lines[lines.length - 1], { opacity: 1, duration: 0.2 }, ">");

        tl.from("[data-l-meter] i", { scaleX: 0, transformOrigin: "left", duration: 0.6, stagger: 0.1, ease: "power2.out" }, 0.4);

        // `fromTo` with the markup rendering the settled figure — see the
        // same note in DecisionSection. The panel must read 88 for anyone the
        // scrub never runs for.
        const score = el.querySelector<HTMLElement>("[data-l-score]");
        if (score) {
          const obj = { n: TRAJECTORY[0].score };
          tl.fromTo(
            obj,
            { n: TRAJECTORY[0].score },
            {
              n: FRAME_36.score,
              duration: 1.8,
              ease: "none",
              onUpdate: () => {
                score.textContent = obj.n.toFixed(0);
              },
            },
            0.2,
          );
        }

        tl.from("[data-l-warn]", { opacity: 0, y: 16, duration: 0.5, ease: EASE.out }, ">-0.3");
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
    <section className="lp-section" id="live" ref={root}>
      <div className="lp-shell">
        <p className="lp-eyebrow">
          <span className="lp-eyebrow__n">07</span> Real time
        </p>
        <h2 className="lp-h2" data-l-h2>
          And while the call is <em>still happening.</em>
        </h2>
        <p className="lp-lede" data-l-lede>
          A complaint filed after the transfer is forensics. This is the same engine
          reading the conversation as it happens — naming the manipulation stage in
          progress, forecasting how long until money moves, and telling the person on the
          line what to say.
        </p>

        <div className="lp-call" data-l-panel>
          <header className="lp-call__head">
            <span className="lp-call__live">
              <span className="lp-call__dot" aria-hidden="true" />
              Live protected call
            </span>
            <span className="lp-mono lp-call__num">
              <PhoneCall size={12} aria-hidden="true" /> {FRAME_36.caller}
            </span>
            <span className="lp-mono lp-call__t">{FRAME_36.t}</span>
          </header>

          <div className="lp-call__grid">
            <div className="lp-call__left">
              <div className="lp-call__wave" aria-hidden="true">
                {Array.from({ length: BARS }, (_, i) => (
                  <i key={i} data-l-bar style={{ ["--seed" as string]: (i % 7) / 7 }} />
                ))}
              </div>

              <p className="lp-label">Transcript</p>
              <ol className="lp-call__script">
                {UTTERANCES.map((u) => (
                  <li key={u.t} data-l-line>
                    <span className="lp-call__stage lp-mono">{prettyStage(u.stage)}</span>
                    <q>{u.text}</q>
                  </li>
                ))}
              </ol>
            </div>

            <div className="lp-call__right">
              <div className="lp-call__score">
                <span className="lp-call__scoren lp-mono" data-l-score>
                  {FRAME_36.score}
                </span>
                <span className="chip chip--caps" data-risk={FRAME_36.level}>
                  {FRAME_36.level}
                </span>
              </div>
              <p className="lp-call__stagenow">
                Stage in progress: <strong>{FRAME_36.stage}</strong>
              </p>

              <p className="lp-label lp-call__mlabel">Manipulation</p>
              <ul className="lp-call__meters">
                {FRAME_36.tactics.map((t) => (
                  <li key={t.label}>
                    <span>{t.label}</span>
                    <span className="lp-call__meter" data-l-meter>
                      <i style={{ ["--w" as string]: `${t.weight * 100}%` }} />
                    </span>
                    <b className="lp-mono">{t.weight.toFixed(2)}</b>
                  </li>
                ))}
              </ul>

              <p className="lp-call__forecast">
                Next likely: <strong>{FRAME_36.forecast.next}</strong> in ~
                {FRAME_36.forecast.inSeconds}s · money moves in ~
                {FRAME_36.forecast.paymentInSeconds}s
              </p>
            </div>
          </div>

          <div className="lp-call__warn" data-l-warn>
            <TriangleAlert size={16} aria-hidden="true" />
            <div>
              <b>High-risk conversation. Do not share an OTP or any financial detail.</b>
              <p>
                Say: “{FRAME_36.coach.line}” {FRAME_36.coach.after}
              </p>
              <span>{FRAME_36.coach.why}</span>
            </div>
          </div>
        </div>

        <p className="lp-note">
          <strong>Consent is explicit and the indicator is visible.</strong> Retention is
          configurable and nothing here is designed around covert recording. The
          transcript above is the recorded demonstration session, quoted verbatim.
        </p>
      </div>
    </section>
  );
}
