/**
 * Toasts — a short confirmation that does not interrupt (G-06).
 *
 * `--z-toast` was reserved in tokens.css and nothing used it. The rules:
 *
 * - **Announced, not focused.** The stack is a polite live region; an error
 *   toast is `role="alert"`. Focus never moves to a toast — that would yank
 *   a keyboard user out of what they were doing.
 * - **Time to read.** A toast dismisses itself after `duration`, and the
 *   timer **pauses** while it is hovered or holds focus, so nobody loses a
 *   message while reading it or reaching for its button.
 * - **Dismissable by keyboard.** Every toast has a close button; Escape
 *   dismisses the toast that holds focus.
 * - **Not for decisions.** A toast never carries the only copy of something
 *   the user must act on; that belongs in the page or a `Modal`.
 */

import { X } from "lucide-react";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

export type ToastTone = "info" | "ok" | "bad";

export interface ToastInput {
  title: string;
  body?: string;
  tone?: ToastTone;
  /** Milliseconds before it dismisses itself. 0 = stays until closed. */
  duration?: number;
}

interface ToastItem extends Required<Omit<ToastInput, "body">> {
  id: number;
  body?: string;
}

interface ToastApi {
  show: (toast: ToastInput) => number;
  dismiss: (id: number) => void;
}

const ToastContext = createContext<ToastApi | null>(null);

export const DEFAULT_DURATION = 6000;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const next = useRef(1);

  const dismiss = useCallback((id: number) => {
    setItems((list) => list.filter((t) => t.id !== id));
  }, []);

  const show = useCallback((toast: ToastInput) => {
    const id = next.current++;
    setItems((list) => [
      ...list,
      { id, title: toast.title, body: toast.body, tone: toast.tone ?? "info", duration: toast.duration ?? DEFAULT_DURATION },
    ]);
    return id;
  }, []);

  const api = useMemo(() => ({ show, dismiss }), [show, dismiss]);

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="toasts" role="region" aria-label="Notifications" aria-live="polite">
        {items.map((t) => (
          <ToastView key={t.id} toast={t} onClose={() => dismiss(t.id)} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  const api = useContext(ToastContext);
  if (!api) throw new Error("useToast() needs a <ToastProvider> above it");
  return api;
}

function ToastView({ toast, onClose }: { toast: ToastItem; onClose: () => void }) {
  const [paused, setPaused] = useState(false);
  const remaining = useRef(toast.duration);
  const started = useRef(0);

  useEffect(() => {
    if (paused || toast.duration <= 0) return;
    started.current = Date.now();
    const timer = window.setTimeout(onClose, remaining.current);
    return () => {
      window.clearTimeout(timer);
      remaining.current = Math.max(0, remaining.current - (Date.now() - started.current));
    };
  }, [paused, toast.duration, onClose]);

  return (
    <div
      className="toast"
      data-tone={toast.tone}
      role={toast.tone === "bad" ? "alert" : "status"}
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocus={() => setPaused(true)}
      onBlur={() => setPaused(false)}
      onKeyDown={(e) => {
        if (e.key === "Escape") onClose();
      }}
    >
      <div className="toast__text">
        <p className="toast__title">{toast.title}</p>
        {toast.body && <p className="toast__body">{toast.body}</p>}
      </div>
      <button type="button" className="iconbtn toast__close" aria-label="Dismiss notification" onClick={onClose}>
        <X size={14} aria-hidden="true" />
      </button>
    </div>
  );
}
