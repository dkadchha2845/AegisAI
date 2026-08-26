/**
 * Motion preference, persisted and applied to `<html data-motion>`.
 *
 * `prefers-reduced-motion` is the floor, not the ceiling. Respecting the OS
 * setting is required and the stylesheets already do it — but a person can
 * want the OS default *and* want this particular interface to stop moving,
 * and on a shared or borrowed machine they cannot change the OS setting at
 * all. So there are three states: follow the system, force full, force
 * reduced.
 *
 * `data-motion="reduced"` is honoured alongside the media query everywhere
 * the media query is honoured (global.css), and `"full"` deliberately does
 * *not* override a system request for reduced motion unless the person picks
 * it explicitly — which is the one case where overriding is their call.
 */

import { useCallback, useEffect, useState } from "react";

export type MotionPreference = "system" | "full" | "reduced";

const KEY = "aegis:motion";

function read(): MotionPreference {
  if (typeof localStorage === "undefined") return "system";
  const v = localStorage.getItem(KEY);
  return v === "full" || v === "reduced" ? v : "system";
}

export function useMotionPreference() {
  const [preference, setPreference] = useState<MotionPreference>(read);
  const [systemPrefersReduced, setSystemPrefersReduced] = useState(
    () =>
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  );

  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const onChange = () => setSystemPrefersReduced(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  useEffect(() => {
    const root = document.documentElement;
    if (preference === "system") delete root.dataset.motion;
    else root.dataset.motion = preference;
    localStorage.setItem(KEY, preference);
  }, [preference]);

  const set = useCallback((next: MotionPreference) => setPreference(next), []);

  return {
    preference,
    systemPrefersReduced,
    /** What is actually in effect right now. */
    reduced: preference === "reduced" || (preference === "system" && systemPrefersReduced),
    set,
  };
}

/**
 * The same decision outside React, for modules that run before or beside the
 * component tree (lib/gsap reads this at import time).
 */
export function motionIsReduced(): boolean {
  if (typeof window === "undefined") return false;
  const forced = document.documentElement.dataset.motion;
  if (forced === "reduced") return true;
  if (forced === "full") return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** Applied before React mounts so the first paint already obeys the choice. */
export function applyStoredMotionPreference(): void {
  const preference = read();
  if (preference === "system") return;
  document.documentElement.dataset.motion = preference;
}
