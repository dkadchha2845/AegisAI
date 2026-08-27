/**
 * The signed-in identity, and what you can do with it — §20, §21, §22.
 *
 * One component, rendered by both the landing header and the app shell, because
 * "am I signed in, and as whom" must not be answered two different ways on two
 * different screens. Signed out it is a Sign in / Get started pair; signed in it
 * is an avatar, a name and a role badge that opens a menu.
 *
 * The menu is a real menu, not a hover card:
 *
 *   * **Keyboard.** Enter/Space/ArrowDown open it and focus the first item;
 *     Arrow keys move; Home/End jump; Escape closes and returns focus to the
 *     button; Tab out closes it. `role="menu"` / `role="menuitem"` so a screen
 *     reader announces it as one.
 *   * **Click-outside** via a pointerdown listener on the document, not a blur
 *     handler — blur fires before the click lands on the item you were aiming
 *     at, which is why "the menu closes and nothing happens" is such a common
 *     bug in hand-rolled dropdowns.
 *   * **Mobile.** Below 640px it becomes a bottom sheet with full-width rows,
 *     because a 264px dropdown anchored to a 32px avatar is not a touch target.
 *
 * **The panel is portalled to `document.body` and positioned from the trigger's
 * rect.** It has to be. `.topbar2` carries `backdrop-filter: blur(14px)`, and a
 * filtered element becomes the containing block for every `position: fixed`
 * descendant — so the bottom sheet's `inset: auto 0 0 0` resolved against a
 * 56px-tall header instead of the viewport, and rendered off the top of the
 * page with only its last row visible. Anchoring in JS also means no future
 * ancestor with a transform, filter or `contain` can move this menu again.
 *
 * The destinations are filtered by permission, so a citizen's menu does not
 * offer them the administration console. That is UX — the route and the API
 * behind it enforce the same thing independently.
 */

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Link, useNavigate } from "react-router-dom";
import {
  ChevronDown,
  FolderArchive,
  LayoutDashboard,
  LogOut,
  Settings,
  ShieldCheck,
  UserRound,
} from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import type { PermissionCode } from "@/lib/api";

interface MenuItem {
  to: string;
  label: string;
  icon: typeof UserRound;
  /** Every code must be held for the row to appear. */
  needs?: PermissionCode[];
}

const ITEMS: MenuItem[] = [
  { to: "__home__", label: "Dashboard", icon: LayoutDashboard },
  { to: "/reports", label: "My investigations", icon: FolderArchive, needs: ["REPORT_READ_OWN"] },
  { to: "/profile", label: "Profile", icon: UserRound },
  { to: "/profile#settings", label: "Settings", icon: Settings },
  { to: "/admin/dashboard", label: "Administration", icon: ShieldCheck, needs: ["USER_MANAGE"] },
];

export function UserMenu({ tone = "app" }: { tone?: "app" | "landing" }) {
  const auth = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [anchor, setAnchor] = useState<{ top: number; right: number } | null>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  const close = useCallback((focusButton = false) => {
    setOpen(false);
    if (focusButton) buttonRef.current?.focus();
  }, []);

  // Where the panel hangs, in viewport coordinates. Measured rather than
  // inherited, for the containing-block reason in the header comment.
  // useLayoutEffect, so the first paint is already in the right place.
  useLayoutEffect(() => {
    if (!open) return;
    const place = () => {
      const r = buttonRef.current?.getBoundingClientRect();
      if (r) setAnchor({ top: r.bottom + 8, right: window.innerWidth - r.right });
    };
    place();
    window.addEventListener("resize", place);
    // Capture phase: the app shell scrolls its own container rather than the
    // window, so a bubbling listener would never hear it and the panel would
    // hang in mid-air while the page moved underneath it.
    window.addEventListener("scroll", place, true);
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  }, [open]);

  // Click-outside. pointerdown rather than blur: blur fires before the click
  // reaches the item, so a blur-closed menu eats its own selection.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: PointerEvent) => {
      const t = e.target as Node;
      if (menuRef.current?.contains(t) || buttonRef.current?.contains(t)) return;
      close();
    };
    document.addEventListener("pointerdown", onDown);
    return () => document.removeEventListener("pointerdown", onDown);
  }, [open, close]);

  // Escape anywhere closes and hands focus back.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        close(true);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, close]);

  // Focus the first item when the menu opens from the keyboard or the mouse —
  // a menu you have to tab into is a menu a keyboard user cannot use.
  useEffect(() => {
    if (!open) return;
    const first = menuRef.current?.querySelector<HTMLElement>("[role='menuitem']");
    first?.focus();
  }, [open]);

  const onMenuKeyDown = (e: React.KeyboardEvent) => {
    const items = Array.from(
      menuRef.current?.querySelectorAll<HTMLElement>("[role='menuitem']") ?? [],
    );
    if (!items.length) return;
    const i = items.indexOf(document.activeElement as HTMLElement);
    if (e.key === "ArrowDown") {
      e.preventDefault();
      items[(i + 1) % items.length].focus();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      items[(i - 1 + items.length) % items.length].focus();
    } else if (e.key === "Home") {
      e.preventDefault();
      items[0].focus();
    } else if (e.key === "End") {
      e.preventDefault();
      items[items.length - 1].focus();
    } else if (e.key === "Tab") {
      close();
    }
  };

  const signOut = async () => {
    close();
    await auth.logout();
    // Back to the landing page, where the navbar is a Sign in / Get started
    // pair again — §5, and the last step of §41.
    navigate("/", { replace: true });
  };

  if (auth.loading) {
    return <span className="usermenu__skeleton" aria-hidden="true" />;
  }

  if (!auth.authed || !auth.user) {
    return (
      <div className="usermenu__signedout">
        <Link className="btn2 btn2--sm" to="/login">
          Sign in
        </Link>
        <Link className="btn2 btn2--primary btn2--sm" to="/signup">
          Get started
        </Link>
      </div>
    );
  }

  const user = auth.user;
  const initial = (user.display_name || user.email).slice(0, 1).toUpperCase();
  const items = ITEMS.filter((it) => !it.needs || auth.can(...it.needs));

  return (
    <div className="usermenu" data-tone={tone}>
      <button
        ref={buttonRef}
        type="button"
        className="usermenu__trigger"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown" && !open) {
            e.preventDefault();
            setOpen(true);
          }
        }}
      >
        <span className="usermenu__avatar" aria-hidden="true">
          {initial}
        </span>
        <span className="usermenu__id">
          <span className="usermenu__name">{user.display_name}</span>
          <span className="usermenu__role">{user.role}</span>
        </span>
        <ChevronDown size={14} className="usermenu__chev" aria-hidden="true" />
      </button>

      {open &&
        createPortal(
          <div className="usermenu__overlay" data-tone={tone}>
            {/* The scrim only paints at the mobile breakpoint (see
                modules.css); on desktop it collapses to nothing rather than
                covering the page. */}
            <div className="usermenu__scrim" aria-hidden="true" onClick={() => close()} />
            <div
              ref={menuRef}
              className="usermenu__panel"
              role="menu"
              aria-label={`Account: ${user.display_name}`}
              onKeyDown={onMenuKeyDown}
              style={anchor ? { top: anchor.top, right: anchor.right } : undefined}
            >
              <div className="usermenu__head">
                <span className="usermenu__avatar usermenu__avatar--lg" aria-hidden="true">
                  {initial}
                </span>
                <span className="usermenu__headtext">
                  <strong>{user.display_name}</strong>
                  <span className="small faint">{user.email}</span>
                  <span className="chip chip--caps usermenu__badge">{user.role}</span>
                </span>
              </div>

              {auth.org?.name && (
                <p className="usermenu__org small faint">{auth.org.name}</p>
              )}

              <div className="usermenu__group">
                {items.map((it) => (
                  <Link
                    key={it.to}
                    to={it.to === "__home__" ? auth.home : it.to}
                    role="menuitem"
                    className="usermenu__item"
                    onClick={() => close()}
                  >
                    <it.icon size={15} aria-hidden="true" />
                    {it.label}
                  </Link>
                ))}
              </div>

              <div className="usermenu__group">
                <button
                  type="button"
                  role="menuitem"
                  className="usermenu__item usermenu__item--danger"
                  onClick={() => void signOut()}
                >
                  <LogOut size={15} aria-hidden="true" />
                  Sign out
                </button>
              </div>
            </div>
          </div>,
          document.body,
        )}
    </div>
  );
}
