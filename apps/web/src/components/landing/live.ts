/**
 * The landing's live reads of the running system.
 *
 * Two sections quote figures from `/api/health` — the agent registry, the
 * classifier that is actually serving, the size of the retrieval corpus and of
 * the intelligence store. They read them from here rather than each fetching,
 * so the page asks once however many sections want the answer.
 *
 * `/api/health` is public, so this works for an anonymous visitor in
 * production as well as in development. When it fails — the API is asleep or
 * unreachable — every caller gets `null` and shows its static copy with no
 * figure, rather than a stale or invented one.
 */

import { useEffect, useState } from "react";
import * as api from "@/lib/api";

let pending: Promise<api.Health | null> | null = null;

function loadHealth(): Promise<api.Health | null> {
  if (!pending) {
    pending = api.getHealth().then((r) => (r.ok ? r.data : null));
  }
  return pending;
}

/** The running system's health report, or `null` until (and unless) it
 *  arrives. */
export function useLiveHealth(): api.Health | null {
  const [health, setHealth] = useState<api.Health | null>(null);
  useEffect(() => {
    let alive = true;
    void loadHealth().then((h) => {
      if (alive) setHealth(h);
    });
    return () => {
      alive = false;
    };
  }, []);
  return health;
}
