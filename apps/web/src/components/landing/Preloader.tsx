/**
 * The first second.
 *
 * The mark draws itself, a scan passes through it, the name resolves, and the
 * veil lifts off the hero. Total: 1.15s, and any click or key press cuts it
 * short.
 *
 * **Why a loading screen at all, when nothing is loading.** Two reasons that
 * are not "it looks nice". The first is that Satoshi arrives from Fontshare
 * after first paint, and a hero whose headline is split into lines *before*
 * the real face lands measures its line breaks in the fallback — the veil
 * covers exactly that swap. The second is that the hero's entrance is the
 * page's best moment and it only plays once; without a beat of stillness
 * first, it plays while the browser is still doing layout and half of it is
 * dropped frames.
 *
 * **Why it is 1.15 seconds and interruptible.** A brand animation that makes
 * someone wait is a brand animation that gets resented. This one is shorter
 * than the time it takes to move a hand back to the trackpad, it never blocks
 * a second visit within the session, and it does not exist at all for a
 * visitor who has asked for reduced motion — they get the page immediately,
 * which is the correct reading of that request.
 */

import { useEffect, useRef } from "react";
import { gsap, DUR, EASE, reduced } from "@/lib/landing-motion";

const SEEN = "aegis:lp-boot";

/** Whether the veil should play at all. Read once, synchronously, so the
 *  first render already knows and there is no frame of overlay for a visitor
 *  who is not getting one. */
export function shouldBoot(): boolean {
  if (typeof window === "undefined") return false;
  if (reduced()) return false;
  try {
    return sessionStorage.getItem(SEEN) !== "1";
  } catch {
    // Private mode, or storage disabled. Showing it is the safe side of this
    // decision — it is a second, not a paywall.
    return true;
  }
}

export function Preloader({ onDone }: { onDone: () => void }) {
  const root = useRef<HTMLDivElement>(null);
  const done = useRef(false);

  useEffect(() => {
    const el = root.current;
    if (!el) return;

    try {
      sessionStorage.setItem(SEEN, "1");
    } catch {
      /* storage disabled — the veil simply plays again next time */
    }

    const finish = () => {
      if (done.current) return;
      done.current = true;
      onDone();
    };

    const ctx = gsap.context(() => {
      const tl = gsap.timeline({ onComplete: finish });

      // The mark draws. DrawSVGPlugin animates the stroke dash offset, which
      // is the one way to get "a line being drawn" without animating a path's
      // geometry every frame.
      tl.from("[data-boot-draw]", {
        drawSVG: "0%",
        duration: 0.62,
        ease: "power2.inOut",
        stagger: 0.08,
      })
        .from("[data-boot-dot]", { scale: 0, transformOrigin: "50% 50%", duration: 0.3, ease: "back.out(2)" }, "-=0.2")
        // The scan: one line crossing the mark, which is the product's own
        // gesture — this is an instrument that reads things.
        .fromTo(
          "[data-boot-scan]",
          { yPercent: -140, opacity: 0 },
          { yPercent: 140, opacity: 1, duration: 0.52, ease: "power1.inOut" },
          "-=0.42",
        )
        .to("[data-boot-scan]", { opacity: 0, duration: 0.18 }, "-=0.14")
        .from(
          "[data-boot-word] span",
          { opacity: 0, yPercent: 60, filter: "blur(8px)", duration: DUR.quick, ease: EASE.out, stagger: 0.035 },
          "-=0.36",
        )
        .to({}, { duration: 0.12 })
        // The veil leaves upward and takes the mark with it, so the eye is
        // already travelling toward the headline when the headline arrives.
        .to("[data-boot-stage]", { y: -26, opacity: 0, filter: "blur(10px)", duration: 0.4, ease: EASE.out })
        .to(
          el,
          { clipPath: "inset(0 0 100% 0)", duration: 0.62, ease: EASE.io },
          "-=0.24",
        );

      // Any input skips it. `once` so the listeners cannot fire into a
      // timeline that has already been killed.
      const skip = () => {
        tl.progress(1, false);
        finish();
      };
      window.addEventListener("pointerdown", skip, { once: true });
      window.addEventListener("keydown", skip, { once: true });
      // The safety net: if a frame budget collapses or the tab is
      // backgrounded mid-veil, the page must still become reachable.
      const bail = window.setTimeout(skip, 2600);

      return () => {
        window.removeEventListener("pointerdown", skip);
        window.removeEventListener("keydown", skip);
        window.clearTimeout(bail);
      };
    }, el);

    return () => ctx.revert();
  }, [onDone]);

  return (
    <div className="lp-boot" ref={root} role="presentation">
      <div className="lp-boot__stage" data-boot-stage>
        <div className="lp-boot__mark">
          <svg viewBox="0 0 24 24" width="72" height="72" fill="none" aria-hidden="true">
            <path
              data-boot-draw
              className="lp-boot__shield"
              d="M12 2.2 20.2 5.1v6.6c0 4.7-3.2 8.6-8.2 10.1-5-1.5-8.2-5.4-8.2-10.1V5.1L12 2.2Z"
              strokeWidth="1.3"
              strokeLinejoin="round"
            />
            <path
              data-boot-draw
              className="lp-boot__spark"
              d="M8.1 14.4 11 11.2l2.1 2.3 3.1-4"
              strokeWidth="1.3"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <circle data-boot-dot className="lp-boot__dot" cx="16.2" cy="9.5" r="1.35" />
          </svg>
          <span className="lp-boot__scan" data-boot-scan aria-hidden="true" />
        </div>
        <p className="lp-boot__word" data-boot-word aria-label="AegisAI">
          {"AEGISAI".split("").map((c, i) => (
            <span key={`${c}-${i}`} aria-hidden="true">
              {c}
            </span>
          ))}
        </p>
      </div>
    </div>
  );
}
