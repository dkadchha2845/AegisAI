/**
 * The landing page's motion engine.
 *
 * `lib/gsap.ts` is the app's registration point and stays that way — it owns
 * ScrollTrigger and the entrance failsafe every route relies on. This module
 * sits on top of it and adds only what the landing needs: the four bonus
 * plugins the cinematic sections use, two custom easing curves, and the small
 * set of reveal primitives that keep twelve sections speaking one language.
 *
 * Three decisions worth defending:
 *
 * 1. **One motion vocabulary, five dialects.** `blurUp`, `maskUp`, `clipIn`,
 *    `slideIn` and `scaleIn` are the only entrances on the page. Sections vary
 *    which one they use — never how it is tuned — so the page reads as one
 *    system rather than twelve. Durations and easings live here, once.
 *
 * 2. **Reduced motion is read live, not at import.** `prefersReducedMotion` in
 *    `lib/gsap` is frozen the first time that module is imported, which is
 *    correct for a console that mounts once. The landing has a preference
 *    toggle three routes away and a person can come back; `reduced()` asks the
 *    document each time it is called.
 *
 * 3. **Nothing here is load-bearing for legibility.** Every entrance is a
 *    `gsap.from`, so the settled state is whatever the stylesheet already
 *    says. If GSAP never runs — a thrown error, a browser we did not test —
 *    the page is a static, fully readable document. `armFailsafe()` is the
 *    second net under that, not the first.
 */

import { gsap, ScrollTrigger, armFailsafe } from "@/lib/gsap";
import { SplitText } from "gsap/SplitText";
import { DrawSVGPlugin } from "gsap/DrawSVGPlugin";
import { MotionPathPlugin } from "gsap/MotionPathPlugin";
import { CustomEase } from "gsap/CustomEase";
import { motionIsReduced } from "@/hooks/useMotionPreference";

gsap.registerPlugin(SplitText, DrawSVGPlugin, MotionPathPlugin, CustomEase);

/* --------------------------------------------------------------- easing */

/**
 * Two curves carry the whole page.
 *
 * `aegis` is a long, decelerating settle — no overshoot, because a security
 * product that bounces reads as a toy. Everything that *arrives* uses it.
 * `aegis.io` is symmetrical and is used only for things that move between two
 * states under their own steam: the nav surface, the mobile menu, the pulses.
 *
 * Registered defensively. `CustomEase.create` throws on a duplicate name, and
 * Vite's HMR re-executes this module on every edit during development.
 */
if (!CustomEase.get("aegis")) CustomEase.create("aegis", "0.16,1,0.3,1");
if (!CustomEase.get("aegis.io")) CustomEase.create("aegis.io", "0.76,0,0.24,1");

/** The page's timing vocabulary, in seconds. Micro / reveal / cinematic. */
export const DUR = {
  micro: 0.22,
  quick: 0.42,
  reveal: 0.78,
  slow: 1.15,
  cinema: 1.7,
} as const;

export const EASE = {
  out: "aegis",
  io: "aegis.io",
  expo: "expo.out",
  power: "power3.out",
} as const;

/* ------------------------------------------------------------ preference */

/** Whether the visitor has asked for less movement, asked right now. */
export function reduced(): boolean {
  return motionIsReduced();
}

/** True on a device that cannot afford pinned, scrubbed choreography. */
export function isHandheld(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(max-width: 767px)").matches;
}

/* -------------------------------------------------------------- reveals */

type RevealVars = Omit<gsap.TweenVars, "scrollTrigger">;

interface RevealOptions extends RevealVars {
  /** Where the element must reach before it starts. Default: 82% down. */
  start?: string;
  /** Fires once and forgets. Almost always what a landing wants. */
  once?: boolean;
  /** Seconds between siblings when `target` is a list. */
  stagger?: number | gsap.StaggerVars;
  trigger?: Element | string;
}

const FROM = {
  /** The house default: out of focus, low, and dark — resolving into place. */
  blurUp: { opacity: 0, y: 34, filter: "blur(14px)" },
  /** For type set on a line mask. No blur: a masked line is already a reveal. */
  maskUp: { yPercent: 116, opacity: 0 },
  /** For panels and cards that should feel *uncovered* rather than moved. */
  clipIn: { clipPath: "inset(0 0 100% 0)", opacity: 0 },
  /** For things that arrive from the side of the story they belong to. */
  slideIn: { opacity: 0, x: -46, filter: "blur(10px)" },
  slideInRight: { opacity: 0, x: 46, filter: "blur(10px)" },
  /** For objects that come *toward* the reader — evidence, nodes, scores. */
  scaleIn: { opacity: 0, scale: 0.86, filter: "blur(12px)" },
} as const;

export type RevealKind = keyof typeof FROM;

/**
 * The one entrance function. Everything on the page reveals through this so
 * the timing and easing cannot drift apart section by section.
 *
 * Returns the tween so a caller can park it on its own timeline instead.
 */
export function reveal(
  target: gsap.TweenTarget,
  kind: RevealKind = "blurUp",
  { start = "top 82%", once = true, trigger, ...vars }: RevealOptions = {},
): gsap.core.Tween {
  return gsap.from(target, {
    ...FROM[kind],
    duration: DUR.reveal,
    ease: EASE.out,
    // `blur(0px)`, not the omission of `filter`: a tween that ends at "none"
    // leaves the browser interpolating between a filter list and a keyword,
    // which Safari resolves by snapping. Naming the identity value keeps it a
    // numeric interpolation the whole way.
    filter: "blur(0px)",
    clearProps: "filter,clipPath",
    ...vars,
    scrollTrigger: {
      trigger: trigger ?? (typeof target === "string" ? target : (target as Element)),
      start,
      once,
    },
  });
}

/* ----------------------------------------------------------------- split */

export interface SplitHandle {
  lines: HTMLElement[];
  words: HTMLElement[];
  chars: HTMLElement[];
  revert: () => void;
}

/**
 * Split a heading into animatable pieces, with the accessibility already
 * handled — SplitText keeps the original text on the element for assistive
 * technology and marks the generated spans `aria-hidden`.
 *
 * `mask: "lines"` wraps each line in its own overflow-hidden box, which is
 * what makes a masked reveal possible without clipping descenders: the mask
 * is the line box GSAP measures, not one we guessed at in CSS.
 *
 * Returns a no-op handle when the element is missing so callers never have to
 * null-check before building a timeline.
 */
export function split(
  el: Element | null,
  type: "lines" | "words" | "chars" | "words,chars" | "lines,words" = "lines",
): SplitHandle {
  if (!el) return { lines: [], words: [], chars: [], revert: () => {} };
  const instance = new SplitText(el, {
    type,
    mask: type.includes("lines") ? "lines" : undefined,
    linesClass: "lp-line",
    wordsClass: "lp-word",
    charsClass: "lp-char",
    // Deliberately *not* `autoSplit`. It re-splits on a font swap or a resize,
    // which throws away the very elements a running entrance is tweening — the
    // tween keeps ticking against detached nodes and the headline is left
    // frozen wherever it had reached. The correct pattern is the one the
    // callers use: wait for `document.fonts.ready`, split once, animate, then
    // `revert()` on completion so later reflows are the browser's own.
    autoSplit: false,
  });
  return {
    lines: instance.lines as HTMLElement[],
    words: instance.words as HTMLElement[],
    chars: instance.chars as HTMLElement[],
    revert: () => instance.revert(),
  };
}

/**
 * The page's signature headline entrance: lines rise out of their own mask,
 * pulled through a blur, each one a beat behind the last.
 *
 * Under reduced motion the headline is simply there — no fade, no delay. A
 * person who asked for less movement should not be made to wait for it.
 */
export function revealHeadline(
  el: HTMLElement | null,
  { trigger, start = "top 84%", delay = 0, stagger = 0.085 }: {
    trigger?: Element | null;
    start?: string;
    delay?: number;
    stagger?: number;
  } = {},
): SplitHandle {
  const handle = split(el, "lines");
  if (!handle.lines.length) return handle;
  gsap.from(handle.lines, {
    yPercent: 118,
    opacity: 0,
    filter: "blur(12px)",
    duration: DUR.slow,
    ease: EASE.out,
    stagger,
    delay,
    scrollTrigger: { trigger: trigger ?? el ?? undefined, start, once: true },
    onComplete: () => gsap.set(handle.lines, { clearProps: "filter" }),
  });
  return handle;
}

/**
 * Resolve once the display face has actually landed.
 *
 * Satoshi arrives from Fontshare after first paint. Splitting a headline into
 * lines before the swap measures the break points in the fallback face, and
 * when the real one lands the reflow leaves words stranded mid-mask. Every
 * headline entrance waits for this.
 *
 * The 900ms cap is the point: `document.fonts.ready` never resolving — an
 * offline Fontshare, a blocked request — must delay the page's best moment by
 * under a second, not forever.
 */
export function fontsReady(): Promise<void> {
  if (typeof document === "undefined" || !document.fonts) return Promise.resolve();
  return Promise.race([
    document.fonts.ready.then(() => undefined),
    new Promise<void>((res) => setTimeout(res, 900)),
  ]);
}

/**
 * Start a timeline only once the tab is actually being looked at.
 *
 * GSAP's ticker is driven by `requestAnimationFrame`, which browsers stop
 * delivering to a hidden tab. A page opened in a background tab — a
 * middle-click from a search result, a link restored on startup — therefore
 * runs its entrance with the ticker asleep and, on return, is a half-played
 * hero frozen at whatever fraction it had reached. Holding the timeline until
 * the first visible frame means that visitor gets the entrance rather than the
 * wreckage of one.
 *
 * Returns a disposer that detaches the listener.
 */
export function playWhenVisible(tl: gsap.core.Timeline): () => void {
  if (typeof document === "undefined" || !document.hidden) {
    tl.play();
    return () => {};
  }
  tl.pause(0);
  const onVisible = () => {
    if (document.hidden) return;
    document.removeEventListener("visibilitychange", onVisible);
    tl.play();
  };
  document.addEventListener("visibilitychange", onVisible);
  return () => document.removeEventListener("visibilitychange", onVisible);
}

/**
 * Ask ScrollTrigger to re-measure the document, once, after every section has
 * finished declaring itself.
 *
 * ScrollTrigger caches each trigger's start and end in pixels when the trigger
 * is created. Every section here waits for `fontsReady()` before it splits its
 * headline and builds its triggers, so all of them are created
 * *asynchronously* — after the route's own `ScrollTrigger.refresh()` has
 * already run, and in an order that depends on when a font request resolves.
 * The investigation section also pins, and a pin inserts several viewports of
 * spacer into the document, moving everything below it.
 *
 * So the measurements taken as each section registers cannot all be right at
 * once. One refresh after the last of them is, and that is what this is.
 *
 * Every section calls it when it finishes wiring up; the calls coalesce into a
 * single refresh on the next tick.
 */
let refreshTimer = 0;
export function refreshSoon(): void {
  if (typeof window === "undefined") return;
  window.clearTimeout(refreshTimer);
  refreshTimer = window.setTimeout(() => ScrollTrigger.refresh(), 80);
}

/* ------------------------------------------------------------- lifecycle */

/**
 * Everything a landing section needs to set up and, more importantly, tear
 * down. React 18's StrictMode mounts effects twice in development, and a
 * ScrollTrigger that survives an unmount measures a DOM that no longer
 * exists — which is how pinned sections end up with a scroll gap and nothing
 * in it.
 *
 * `gsap.context` scopes every selector string to the section root and reverts
 * every tween and trigger created inside it in one call.
 */
export function landingContext(
  root: Element | null,
  build: (ctx: gsap.Context) => void,
): () => void {
  if (!root) return () => {};
  const ctx = gsap.context(build, root);
  return () => ctx.revert();
}

/**
 * A `matchMedia` context, for choreography that must differ by breakpoint
 * rather than merely scale. Pinning is the main one: a pinned, scrubbed
 * section on a phone fights the browser's own address-bar resize, so the
 * handheld branch replaces it with sequential reveals.
 *
 * **Breakpoint only — it says nothing about motion preference.** GSAP's
 * `matchMedia` can only evaluate media queries, and this product's motion
 * preference is a `data-motion` attribute on `<html>` as well as a media
 * query, because a person can want the system default globally and want *this*
 * interface still. A `(prefers-reduced-motion)` condition here would honour
 * half of that and silently ignore the half a visitor actually set. Callers
 * check `reduced()` first and branch before they get here.
 */
export interface LandingConditions {
  /** Wide enough *and* tall enough for a pinned, scrubbed section.
   *
   *  Height matters as much as width and is the half that is easy to forget:
   *  a pinned frame is fixed, so anything taller than the viewport is not
   *  scrolled to — it is simply unreachable. The two-column investigation
   *  layout only exists above 1080px, and below ~640px of height its panels
   *  no longer fit whatever the width. Both fall back to the unpinned
   *  sequence, which is the same content in the same order. */
  pinnable: boolean;
  /** The inverse. Declared rather than derived so a caller reads as a
   *  two-branch decision instead of a negation. */
  flowing: boolean;
}

export function landingMedia(
  root: Element | null,
  build: (conditions: LandingConditions, context: gsap.Context) => void,
): () => void {
  if (!root) return () => {};
  const mm = gsap.matchMedia(root);
  mm.add(
    {
      pinnable: "(min-width: 1080px) and (min-height: 640px)",
      flowing: "(max-width: 1079px), (max-height: 639px)",
    },
    (context) => {
      build(context.conditions as unknown as LandingConditions, context);
    },
  );
  return () => mm.revert();
}

export { gsap, ScrollTrigger, SplitText, DrawSVGPlugin, MotionPathPlugin, armFailsafe };
