import { useLayoutEffect, type RefObject } from "react";
import { gsap, prefersReducedMotion } from "@/lib/gsap";

/**
 * Staggered entrance for anything marked [data-reveal] inside `scope`.
 *
 * Adapted from mindteck_workspace_central's useReveal — ScrollTrigger removed,
 * because this console is a fixed viewport and nothing scrolls into view.
 * Runs in useLayoutEffect so the hidden state is set before paint, and adds
 * .fx-revealed on completion so the failsafe in global.css can tell the
 * difference between "animating" and "stuck".
 */
export function useReveal(scope: RefObject<HTMLElement | null>, deps: unknown[] = []) {
  useLayoutEffect(() => {
    const root = scope.current;
    if (!root || prefersReducedMotion) return;

    const ctx = gsap.context(() => {
      const items = gsap.utils.toArray<HTMLElement>("[data-reveal]");
      if (!items.length) return;
      gsap.set(items, { opacity: 0, y: 14 });
      gsap.to(items, {
        opacity: 1,
        y: 0,
        duration: 0.7,
        ease: "power3.out",
        stagger: 0.055,
        overwrite: true,
        onComplete: () => items.forEach((el) => el.classList.add("fx-revealed")),
      });
    }, root);

    return () => ctx.revert();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}
