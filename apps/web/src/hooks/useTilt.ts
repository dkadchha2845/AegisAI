import { useEffect, useRef } from "react";
import { gsap, prefersReducedMotion } from "@/lib/gsap";

/**
 * Cursor-driven 3D tilt for a card — a subtle parallax that gives the landing
 * and login surfaces depth without turning into a toy.
 *
 * Deliberately restrained: a few degrees of rotation and a small lift, eased
 * so it tracks the pointer rather than snapping. It sets a CSS variable pair
 * (`--tilt-x` / `--tilt-y`) as well as writing the transform, so a child (an
 * inner sheen, a floating badge) can parallax off the same signal.
 *
 * Off entirely for reduced-motion and coarse-pointer (touch) devices — there is
 * no hover on a phone, and a tilt that only fires on tap reads as a bug.
 */
export function useTilt<T extends HTMLElement>(opts: { max?: number; lift?: number } = {}) {
  const { max = 7, lift = 6 } = opts;
  const ref = useRef<T>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el || prefersReducedMotion) return;
    if (window.matchMedia("(pointer: coarse)").matches) return;

    el.style.transformStyle = "preserve-3d";
    el.style.willChange = "transform";
    const rotX = gsap.quickTo(el, "rotationX", { duration: 0.5, ease: "power3.out" });
    const rotY = gsap.quickTo(el, "rotationY", { duration: 0.5, ease: "power3.out" });
    const yTo = gsap.quickTo(el, "y", { duration: 0.5, ease: "power3.out" });

    const onMove = (e: PointerEvent) => {
      const r = el.getBoundingClientRect();
      const px = (e.clientX - r.left) / r.width - 0.5; // -0.5 .. 0.5
      const py = (e.clientY - r.top) / r.height - 0.5;
      rotY(px * max * 2);
      rotX(-py * max * 2);
      yTo(-lift);
      el.style.setProperty("--tilt-x", `${px.toFixed(3)}`);
      el.style.setProperty("--tilt-y", `${py.toFixed(3)}`);
    };
    const reset = () => {
      rotX(0);
      rotY(0);
      yTo(0);
      el.style.setProperty("--tilt-x", "0");
      el.style.setProperty("--tilt-y", "0");
    };

    el.addEventListener("pointermove", onMove);
    el.addEventListener("pointerleave", reset);
    return () => {
      el.removeEventListener("pointermove", onMove);
      el.removeEventListener("pointerleave", reset);
    };
  }, [max, lift]);

  return ref;
}
