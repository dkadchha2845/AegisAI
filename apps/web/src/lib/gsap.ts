/**
 * Single GSAP registration point. Ported from mindteck_workspace_central.
 *
 * ScrollTrigger is registered here now that the app is more than one fixed
 * console screen: the home and dashboard routes scroll, the live console
 * still does not. Registering a plugin twice is harmless; registering it in
 * two files is how you end up with two copies of it.
 */
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { motionIsReduced } from "@/hooks/useMotionPreference";

gsap.registerPlugin(ScrollTrigger);

/**
 * Whether to animate at all.
 *
 * Reads the app's own preference as well as the OS media query, because a
 * person can want the system default globally and want *this* interface still
 * — and on a borrowed machine they cannot change the OS setting at all.
 * `applyStoredMotionPreference()` runs before React mounts, so the attribute
 * is already on `<html>` when this module is first imported.
 */
export const prefersReducedMotion = motionIsReduced();

/** How long an entrance is allowed to take before the failsafe forces it.
 *  Comfortably longer than the longest stagger (~1.1s) and short enough that
 *  a stuck panel is fixed before anyone reads it as broken. */
const FAILSAFE_MS = 2500;

/**
 * Marks the document as JS-alive so .fx-* entrance states apply, and reveals
 * anything still not fully visible after FAILSAFE_MS. See global.css.
 *
 * This is not paranoia. Entrance animations start elements at opacity 0, so
 * anything that stops the tween leaves the content invisible and the page
 * looks broken rather than unanimated — unrecoverable on a stage.
 *
 * It checks for *partial* opacity, not just exactly 0, and that distinction
 * is the whole point. GSAP's ticker sleeps while a tab is backgrounded, so
 * switching away mid-entrance freezes panels at whatever fraction they had
 * reached — 0.13, 0.38 — which the old `=== "0"` test skipped entirely. The
 * observed failure was three console panels stuck at 13% opacity with no way
 * back short of a reload.
 */
export function armFailsafe() {
  if (typeof document === "undefined") return;
  document.documentElement.classList.add("js");
  window.setTimeout(() => {
    document
      .querySelectorAll<HTMLElement>(
        ".fx-fade, .fx-rise, [data-reveal], [data-scroll-reveal]",
      )
      .forEach((el) => {
        if (Number(getComputedStyle(el).opacity) < 0.99) {
          // Kill first, then force. Writing the styles while a tween is still
          // attached to the element only wins until the ticker next runs —
          // GSAP resumes from its own timeline and drags the opacity straight
          // back down, which looked exactly like the failsafe never fired.
          gsap.killTweensOf(el);
          el.style.opacity = "1";
          el.style.transform = "none";
          el.classList.add("fx-revealed");
        }
      });
  }, FAILSAFE_MS);
}

export { gsap, ScrollTrigger };
