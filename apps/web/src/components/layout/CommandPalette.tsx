/**
 * ⌘K palette — keyboard navigation between screens and demo actions.
 *
 * Worth the ~120 lines for one reason: during a demo, hunting for a nav item
 * with a trackpad in front of an audience is the slowest, most visible thing
 * you can do. Two keystrokes to any screen is the difference between a
 * rehearsed run and a fumbled one.
 */

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { CornerDownLeft, Search } from "lucide-react";
import type { NavItem } from "./nav";

interface Props {
  open: boolean;
  onClose: () => void;
  /** The destinations this user can actually reach — the shell passes the
   *  same role-filtered list the sidebar renders, so the palette never offers
   *  a screen that would bounce them straight back out of it. */
  items: NavItem[];
}

export function CommandPalette({ open, onClose, items }: Props) {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const returnFocusRef = useRef<HTMLElement | null>(null);
  const listRef = useRef<HTMLUListElement>(null);

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return items;
    // Match on the blurb/detail too, so "upi" finds Analyze even though the
    // word does not appear in its label.
    return items.filter((item) =>
      `${item.label} ${item.blurb} ${item.detail}`.toLowerCase().includes(q),
    );
  }, [query, items]);

  /**
   * Opening and closing a modal is a focus contract, not a visibility change.
   *
   * `useLayoutEffect`, not `useEffect` + `requestAnimationFrame`: the input is
   * in the DOM by the time layout effects run, so it can be focused directly.
   * The rAF version was one frame late and, on a machine that drops that
   * frame, never ran at all — which left focus on `<body>`, and with it the
   * Escape handler (bound to the panel) unreachable.
   *
   * Focus goes back where it came from on close. A palette that swallows the
   * user's place in the page is worse than no palette.
   */
  useLayoutEffect(() => {
    if (!open) return;
    returnFocusRef.current = document.activeElement as HTMLElement | null;
    setQuery("");
    setActive(0);
    inputRef.current?.focus();
    return () => {
      returnFocusRef.current?.focus?.();
    };
  }, [open]);

  // Escape anywhere, not only inside the panel — the scrim takes focus after a
  // click on it, and a modal you cannot dismiss from the keyboard is a trap.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  useEffect(() => {
    setActive(0);
  }, [query]);

  // Arrowing past the fold has to bring the option with it, or the selection
  // is somewhere the user cannot see.
  useEffect(() => {
    listRef.current
      ?.querySelector<HTMLElement>("[data-active]")
      ?.scrollIntoView({ block: "nearest" });
  }, [active]);

  if (!open) return null;

  const go = (to: string) => {
    navigate(to);
    onClose();
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      onClose();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => (i + 1) % Math.max(results.length, 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => (i - 1 + results.length) % Math.max(results.length, 1));
    } else if (e.key === "Enter" && results[active]) {
      e.preventDefault();
      go(results[active].to);
    }
  };

  return (
    <div className="palette" role="dialog" aria-modal="true" aria-label="Jump to a screen">
      <div className="palette__scrim" onClick={onClose} />
      <div className="palette__panel" onKeyDown={onKeyDown}>
        <div className="palette__search">
          <Search size={16} />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Jump to a screen…"
            aria-label="Search screens"
          />
          <kbd>esc</kbd>
        </div>

        <ul className="palette__list" role="listbox">
          {results.map((item, i) => (
            <li key={item.to}>
              <button
                className="palette__item"
                data-active={i === active || undefined}
                onMouseEnter={() => setActive(i)}
                onClick={() => go(item.to)}
                role="option"
                aria-selected={i === active}
              >
                <item.icon size={16} />
                <span className="palette__text">
                  <span className="palette__label">{item.label}</span>
                  <span className="palette__blurb">{item.blurb}</span>
                </span>
                {i === active && <CornerDownLeft size={13} className="palette__enter" />}
              </button>
            </li>
          ))}
          {!results.length && (
            <li className="palette__empty">
              No screen matches “{query}”. Try “message”, “call” or “graph”.
            </li>
          )}
        </ul>
      </div>
    </div>
  );
}
