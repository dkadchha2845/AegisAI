/**
 * Polls /api/health.
 *
 * Every screen wants to know whether the backend is up and which components
 * degraded, and none of them should each own a fetch loop. Polls slowly (15s):
 * this changes when a process restarts, not per second, and a chatty health
 * check competes with the frame socket for no benefit.
 */

import { useEffect, useState } from "react";
import { getHealth, type Health } from "@/lib/api";

const POLL_MS = 15_000;

export function useHealth() {
  const [data, setData] = useState<Health | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;

    const tick = async () => {
      const res = await getHealth();
      if (!alive) return;
      if (res.ok) {
        setData(res.data);
        setError(null);
      } else {
        setData(null);
        setError(res.error);
      }
      setLoading(false);
    };

    tick();
    const id = window.setInterval(tick, POLL_MS);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, []);

  return { data, loading, error };
}
