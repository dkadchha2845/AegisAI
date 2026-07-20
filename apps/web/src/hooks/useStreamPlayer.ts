/**
 * Drives the console from a recorded contract stream.
 *
 * Deliberately shaped like the real WebSocket client will be: it consumes
 * `ServerMessage`s and exposes (a) the latest `StateFrame` and (b) a subscribe
 * hook for discrete `Event`s. Swapping the mock for a live socket later means
 * replacing the transport inside this file and nothing else.
 *
 * State vs events, again
 * ----------------------
 * Frames are applied wholesale — `setFrame(msg)`, never merged. Events go to
 * subscribers through a ref-held listener set, so a component can fire an
 * animation without the whole tree re-rendering on every tick.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import type { PresageEvent, StateFrame } from "@/types/contract";
import { isEvent, isState } from "@/types/contract";
import raw from "@/mock/stream.json";

/** Only timed messages are replayable — ErrorMessage carries no `t`, so it
 *  is deliberately excluded from the recorded stream. */
type TimedMessage = StateFrame | PresageEvent;

const MESSAGES = raw as unknown as TimedMessage[];

export type EventListener = (e: PresageEvent) => void;

export interface StreamPlayer {
  frame: StateFrame | null;
  playing: boolean;
  /** 1 = real time. The recorded call is ~104s. */
  speed: number;
  setSpeed: (s: number) => void;
  play: () => void;
  pause: () => void;
  restart: () => void;
  seek: (t: number) => void;
  duration: number;
  onEvent: (fn: EventListener) => () => void;
}

export function useStreamPlayer(autoplay = true, initialSpeed = 1): StreamPlayer {
  const [frame, setFrame] = useState<StateFrame | null>(null);
  const [playing, setPlaying] = useState(autoplay);
  const [speed, setSpeed] = useState(initialSpeed);

  const cursor = useRef(0); // index of the next message to deliver
  const clock = useRef(0); // virtual call time, seconds
  const rafId = useRef<number | undefined>(undefined);
  const lastTs = useRef<number | undefined>(undefined);
  const listeners = useRef(new Set<EventListener>());

  const duration = MESSAGES.length ? MESSAGES[MESSAGES.length - 1].t : 0;

  const onEvent = useCallback((fn: EventListener) => {
    listeners.current.add(fn);
    return () => {
      listeners.current.delete(fn);
    };
  }, []);

  /** Deliver every message whose timestamp has passed. */
  const drain = useCallback(() => {
    let latestFrame: StateFrame | null = null;
    while (
      cursor.current < MESSAGES.length &&
      MESSAGES[cursor.current].t <= clock.current
    ) {
      const msg = MESSAGES[cursor.current++];
      if (isState(msg)) {
        // Coalesce: if several frames elapsed in one tick only the last
        // matters, because frames are snapshots rather than deltas.
        latestFrame = msg;
      } else if (isEvent(msg)) {
        listeners.current.forEach((fn) => fn(msg));
      }
    }
    if (latestFrame) setFrame(latestFrame);
  }, []);

  const seek = useCallback((t: number) => {
    clock.current = t;
    cursor.current = 0;
    // Replay state up to t WITHOUT firing events — scrubbing backwards must
    // not re-trigger the guardian alert or slam the payment stamp again.
    let latest: StateFrame | null = null;
    while (cursor.current < MESSAGES.length && MESSAGES[cursor.current].t <= t) {
      const msg = MESSAGES[cursor.current++];
      if (isState(msg)) latest = msg;
    }
    setFrame(latest);
  }, []);

  const restart = useCallback(() => {
    clock.current = 0;
    cursor.current = 0;
    setFrame(null);
    setPlaying(true);
  }, []);

  useEffect(() => {
    if (!playing) {
      lastTs.current = undefined;
      return;
    }
    const tick = (ts: number) => {
      if (lastTs.current !== undefined) {
        clock.current += ((ts - lastTs.current) / 1000) * speed;
      }
      lastTs.current = ts;
      drain();
      if (cursor.current >= MESSAGES.length) {
        setPlaying(false);
        return;
      }
      rafId.current = requestAnimationFrame(tick);
    };
    rafId.current = requestAnimationFrame(tick);
    return () => {
      if (rafId.current) cancelAnimationFrame(rafId.current);
      lastTs.current = undefined;
    };
  }, [playing, speed, drain]);

  return {
    frame,
    playing,
    speed,
    setSpeed,
    play: () => setPlaying(true),
    pause: () => setPlaying(false),
    restart,
    seek,
    duration,
    onEvent,
  };
}
