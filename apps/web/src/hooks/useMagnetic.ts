import { useEffect, useRef } from "react";
import { gsap, prefersReducedMotion } from "@/lib/gsap";

/** Magnetic pull toward the cursor — for CTAs, icons, toggles. */
export function useMagnetic<T extends HTMLElement>(strength = 0.35) {
  const ref = useRef<T>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el || prefersReducedMotion) return;
    if (window.matchMedia("(pointer: coarse)").matches) return;

    // Marks the element for the CSS that drops `transform` from its own
    // transition. `.btn2` transitions transform for its press state, and a
    // 90ms CSS ease layered on top of a per-frame tween of the same property
    // is what made this feel like dragging the button through syrup.
    el.dataset.magnetic = "";

    const xTo = gsap.quickTo(el, "x", { duration: 0.55, ease: "power3.out" });
    const yTo = gsap.quickTo(el, "y", { duration: 0.55, ease: "power3.out" });
    const scaleTo = gsap.quickTo(el, "scale", { duration: 0.2, ease: "power2.out" });

    const onMove = (e: PointerEvent) => {
      const r = el.getBoundingClientRect();
      // Back out the translation already applied. `getBoundingClientRect`
      // reports the *moved* box, so measuring the offset from it feeds the
      // element's own displacement into the next target: as the button
      // approaches the cursor the measured distance shrinks, the target
      // shrinks with it, and the pull settles at strength/(1+strength) of
      // what was asked for — 0.4 behaving like 0.29, and never still while
      // the pointer moves, because every frame re-aims at a moved element.
      const cx = r.left + r.width / 2 - (gsap.getProperty(el, "x") as number);
      const cy = r.top + r.height / 2 - (gsap.getProperty(el, "y") as number);
      xTo(clamp((e.clientX - cx) * strength, r.width * 0.12));
      yTo(clamp((e.clientY - cy) * strength, r.height * 0.22));
    };
    const onLeave = () => {
      xTo(0);
      yTo(0);
      scaleTo(1);
    };
    // The inline transform GSAP writes outranks the `:active` rule in the
    // stylesheet, so the press feedback every other button has was silently
    // dead here. Same gesture, expressed on the axis GSAP owns.
    const onDown = () => scaleTo(0.97);
    const onUp = () => scaleTo(1);

    el.addEventListener("pointermove", onMove);
    el.addEventListener("pointerleave", onLeave);
    el.addEventListener("pointerdown", onDown);
    el.addEventListener("pointerup", onUp);
    return () => {
      el.removeEventListener("pointermove", onMove);
      el.removeEventListener("pointerleave", onLeave);
      el.removeEventListener("pointerdown", onDown);
      el.removeEventListener("pointerup", onUp);
      gsap.killTweensOf(el);
      gsap.set(el, { x: 0, y: 0, scale: 1 });
      delete el.dataset.magnetic;
    };
  }, [strength]);

  return ref;
}

const clamp = (v: number, max: number) => Math.max(-max, Math.min(max, v));
