/**
 * Error boundary around the routed content.
 *
 * Without one, a render error anywhere inside a page unmounts the whole React
 * tree and leaves a white screen — no navigation, no way back, nothing to do
 * but reload. That is a bad outcome in general and an unrecoverable one in
 * front of an audience.
 *
 * Scoped to the outlet rather than the whole app on purpose: the shell (top
 * bar, sidebar, ⌘K) stays mounted and usable, so a broken screen costs you
 * that screen instead of the session. The error text is shown rather than
 * swallowed, because "something went wrong" tells the person who can fix it
 * nothing at all.
 */

import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  /** Changing this resets the boundary — pass the current pathname so
   *  navigating away from a broken screen clears the error. */
  resetKey?: string;
}

interface State {
  error: Error | null;
}

export class RouteBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidUpdate(prev: Props) {
    if (prev.resetKey !== this.props.resetKey && this.state.error) {
      this.setState({ error: null });
    }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Keep the component stack in the console — it is the only place the
    // failing component is named, and the UI below deliberately does not
    // dump it at the user.
    console.error("Route failed to render:", error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;

    return (
      <div className="page">
        <div className="banner banner--bad" style={{ display: "block" }}>
          <strong>This screen failed to render.</strong>
          <p className="small" style={{ margin: "8px 0 0" }}>
            The rest of the app still works — pick another screen from the
            sidebar, or press <kbd>⌘K</kbd>.
          </p>
          <pre
            className="mono small"
            style={{
              marginTop: "var(--s-4)",
              whiteSpace: "pre-wrap",
              overflowX: "auto",
              color: "var(--ink-muted)",
            }}
          >
            {this.state.error.message}
          </pre>
        </div>
      </div>
    );
  }
}
