/**
 * ⌘K palette — keyboard navigation between screens and demo actions.
 *
 * Worth the ~120 lines for one reason: during a demo, hunting for a nav item
 * with a trackpad in front of an audience is the slowest, most visible thing
 * you can do. Two keystrokes to any screen is the difference between a
 * rehearsed run and a fumbled one.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { CornerDownLeft, Search } from "lucide-react";
import { NAV } from "./nav";

interface Props {
  open: boolean;
  onClose: () => void;
}

export function CommandPalette({ open, onClose }: Props) {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return NAV;
    // Match on the blurb too, so "upi" finds the Analyzer even though the
    // word does not appear in its label.
    return NAV.filter((item) =>
      `${item.label} ${item.blurb} ${item.detail} ${item.group}`
        .toLowerCase()
        .includes(q),
    );
  }, [query]);

  useEffect(() => {
    if (open) {
      setQuery("");
      setActive(0);
      // rAF, not a bare focus() — the element is not in the layout yet on the
      // frame the state flips.
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  useEffect(() => {
    setActive(0);
  }, [query]);

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
                <span className="palette__group label">{item.group}</span>
                {i === active && <CornerDownLeft size={13} className="palette__enter" />}
              </button>
            </li>
          ))}
          {!results.length && (
            <li className="palette__empty">No screen matches “{query}”.</li>
          )}
        </ul>
      </div>
    </div>
  );
}
