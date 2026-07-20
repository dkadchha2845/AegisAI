import { useEffect, useRef } from "react";
import { gsap, prefersReducedMotion } from "@/lib/gsap";
import type { Stage, Transcript } from "@/types/contract";

/**
 * Live transcript.
 *
 * Two decisions worth noting:
 *
 * 1. Only *new* utterances animate in. Re-animating the whole list on every
 *    frame would thrash and, worse, make already-read lines twitch while the
 *    user is reading them.
 *
 * 2. The stage tag sits on the caller's lines only. Tagging the victim's
 *    replies too is technically correct — the contract labels them — but on
 *    screen it reads as though the victim is running the scam.
 */

const SHORT: Record<Stage, string> = {
  GREETING: "GREET",
  AUTHORITY_CLAIM: "AUTHORITY",
  FEAR_INDUCTION: "FEAR",
  ISOLATION: "ISOLATION",
  VERIFICATION_DEMAND: "CREDENTIALS",
  PAYMENT_SETUP: "PAY SETUP",
  PAYMENT_EXECUTION: "PAY EXEC",
  BENIGN: "BENIGN",
};

const ALARMING: Stage[] = [
  "FEAR_INDUCTION",
  "ISOLATION",
  "VERIFICATION_DEMAND",
  "PAYMENT_SETUP",
  "PAYMENT_EXECUTION",
];

export function TranscriptPane({ transcript }: { transcript: Transcript }) {
  const listRef = useRef<HTMLOListElement>(null);
  const rendered = useRef(0);

  useEffect(() => {
    const list = listRef.current;
    if (!list) return;
    const n = transcript.final.length;

    if (n > rendered.current && !prefersReducedMotion) {
      const fresh = Array.from(list.children).slice(rendered.current) as HTMLElement[];
      gsap.fromTo(
        fresh,
        { opacity: 0, y: 10 },
        { opacity: 1, y: 0, duration: 0.4, ease: "power3.out", stagger: 0.05 },
      );
    }
    rendered.current = n;

    // Keep the newest line in view. `smooth` on every append fights itself
    // when lines land quickly, so jump when far behind and glide when close.
    const dist = list.scrollHeight - list.scrollTop - list.clientHeight;
    list.scrollTo({ top: list.scrollHeight, behavior: dist > 400 ? "auto" : "smooth" });
  }, [transcript.final.length]);

  return (
    <div className="transcript">
      <div className="transcript__head">
        <span className="label">Live transcript</span>
        <span className="transcript__count mono">{transcript.final.length}</span>
      </div>

      <ol className="transcript__list" ref={listRef}>
        {transcript.final.map((u) => (
          <li
            key={u.id}
            className="turn"
            data-speaker={u.speaker}
            data-alarming={ALARMING.includes(u.stage) || undefined}
          >
            <div className="turn__meta">
              <span className="turn__who">{u.speaker === "CALLER" ? "Caller" : "Victim"}</span>
              <span className="turn__time mono">{u.t0.toFixed(0)}s</span>
              {u.speaker === "CALLER" && (
                <span className="turn__stage">{SHORT[u.stage]}</span>
              )}
            </div>
            <p className="turn__text">{u.text}</p>
          </li>
        ))}
      </ol>

      {transcript.partial && (
        <p className="transcript__partial">{transcript.partial}</p>
      )}
    </div>
  );
}
