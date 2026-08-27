/**
 * Persistent chrome: sidebar, top bar, command palette, outlet.
 *
 * The shell owns four things worth calling out:
 *
 * **Live status is global.** Whether the API is reachable, and what is
 * degraded, is shown on every screen rather than being discovered per-page. A
 * user who does not know the classifier fell back to the lexical model will
 * read its output as if it were the good one. It sits in the sidebar footer
 * rather than the top bar because the top bar's right-hand cluster had to
 * hide it below 620px — the viewport where a degraded backend is *most*
 * likely, since that is the phone someone reaches for mid-call.
 *
 * **The sidebar owns the left column outright**, top to bottom, so the logo
 * has one home and the page title gets the top bar's leading edge. Previously
 * the brand sat in the top bar next to a tagline and the page's own H1
 * repeated the location two rows below it.
 *
 * **Navigation is role-aware.** `navGroups` returns one group for a citizen
 * and two for an analyst, so an analyst's tools are in their navigation
 * instead of behind a link on the Profile page.
 *
 * **Layout mode is not the shell's business.** The console is a fixed
 * instrument viewport and everything else is a document, but the landing and
 * the login screen render *outside* this component — so a shell-owned switch
 * could never speak for them, and never unset itself on the way out. It lives
 * in `LayoutMode` (App.tsx), one level up, where it covers every route.
 */

import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import {
  AlertTriangle,
  CircleDot,
  LogOut,
  Menu,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  Sun,
  X,
} from "lucide-react";
import { Logo, LogoMark } from "@/components/brand/Logo";
import { navAll, navGroups } from "./nav";
import { UserMenu } from "./UserMenu";
import { CommandPalette } from "./CommandPalette";
import { RouteBoundary } from "./RouteBoundary";
import { useTheme } from "@/context/ThemeContext";
import { useAuth } from "@/context/AuthContext";
import { useHealth } from "@/hooks/useHealth";
import { armFailsafe } from "@/lib/gsap";

const COLLAPSE_KEY = "aegis:sidebar-collapsed";

export function AppShell() {
  const location = useLocation();
  const { theme, toggle } = useTheme();
  const health = useHealth();
  const auth = useAuth();
  const [collapsed, setCollapsed] = useState(
    () => typeof localStorage !== "undefined" && localStorage.getItem(COLLAPSE_KEY) === "1",
  );
  const [mobileOpen, setMobileOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const burgerRef = useRef<HTMLButtonElement>(null);
  const drawerRef = useRef<HTMLElement>(null);

  // Navigation is filtered by permission, not by role name: `nav.ts` asks
  // "can you do this" and the answer comes from the server's own grant list.
  const groups = navGroups(auth.permissions, auth.authed);
  const here = navAll(auth.permissions, auth.authed).find(
    (i) => location.pathname === i.to || location.pathname.startsWith(`${i.to}/`),
  );

  useEffect(() => {
    localStorage.setItem(COLLAPSE_KEY, collapsed ? "1" : "0");
  }, [collapsed]);

  // Re-armed per route, not once per app load: each screen starts its own
  // entrance animation, so a failsafe that only ran at boot would not protect
  // the console you navigate to two minutes later. Also re-armed when the tab
  // comes back, because GSAP's ticker sleeps while backgrounded and leaves
  // any in-flight entrance frozen part-way.
  useEffect(() => {
    armFailsafe();
    const onVisible = () => {
      if (!document.hidden) armFailsafe();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, [location.pathname]);

  // Close the mobile drawer on navigation — leaving it open over the page the
  // user just chose is the classic drawer bug.
  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname]);

  // The drawer is a modal surface on mobile: the page behind it must not
  // scroll, Escape must close it, and focus must land inside it and come back
  // to the button that opened it.
  useEffect(() => {
    if (!mobileOpen) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const first = drawerRef.current?.querySelector<HTMLElement>("a, button");
    first?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setMobileOpen(false);
        burgerRef.current?.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prev;
      document.removeEventListener("keydown", onKey);
    };
  }, [mobileOpen]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((open) => !open);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const degraded = health.data?.degraded ?? [];

  return (
    <div className="shell2" data-collapsed={collapsed || undefined}>
      <aside
        className="sidebar"
        ref={drawerRef}
        data-open={mobileOpen || undefined}
        aria-label="Main navigation"
        aria-hidden={undefined}
      >
        <div className="sidebar__brand">
          <NavLink to="/" className="sidebar__logo" aria-label="AegisAI home">
            {collapsed ? <LogoMark size={22} /> : <Logo size={22} />}
          </NavLink>
          <button
            className="iconbtn sidebar__collapse"
            onClick={() => setCollapsed((c) => !c)}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            aria-pressed={collapsed}
          >
            {collapsed ? <PanelLeftOpen size={17} /> : <PanelLeftClose size={17} />}
          </button>
        </div>

        <nav className="sidebar__nav">
          {groups.map((group) => (
            <div className="sidebar__group" key={group.id}>
              <p className="label sidebar__grouplabel">{group.label}</p>
              {group.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) => `sidenav ${isActive ? "sidenav--active" : ""}`}
                  data-tooltip={`${item.label} — ${item.blurb}`}
                >
                  <item.icon size={17} className="sidenav__icon" aria-hidden="true" />
                  <span className="sidenav__text">
                    <span className="sidenav__label">{item.label}</span>
                    <span className="sidenav__blurb">{item.blurb}</span>
                  </span>
                </NavLink>
              ))}
            </div>
          ))}
        </nav>

        <div className="sidebar__foot">
          <StatusPill loading={health.loading} online={!!health.data} degraded={degraded} />

          {auth.authed && auth.user ? (
            <div className="userchip">
              <span className="userchip__avatar" aria-hidden="true">
                {(auth.user.display_name || auth.user.email).slice(0, 1).toUpperCase()}
              </span>
              <span className="userchip__text">
                <span className="userchip__email" data-tooltip={auth.user.email}>
                  {auth.user.display_name}
                </span>
                {/* Both lines ellipsize in a 248px rail, so the full values
                    ride along as tooltips rather than being lost. */}
                <span
                  className="userchip__role"
                  data-tooltip={`${auth.user.role}${auth.org?.name ? ` · ${auth.org.name}` : ""}`}
                >
                  {auth.user.role}
                  {auth.org?.name ? ` · ${auth.org.name}` : ""}
                </span>
              </span>
              <button
                className="iconbtn userchip__out"
                onClick={() => void auth.logout()}
                aria-label="Sign out"
              >
                <LogOut size={15} />
              </button>
            </div>
          ) : (
            <NavLink className="btn2 btn2--sm btn2--block" to="/login">
              Sign in
            </NavLink>
          )}

          <p className="sidebar__helpline">
            Fraud in progress? Call <strong className="mono">1930</strong> or file at{" "}
            <a href="https://cybercrime.gov.in" target="_blank" rel="noreferrer">
              cybercrime.gov.in
            </a>
            .
          </p>
        </div>
      </aside>

      <header className="topbar2">
        <button
          className="iconbtn topbar2__burger"
          ref={burgerRef}
          onClick={() => setMobileOpen((o) => !o)}
          aria-label={mobileOpen ? "Close navigation" : "Open navigation"}
          aria-expanded={mobileOpen}
        >
          {mobileOpen ? <X size={18} /> : <Menu size={18} />}
        </button>

        {/* On mobile the sidebar is off-canvas, so the brand needs a home in
            the bar; on desktop the sidebar already shows it and repeating it
            here is the duplication this restructure removed. */}
        <NavLink to="/" className="topbar2__brand" aria-label="AegisAI home">
          <Logo size={19} />
        </NavLink>

        <nav className="crumbs" aria-label="Breadcrumb">
          <span className="crumbs__here">{here?.label ?? "AegisAI"}</span>
          {here?.blurb && <span className="crumbs__blurb">{here.blurb}</span>}
        </nav>

        <button className="paletteHint" onClick={() => setPaletteOpen(true)}>
          <Search size={14} aria-hidden="true" />
          <span>Search or jump to…</span>
          <kbd aria-hidden="true">⌘K</kbd>
        </button>

        <div className="topbar2__right">
          <button
            className="iconbtn"
            onClick={toggle}
            aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
          >
            {theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
          </button>
          {/* The same identity control the landing page carries. The sidebar
              footer's chip is the desktop rail's version of it and is hidden on
              mobile, where the rail is off-canvas — this is the one that is
              always reachable. */}
          <UserMenu />
        </div>
      </header>

      {mobileOpen && (
        <div className="scrim" onClick={() => setMobileOpen(false)} aria-hidden="true" />
      )}

      <main className="content" id="main" tabIndex={-1}>
        {/* Scoped to the outlet: a page that throws costs you that page,
            not the navigation you would use to get away from it. */}
        <RouteBoundary resetKey={location.pathname}>
          <Outlet />
        </RouteBoundary>
      </main>

      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        items={navAll(auth.permissions, auth.authed)}
      />
    </div>
  );
}

/**
 * The one place the product says out loud what is and is not working.
 * `title` carries the specific tags (`clf:lexical_fallback`) so "3 degraded"
 * is a starting point rather than the whole answer.
 */
function StatusPill({
  loading,
  online,
  degraded,
}: {
  loading: boolean;
  online: boolean;
  degraded: string[];
}) {
  if (loading) {
    return (
      <span className="statuspill" data-state="pending">
        <span className="statuspill__dot" aria-hidden="true" />
        Checking systems
      </span>
    );
  }
  if (!online) {
    return (
      <span
        className="statuspill tt"
        data-state="offline"
        data-tooltip="Start it with: .venv/bin/uvicorn services.api.main:app --port 8000"
      >
        <AlertTriangle size={13} aria-hidden="true" />
        API offline
      </span>
    );
  }
  if (degraded.length) {
    return (
      <span className="statuspill tt" data-state="degraded" data-tooltip={degraded.join("\n")}>
        <AlertTriangle size={13} aria-hidden="true" />
        {degraded.length} running degraded
      </span>
    );
  }
  return (
    <span className="statuspill" data-state="ok">
      <CircleDot size={13} aria-hidden="true" />
      All systems live
    </span>
  );
}
