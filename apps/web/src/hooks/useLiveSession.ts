/**
 * Live session over the WebSocket, with the same shape as `useStreamPlayer`.
 *
 * Deliberately interface-compatible with the recorded-stream player: both
 * expose `{ frame, onEvent }`, so a component can render either without
 * knowing which it has. That is what makes the fallback real — if the backend
 * is unreachable mid-demo, the console switches to the recorded stream and
 * nothing below it changes.
 *
 * Frames are applied wholesale, never merged. Events go to subscribers through
 * a ref-held set, so an animation can fire without re-rendering the tree on
 * every tick.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { AegisEvent, StateFrame } from "@/types/contract";
import { isEvent, isState } from "@/types/contract";
import * as api from "@/lib/api";

export type ConnectionState = "idle" | "connecting" | "live" | "error" | "closed";

export interface LiveSession {
  frame: StateFrame | null;
  sessionId: string | null;
  connection: ConnectionState;
  error: string | null;
  start: (callerNumber?: string, guardianName?: string) => Promise<void>;
  stop: () => Promise<void>;
  say: (text: string, speaker?: "CALLER" | "VICTIM") => Promise<void>;
  ackGuardian: (name?: string) => Promise<void>;
  tryPayment: (amount: number, payee?: string) => Promise<void>;
  cancelPayment: () => Promise<void>;
  approvePayment: () => Promise<void>;
  onEvent: (fn: (e: AegisEvent) => void) => () => void;
}

export function useLiveSession(): LiveSession {
  const [frame, setFrame] = useState<StateFrame | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [connection, setConnection] = useState<ConnectionState>("idle");
  const [error, setError] = useState<string | null>(null);

  const socket = useRef<WebSocket | null>(null);
  const listeners = useRef(new Set<(e: AegisEvent) => void>());
  // Guards against a socket opened by an unmounted component writing state.
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      socket.current?.close();
      socket.current = null;
    };
  }, []);

  const onEvent = useCallback((fn: (e: AegisEvent) => void) => {
    listeners.current.add(fn);
    return () => {
      listeners.current.delete(fn);
    };
  }, []);

  const connect = useCallback((id: string) => {
    const ws = new WebSocket(api.socketUrl(id));
    socket.current = ws;
    ws.onopen = () => alive.current && setConnection("live");
    ws.onerror = () => {
      if (!alive.current) return;
      setConnection("error");
      setError("Lost the connection to the analysis service.");
    };
    ws.onclose = () => alive.current && setConnection((c) => (c === "error" ? c : "closed"));
    ws.onmessage = (msg) => {
      if (!alive.current) return;
      const data = JSON.parse(msg.data);
      if (isState(data)) setFrame(data);
      else if (isEvent(data)) listeners.current.forEach((fn) => fn(data));
      else if (data.type === "error") setError(data.message);
    };
  }, []);

  const start = useCallback(
    async (callerNumber?: string, guardianName?: string) => {
      setConnection("connecting");
      setError(null);
      const res = await api.startSession(callerNumber, guardianName);
      if (!res.ok) {
        setConnection("error");
        setError(res.error);
        return;
      }
      setFrame(res.data);
      setSessionId(res.data.session_id);
      connect(res.data.session_id);
    },
    [connect],
  );

  /** Every action returns the resulting frame, so the UI updates immediately
   *  rather than waiting up to 250ms for the next socket tick. The frame that
   *  arrives on the socket afterwards is identical — snapshots are
   *  idempotent, which is exactly what makes this safe. */
  const apply = useCallback((res: api.ApiResult<api.SessionActionResult>) => {
    if (!res.ok) {
      setError(res.error);
      return;
    }
    setFrame(res.data.frame);
    res.data.events.forEach((e) =>
      listeners.current.forEach((fn) => fn(e as unknown as AegisEvent)),
    );
  }, []);

  const say = useCallback(
    async (text: string, speaker: "CALLER" | "VICTIM" = "CALLER") => {
      if (!sessionId) return;
      apply(await api.injectUtterance(sessionId, text, speaker));
    },
    [sessionId, apply],
  );

  const ackGuardian = useCallback(
    async (name?: string) => {
      if (!sessionId) return;
      apply(await api.guardianAck(sessionId, name));
    },
    [sessionId, apply],
  );

  const tryPayment = useCallback(
    async (amount: number, payee?: string) => {
      if (!sessionId) return;
      apply(await api.attemptPayment(sessionId, amount, payee));
    },
    [sessionId, apply],
  );

  const doCancel = useCallback(async () => {
    if (!sessionId) return;
    apply(await api.cancelPayment(sessionId));
  }, [sessionId, apply]);

  const doApprove = useCallback(async () => {
    if (!sessionId) return;
    apply(await api.approvePayment(sessionId));
  }, [sessionId, apply]);

  const stop = useCallback(async () => {
    if (!sessionId) return;
    apply(await api.endSession(sessionId));
    socket.current?.close();
    socket.current = null;
    setConnection("closed");
  }, [sessionId, apply]);

  return {
    frame,
    sessionId,
    connection,
    error,
    start,
    stop,
    say,
    ackGuardian,
    tryPayment,
    cancelPayment: doCancel,
    approvePayment: doApprove,
    onEvent,
  };
}
