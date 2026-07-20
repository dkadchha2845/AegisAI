import { useEffect, useRef } from "react";
import { gsap, prefersReducedMotion } from "@/lib/gsap";

/**
 * Tween a numeric readout toward a target, writing straight to textContent.
 *
 * Deliberately bypasses React state: the threat score updates several times a
 * second and re-rendering the tree for each frame is wasteful and janky.
 * GSAP owns the DOM node, React owns the target value.
 */
export function useCountUp(value: number, decimals = 0, duration = 0.55) {
  const ref = useRef<HTMLSpanElement>(null);
  const current = useRef(value);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (prefersReducedMotion) {
      el.textContent = value.toFixed(decimals);
      current.current = value;
      return;
    }
    const obj = { n: current.current };
    const tween = gsap.to(obj, {
      n: value,
      duration,
      ease: "power2.out",
      onUpdate: () => {
        el.textContent = obj.n.toFixed(decimals);
      },
      onComplete: () => {
        current.current = value;
      },
    });
    return () => {
      tween.kill();
      current.current = obj.n;
    };
  }, [value, decimals, duration]);

  return ref;
}
