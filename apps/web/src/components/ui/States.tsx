/**
 * Empty, loading and error states — the three things a screen shows when it
 * has no content to show, built once.
 *
 * Before this the product had: four visually different "nothing here yet"
 * sentences, a spinner used for every wait regardless of what was being
 * waited on, and raw backend strings rendered straight into the page. All
 * three are the same failure — the screen stops explaining itself at exactly
 * the moment the user needs it to.
 *
 * The rules each one encodes:
 *
 * - **Empty** always says what *would* be here and, where one exists, offers
 *   the action that puts it there. "No saved cases yet." on its own is a
 *   dead end.
 * - **Loading** prefers a skeleton in the shape of the answer. A skeleton
 *   says "a table is coming"; a spinner says "something is happening". Use
 *   `<Spinner>` only for waits with no knowable shape.
 * - **Error** never prints the exception. It says what failed in the user's
 *   terms, offers the retry, and puts the technical detail behind a
 *   disclosure for the person who can act on it.
 */

import type { ReactNode } from "react";
import { AlertTriangle, Inbox, RotateCw } from "lucide-react";

/* -------------------------------------------------------------- empty ---- */

interface EmptyProps {
  /** Statement of fact: "No saved reports yet." */
  title: string;
  /** What would fill this, in one sentence. */
  body?: ReactNode;
  /** The action that fills it, if there is one. */
  action?: ReactNode;
  icon?: ReactNode;
  /** Sits inside an existing card rather than owning a region. */
  inline?: boolean;
}

export function EmptyState({ title, body, action, icon, inline }: EmptyProps) {
  return (
    <div className={`empty${inline ? " empty--inline" : ""}`}>
      <span className="empty__mark" aria-hidden="true">
        {icon ?? <Inbox size={20} />}
      </span>
      <p className="empty__title">{title}</p>
      {body && <p className="empty__body">{body}</p>}
      {action && <div className="empty__action">{action}</div>}
    </div>
  );
}

/* ------------------------------------------------------------ loading ---- */

/**
 * A skeleton in the shape of what is coming. `lines` for prose, `rows` for a
 * table or list. Announced politely once, not per shimmering bar.
 */
export function Skeleton({
  lines = 3,
  block = false,
  label = "Loading",
}: {
  lines?: number;
  block?: boolean;
  label?: string;
}) {
  return (
    <div role="status" aria-live="polite" aria-busy="true">
      <span className="vh">{label}…</span>
      {block ? (
        <span className="skeleton skeleton--block" />
      ) : (
        Array.from({ length: lines }, (_, i) => (
          <span
            key={i}
            className="skeleton skeleton--text"
            /* Ragged right edge, like real text. A stack of identical bars
               reads as a loading *graphic* rather than as absent content. */
            style={{ width: `${[100, 92, 74, 86, 62][i % 5]}%` }}
          />
        ))
      )}
    </div>
  );
}

/** Rows of a table that has not arrived yet. */
export function SkeletonRows({ rows = 4, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div role="status" aria-live="polite" aria-busy="true" className="skelrows">
      <span className="vh">Loading…</span>
      {Array.from({ length: rows }, (_, r) => (
        <div className="skelrows__row" key={r} style={{ gridTemplateColumns: `repeat(${cols}, 1fr)` }}>
          {Array.from({ length: cols }, (_, c) => (
            <span key={c} className="skeleton skeleton--text" style={{ width: c === 0 ? "60%" : "80%" }} />
          ))}
        </div>
      ))}
    </div>
  );
}

/** For waits with no knowable shape. Prefer a skeleton where there is one. */
export function Spinner({ label }: { label?: string }) {
  return (
    <span className="spinner-wrap" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      {label && <span className="spinner-wrap__label">{label}</span>}
    </span>
  );
}

/* -------------------------------------------------------------- error ---- */

interface ErrorProps {
  /** What failed, in the user's terms — not the exception. */
  title?: string;
  body?: ReactNode;
  onRetry?: () => void;
  retryLabel?: string;
  /**
   * The raw message. Kept out of the sentence and behind a disclosure: it
   * means nothing to the person it interrupted and everything to the one
   * who has to fix it.
   */
  detail?: string | null;
  inline?: boolean;
}

export function ErrorState({
  title = "Something went wrong",
  body = "We couldn't finish that. It is usually temporary — try again, and if it keeps happening the system status in the sidebar will say what is degraded.",
  onRetry,
  retryLabel = "Try again",
  detail,
  inline,
}: ErrorProps) {
  return (
    <div className={`empty${inline ? " empty--inline" : ""}`} role="alert">
      <span className="empty__mark empty__mark--bad" aria-hidden="true">
        <AlertTriangle size={20} />
      </span>
      <p className="empty__title">{title}</p>
      <p className="empty__body">{body}</p>
      {onRetry && (
        <div className="empty__action">
          <button className="btn2" onClick={onRetry}>
            <RotateCw size={14} aria-hidden="true" /> {retryLabel}
          </button>
        </div>
      )}
      {detail && (
        <details className="empty__detail">
          <summary>Technical detail</summary>
          <p className="mono">{detail}</p>
        </details>
      )}
    </div>
  );
}
