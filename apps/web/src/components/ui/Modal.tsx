/**
 * A general modal dialog (G-07).
 *
 * The product had one bespoke dialog (the command palette). This is the
 * general one, with the behaviour a dialog owes a keyboard and a screen
 * reader:
 *
 * - `role="dialog"`, `aria-modal`, named by its title.
 * - Focus moves in on open — to the first control, or the dialog itself —
 *   and is **trapped**: Tab and Shift+Tab cycle inside it.
 * - **Escape** closes it, as does a click on the backdrop (unless
 *   `dismissable={false}`, for a step that must be answered).
 * - Focus **returns** to whatever opened it.
 * - The page behind does not scroll while it is open.
 */

import { X } from "lucide-react";
import { useEffect, useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

interface Props {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  /** Buttons, right-aligned under the body. */
  footer?: ReactNode;
  /** False for a step that must be answered: no Escape, no backdrop close. */
  dismissable?: boolean;
}

export function Modal({ open, onClose, title, children, footer, dismissable = true }: Props) {
  const dialog = useRef<HTMLDivElement>(null);
  const titleId = useId();

  useEffect(() => {
    if (!open) return;
    const opener = document.activeElement as HTMLElement | null;
    const node = dialog.current;
    const first = node?.querySelector<HTMLElement>(FOCUSABLE);
    (first ?? node)?.focus();
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = overflow;
      opener?.focus?.();
    };
  }, [open]);

  if (!open) return null;

  function onKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    if (e.key === "Escape" && dismissable) {
      e.stopPropagation();
      onClose();
      return;
    }
    if (e.key !== "Tab" || !dialog.current) return;
    const items = Array.from(dialog.current.querySelectorAll<HTMLElement>(FOCUSABLE));
    if (items.length === 0) {
      e.preventDefault();
      return;
    }
    const first = items[0];
    const last = items[items.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }

  return createPortal(
    <div
      className="modal__backdrop"
      onMouseDown={(e) => {
        if (dismissable && e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={dialog}
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        onKeyDown={onKeyDown}
      >
        <div className="modal__head">
          <h2 className="modal__title" id={titleId}>{title}</h2>
          {dismissable && (
            <button type="button" className="iconbtn" aria-label="Close" onClick={onClose}>
              <X size={16} aria-hidden="true" />
            </button>
          )}
        </div>
        <div className="modal__body">{children}</div>
        {footer && <div className="modal__foot">{footer}</div>}
      </div>
    </div>,
    document.body,
  );
}
