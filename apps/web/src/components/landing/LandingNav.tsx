/**
 * The landing's navigation.
 *
 * It has two states and the interesting part is the journey between them.
 * Over the hero it is not a bar at all — no surface, no border, generous
 * height, the mark and the links floating directly on the page. Once the page
 * has moved it becomes a compact, translucent, blurred bar with a hairline
 * under it.
 *
 * **Why that transition is scrubbed rather than toggled.** A class swap gives
 * you a CSS transition that runs at a fixed speed regardless of how fast you
 * scrolled, which is the tell of a template: flick the wheel and the bar is
 * still catching up a third of a second later. Here a ScrollTrigger scrubs the
 * whole transformation against the first 200px of scroll, so the bar is
 * exactly as settled as the page is — and `scrub: 0.5` gives it just enough
 * lag to read as mass rather than as a value being written.
 *
 * Everything the scrub touches is a custom property consumed by one rule in
 * landing.css. That keeps the animated surface to a single element and means
 * the whole state machine is legible in one place instead of spread across a
 * class name, a media query and a transition.
 *
 * **The current-section indicator** is five ScrollTriggers, one per anchor,
 * each flipping a piece of React state as its section crosses the middle of
 * the viewport. It is the only thing on this page that tells a reader how far
 * through twelve sections they are.
 *
 * Signed-in state is not this component's business: `<UserMenu>` is shared
 * with the app shell precisely so the two chromes cannot disagree about
 * whether you are signed in. It is restyled for this surface in CSS, not
 * forked.
 */

import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Menu, Moon, Sun, X } from "lucide-react";
import { Logo } from "@/components/brand/Logo";
import { UserMenu } from "@/components/layout/UserMenu";
import { useTheme } from "@/context/ThemeContext";
import { gsap, ScrollTrigger, DUR, EASE, reduced } from "@/lib/landing-motion";

/** The five destinations, in page order. Fewer than the section count on
 *  purpose — a nav that lists twelve things is a table of contents. */
const LINKS = [
  { id: "problem", label: "Platform" },
  { id: "investigation", label: "How it works" },
  { id: "agents", label: "Capabilities" },
  { id: "graph", label: "Intelligence" },
  { id: "research", label: "Research" },
] as const;

export function LandingNav() {
  const navRef = useRef<HTMLElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const { theme, toggle } = useTheme();
  const [open, setOpen] = useState(false);
  const [current, setCurrent] = useState<string | null>(null);

  /* --- the settle ---------------------------------------------------- */
  useEffect(() => {
    const nav = navRef.current;
    if (!nav) return;

    // Reduced motion still gets both states — it just gets them as a step at
    // the same threshold rather than a scrub. The bar has to become opaque or
    // the links stop being legible over the section below it.
    if (reduced()) {
      const st = ScrollTrigger.create({
        start: 120,
        onToggle: ({ isActive }) => nav.toggleAttribute("data-settled", isActive),
      });
      return () => st.kill();
    }

    const tl = gsap.timeline({
      scrollTrigger: { start: 0, end: 200, scrub: 0.5 },
    });
    tl.fromTo(
      nav,
      { "--nav-pad": "26px", "--nav-bg": 0, "--nav-blur": "0px", "--nav-line": 0, "--nav-lift": 0 },
      {
        "--nav-pad": "12px",
        "--nav-bg": 0.82,
        "--nav-blur": "18px",
        "--nav-line": 1,
        "--nav-lift": 1,
        ease: "none",
      },
    );
    return () => {
      tl.scrollTrigger?.kill();
      tl.kill();
      gsap.set(nav, { clearProps: "--nav-pad,--nav-bg,--nav-blur,--nav-line,--nav-lift" });
    };
  }, []);

  /* --- which section am I in ----------------------------------------- */
  useEffect(() => {
    const triggers = LINKS.map(({ id }) => {
      const el = document.getElementById(id);
      if (!el) return null;
      return ScrollTrigger.create({
        trigger: el,
        start: "top 55%",
        end: "bottom 55%",
        onToggle: ({ isActive }) => setCurrent((c) => (isActive ? id : c === id ? null : c)),
      });
    });
    return () => triggers.forEach((t) => t?.kill());
  }, []);

  /* --- the mobile sheet ------------------------------------------------
     Built as a paused timeline once and played forward or backward, so an
     interrupted open reverses from wherever it had reached rather than
     snapping and starting again. */
  const sheet = useRef<gsap.core.Timeline | null>(null);
  useEffect(() => {
    const el = menuRef.current;
    if (!el) return;
    const items = el.querySelectorAll<HTMLElement>("[data-sheet-item]");
    const tl = gsap.timeline({ paused: true });
    tl.fromTo(
      el,
      { opacity: 0, clipPath: "inset(0 0 100% 0)" },
      { opacity: 1, clipPath: "inset(0 0 0% 0)", duration: DUR.quick, ease: EASE.io },
    ).from(
      items,
      { opacity: 0, y: 26, filter: "blur(8px)", duration: DUR.reveal, ease: EASE.out, stagger: 0.05 },
      "-=0.18",
    );
    sheet.current = tl;
    return () => {
      tl.kill();
      sheet.current = null;
    };
  }, []);

  useEffect(() => {
    const tl = sheet.current;
    if (!tl) return;
    if (reduced()) {
      tl.progress(open ? 1 : 0).pause();
    } else if (open) {
      tl.play();
    } else {
      tl.reverse();
    }
    // `inert` set imperatively: React 18's typings predate the attribute, and
    // it is the only thing that keeps Tab out of a closed sheet that is still
    // in the tree so it can animate out.
    if (menuRef.current) menuRef.current.toggleAttribute("inert", !open);
    // The sheet covers the page; letting the document behind it scroll is the
    // classic mobile-menu bug where closing drops you somewhere else.
    document.body.style.overflow = open ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  /** Anchor navigation, done in JS so it can respect the motion preference
   *  and offset for the bar without a global `scroll-behavior` that would
   *  follow the visitor into the console. */
  const goTo = (id: string) => (e: React.MouseEvent) => {
    const el = document.getElementById(id);
    if (!el) return;
    e.preventDefault();
    setOpen(false);
    window.scrollTo({
      top: el.getBoundingClientRect().top + window.scrollY - 68,
      behavior: reduced() ? "auto" : "smooth",
    });
  };

  return (
    <>
      <header className="lp-nav" ref={navRef}>
        <div className="lp-nav__surface" aria-hidden="true" />
        <div className="lp-nav__inner">
          <Link className="lp-nav__brand" to="/" aria-label="AegisAI home">
            <Logo size={21} />
          </Link>

          <nav className="lp-nav__links" aria-label="Sections">
            {LINKS.map((l) => (
              <a
                key={l.id}
                href={`#${l.id}`}
                className="lp-nav__link"
                data-current={current === l.id || undefined}
                aria-current={current === l.id ? "true" : undefined}
                onClick={goTo(l.id)}
              >
                <span>{l.label}</span>
              </a>
            ))}
          </nav>

          <div className="lp-nav__right">
            <button
              type="button"
              className="lp-nav__icon"
              onClick={toggle}
              aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
            >
              {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
            </button>
            <UserMenu tone="landing" />
            <button
              type="button"
              className="lp-nav__icon lp-nav__burger"
              onClick={() => setOpen((o) => !o)}
              aria-expanded={open}
              aria-controls="lp-sheet"
              aria-label={open ? "Close menu" : "Open menu"}
            >
              {open ? <X size={18} /> : <Menu size={18} />}
            </button>
          </div>
        </div>
      </header>

      {/* Rendered always, hidden from assistive tech and from hit-testing when
          closed — a menu that unmounts cannot animate out. */}
      <div
        id="lp-sheet"
        className="lp-sheet"
        ref={menuRef}
        data-open={open || undefined}
        aria-hidden={!open}
      >
        <nav className="lp-sheet__nav" aria-label="Sections">
          {LINKS.map((l, i) => (
            <a
              key={l.id}
              href={`#${l.id}`}
              className="lp-sheet__link"
              data-sheet-item
              onClick={goTo(l.id)}
            >
              <span className="lp-sheet__n lp-mono">{String(i + 1).padStart(2, "0")}</span>
              {l.label}
            </a>
          ))}
        </nav>
        <div className="lp-sheet__foot" data-sheet-item>
          <Link className="lp-btn lp-btn--primary" to="/analyze" onClick={() => setOpen(false)}>
            Start an investigation
          </Link>
        </div>
      </div>
    </>
  );
}
