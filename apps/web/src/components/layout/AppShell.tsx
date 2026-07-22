/**
 * Persistent chrome: top bar, collapsible sidebar, command palette, outlet.
 *
 * The shell owns two things worth calling out:
 *
 * **Live status is global.** Whether the API is reachable, and what is
 * degraded, is shown in the top bar on every screen rather than being
 * discovered per-page. A user who does not know the classifier fell back to
 * the lexical model will read its output as if it were the good one.
 *
 * **The console route opts out of scrolling.** It is a fixed instrument
 * viewport; everything else is a document. Rather than fighting
 * `body { overflow: hidden }` from global.css, the shell sets a data attribute
 * and the stylesheet keys off it.
 */

import { useEffect, useLayoutEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import {
  AlertTriangle,
  CircleDot,
  Command,
  LogOut,
  Menu,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
  Sun,
  X,
} from "lucide-react";
import { GROUPS, byGroup } from "./nav";
import { CommandPalette } from "./CommandPalette";
import { RouteBoundary } from "./RouteBoundary";
import { useTheme } from "@/context/ThemeContext";
import { useAuth } from "@/context/AuthContext";
import { useHealth } from "@/hooks/useHealth";
import { armFailsafe } from "@/lib/gsap";

const FIXED_ROUTES = ["/console"];

export function AppShell() {
  const location = useLocation();
  const { theme, toggle } = useTheme();
  const health = useHealth();
  const auth = useAuth();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);

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

  // Fixed-viewport routes vs scrolling document routes.
  //
  // useLayoutEffect, not useEffect, and it matters: React runs child effects
  // before parent effects, so with useEffect a page's own entrance animations
  // initialise while the document is still `overflow: hidden` at viewport
  // height. GSAP ScrollTrigger then caches start positions against a page that
  // cannot scroll, and every scroll-triggered reveal on Home stayed at
  // opacity 0 forever. Setting the attribute during the layout phase means the
  // document is already scrollable when children measure it.
  useLayoutEffect(() => {
    const fixed = FIXED_ROUTES.some((r) => location.pathname.startsWith(r));
    document.documentElement.dataset.layout = fixed ? "fixed" : "flow";
  }, [location.pathname]);

  // Close the mobile drawer on navigation — leaving it open over the page the
  // user just chose is the classic drawer bug.
  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    document.body.style.overflow = mobileOpen ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
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
      <header className="topbar2">
        <button
          className="iconbtn topbar2__burger"
          onClick={() => setMobileOpen((o) => !o)}
          aria-label={mobileOpen ? "Close navigation" : "Open navigation"}
        >
          {mobileOpen ? <X size={18} /> : <Menu size={18} />}
        </button>

        <button
          className="iconbtn topbar2__collapse"
          onClick={() => setCollapsed((c) => !c)}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
        </button>

        <NavLink to="/" className="brand2">
          <span className="brand2__mark" aria-hidden="true" />
          <span className="brand2__name">PRESAGE</span>
          <span className="brand2__tag">It knows what the scammer will say next</span>
        </NavLink>

        <div className="topbar2__right">
          <button className="paletteHint" onClick={() => setPaletteOpen(true)}>
            <Command size={13} />
            <span>Jump to…</span>
            <kbd>⌘K</kbd>
          </button>

          <StatusPill loading={health.loading} online={!!health.data} degraded={degraded} />

          {auth.authed && auth.user && (
            <span className="userchip" title={`${auth.user.email} · ${auth.org?.name ?? ""}`}>
              <span className="userchip__role">{auth.user.role}</span>
              <span className="userchip__email">{auth.user.email}</span>
              <button
                className="userchip__out"
                onClick={auth.logout}
                aria-label="Sign out"
                title="Sign out"
              >
                <LogOut size={13} />
              </button>
            </span>
          )}

          <button className="iconbtn" onClick={toggle} aria-label="Toggle theme">
            {theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
          </button>
        </div>
      </header>

      <aside className="sidebar" data-open={mobileOpen || undefined}>
        <nav aria-label="Sections">
          {GROUPS.map((group) => (
            <div className="sidebar__group" key={group}>
              <p className="label sidebar__grouplabel">{group}</p>
              {byGroup(group).map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    `sidenav ${isActive ? "sidenav--active" : ""}`
                  }
                  title={collapsed ? `${item.label} — ${item.blurb}` : undefined}
                >
                  <item.icon size={17} className="sidenav__icon" />
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
          <p className="label">Report fraud</p>
          <p className="sidebar__helpline">
            Call <strong className="mono">1930</strong> or file at{" "}
            <a href="https://cybercrime.gov.in" target="_blank" rel="noreferrer">
              cybercrime.gov.in
            </a>
            . Reporting within the first few hours is what gets money frozen.
          </p>
        </div>
      </aside>

      {mobileOpen && (
        <div className="scrim" onClick={() => setMobileOpen(false)} aria-hidden="true" />
      )}

      <main className="content">
        {/* Scoped to the outlet: a page that throws costs you that page,
            not the navigation you would use to get away from it. */}
        <RouteBoundary resetKey={location.pathname}>
          <Outlet />
        </RouteBoundary>
      </main>

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </div>
  );
}

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
        <CircleDot size={13} /> checking
      </span>
    );
  }
  if (!online) {
    return (
      <span
        className="statuspill"
        data-state="offline"
        title="Start it with: .venv/bin/uvicorn services.api.main:app --port 8000"
      >
        <AlertTriangle size={13} /> API offline
      </span>
    );
  }
  if (degraded.length) {
    // Naming the degradation rather than showing a generic warning. "Reduced"
    // with a tooltip listing `clf:lexical_fallback` tells the user which half
    // of the system is the weaker one.
    return (
      <span className="statuspill" data-state="degraded" title={degraded.join("\n")}>
        <AlertTriangle size={13} /> {degraded.length} degraded
      </span>
    );
  }
  return (
    <span className="statuspill" data-state="ok">
      <CircleDot size={13} /> all systems live
    </span>
  );
}
