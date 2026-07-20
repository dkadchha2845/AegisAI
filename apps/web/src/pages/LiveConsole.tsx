/**
 * Live console.
 *
 * The screen is a pure render of one `StateFrame`. There is no threat logic
 * here — no thresholds, no stage rules, no score maths. Discrete `Event`s
 * drive the animations that need an edge (the meter shake, the forecast
 * confirmation), because deriving edges by diffing frames breaks the moment a
 * frame drops or repeats.
 *
 * Two sources, one renderer
 * -------------------------
 * `recorded` replays the fixture at a controllable speed and is what the demo
 * runs on. `live` opens a real session against the API and lets you type into
 * the call. Both expose `{ frame, onEvent }`, so everything below this
 * component is identical either way — which is what makes the fallback real
 * rather than aspirational. If the backend dies mid-demo, switching to
 * recorded costs one click and nothing else changes.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { Radio, Send, SkipForward, Wifi, WifiOff } from "lucide-react";
import { gsap, prefersReducedMotion } from "@/lib/gsap";
import { useReveal } from "@/hooks/useReveal";
import { useStreamPlayer } from "@/hooks/useStreamPlayer";
import { useLiveSession } from "@/hooks/useLiveSession";
import { ThreatDrivers, ThreatMeter } from "@/components/ThreatMeter";
import { ForecastChip } from "@/components/ForecastChip";
import {
  CoachCard,
  CoercionSparkline,
  ManipulationMap,
  TrustPassport,
} from "@/components/Panels";
import { TranscriptPane } from "@/components/TranscriptPane";
import { NarrationPanel } from "@/components/NarrationPanel";
import type { PresageEvent, StateFrame } from "@/types/contract";

/** Demo beats, for the rehearsal scrubber. Timings come from mock-stream.json. */
const BEATS = [
  { t: 0, label: "Open" },
  { t: 18, label: "Fear" },
  { t: 31.5, label: "Forecast" },
  { t: 36, label: "Isolation" },
  { t: 54, label: "Credentials" },
  { t: 90, label: "Payment" },
];

/** Scripted lines for the live mode, so a demo does not depend on typing
 *  Hinglish accurately in front of an audience. */
const SCRIPT: { speaker: "CALLER" | "VICTIM"; text: string }[] = [
  { speaker: "CALLER", text: "Hello, kya main Rajesh Kumar ji se baat kar raha hoon?" },
  { speaker: "VICTIM", text: "Haan ji, boliye." },
  { speaker: "CALLER", text: "Main CBI Mumbai crime branch se Inspector Sharma bol raha hoon, badge number 4471." },
  { speaker: "CALLER", text: "Aapke Aadhaar par ek parcel mila hai jisme drugs hain. Money laundering ka case register ho chuka hai." },
  { speaker: "VICTIM", text: "Kya? Sir mujhe kuch nahi pata, mujhe dar lag raha hai." },
  { speaker: "CALLER", text: "Ye matter confidential hai, kisi ko batana mana hai. Call disconnect mat kariye." },
  { speaker: "CALLER", text: "Verification ke liye aapka Aadhaar number aur OTP bataiye jo abhi aaya hai." },
  { speaker: "CALLER", text: "RBI supervised account mein 4,50,000 transfer karna hoga, ye refundable security deposit hai." },
  { speaker: "CALLER", text: "UPI app kholiye, amount daaliye aur PIN confirm kar dijiye. Main line par hoon." },
];

type Source = "recorded" | "live";

export function LiveConsole() {
  const [source, setSource] = useState<Source>("recorded");
  const player = useStreamPlayer(true, 1);
  const live = useLiveSession();

  const frame: StateFrame | null = source === "live" ? live.frame : player.frame;
  const onEvent = source === "live" ? live.onEvent : player.onEvent;

  const rootRef = useRef<HTMLDivElement>(null);
  const shellRef = useRef<HTMLDivElement>(null);
  const [hitSeq, setHitSeq] = useState(0);
  const [scriptIndex, setScriptIndex] = useState(0);
  const [draft, setDraft] = useState("");
  const t = frame?.t ?? 0;

  useReveal(rootRef, [source]);

  // Threat level lives on <html> so CSS anywhere can react to it without
  // prop-drilling — the vignette, the meter hue, the 3D field on Home.
  useEffect(() => {
    const level = frame?.threat?.level;
    if (level) document.documentElement.dataset.threat = level;
  }, [frame?.threat?.level]);

  // Clear the global threat level on unmount, or the marketing pages stay
  // tinted CRITICAL after you navigate away from a finished call.
  useEffect(() => {
    return () => {
      delete document.documentElement.dataset.threat;
    };
  }, []);

  // Edge-driven animation. Subscribed once; never re-renders on events.
  useEffect(() => {
    return onEvent((e: PresageEvent) => {
      switch (e.kind) {
        case "THRESHOLD_CROSSED": {
          const level = e.payload.level as string;
          if ((level === "HIGH" || level === "CRITICAL") && !prefersReducedMotion) {
            const el = shellRef.current;
            if (el) {
              gsap.fromTo(el, { x: -5 }, { x: 0, duration: 0.5, ease: "elastic.out(1.6, 0.35)" });
            }
          }
          break;
        }
        case "FORECAST_HIT":
          setHitSeq((n) => n + 1);
          break;
        default:
          break;
      }
    });
  }, [onEvent]);

  const level = frame?.threat?.level ?? "CALM";

  const connectionChip = useMemo(() => {
    if (source === "recorded") {
      return { icon: <Radio size={13} />, text: "recorded stream", tone: undefined };
    }
    if (live.connection === "live") {
      return { icon: <Wifi size={13} />, text: `live · ${live.sessionId?.slice(0, 8)}`, tone: "ok" };
    }
    if (live.connection === "connecting") {
      return { icon: <Wifi size={13} />, text: "connecting…", tone: "warn" };
    }
    return { icon: <WifiOff size={13} />, text: live.connection, tone: "bad" };
  }, [source, live.connection, live.sessionId]);

  const sendNext = () => {
    const line = SCRIPT[scriptIndex];
    if (!line) return;
    live.say(line.text, line.speaker);
    setScriptIndex((i) => Math.min(i + 1, SCRIPT.length));
  };

  return (
    <div className="shell" ref={shellRef}>
      <div
        className="vignette"
        data-on={level === "HIGH" || level === "CRITICAL" || undefined}
      />

      <header className="topbar">
        <div className="brand">
          <span className="brand__mark" aria-hidden="true" />
          <span className="brand__name">LIVE CALL</span>
          <span className={`chip`} data-tone={connectionChip.tone}>
            {connectionChip.icon} {connectionChip.text}
          </span>
        </div>

        <div className="callmeta">
          <span
            className="callmeta__dot"
            data-live={frame?.call.status === "active" || undefined}
          />
          <span className="mono">{frame?.call.caller_number ?? "—"}</span>
          <span className="mono callmeta__time">
            {String(Math.floor(t / 60)).padStart(2, "0")}:
            {String(Math.floor(t % 60)).padStart(2, "0")}
          </span>
        </div>

        <div className="controls">
          <button
            className="btn"
            data-active={source === "recorded" || undefined}
            onClick={() => setSource("recorded")}
          >
            Recorded
          </button>
          <button
            className="btn"
            data-active={source === "live" || undefined}
            onClick={async () => {
              setSource("live");
              if (!live.sessionId) {
                await live.start("+91 98XXXX1234", "Priya (daughter)");
              }
            }}
          >
            Live
          </button>

          {source === "recorded" ? (
            <>
              <button className="btn" onClick={player.playing ? player.pause : player.play}>
                {player.playing ? "Pause" : "Play"}
              </button>
              <button className="btn" onClick={player.restart}>
                Restart
              </button>
              {[1, 2, 4].map((s) => (
                <button
                  key={s}
                  className="btn btn--ghost"
                  data-active={player.speed === s || undefined}
                  onClick={() => player.setSpeed(s)}
                >
                  {s}×
                </button>
              ))}
            </>
          ) : (
            <>
              <button
                className="btn"
                onClick={sendNext}
                disabled={live.connection !== "live" || scriptIndex >= SCRIPT.length}
                title={SCRIPT[scriptIndex]?.text ?? "Script finished"}
              >
                <SkipForward size={13} /> Next line ({scriptIndex}/{SCRIPT.length})
              </button>
              <button
                className="btn btn--ghost"
                onClick={async () => {
                  await live.stop();
                  setScriptIndex(0);
                  await live.start("+91 98XXXX1234", "Priya (daughter)");
                }}
              >
                Restart
              </button>
            </>
          )}
        </div>
      </header>

      {source === "recorded" ? (
        /* Rehearsal scrubber. Jumping to a beat without waiting out the call
           is the difference between rehearsing six times and twice. `seek`
           replays state without re-firing events, so scrubbing back does not
           re-trigger the guardian alert. */
        <div className="scrub">
          <input
            className="scrub__range"
            type="range"
            min={0}
            max={player.duration}
            step={0.5}
            value={t}
            aria-label="Scrub call timeline"
            onChange={(e) => {
              player.pause();
              player.seek(Number(e.target.value));
            }}
          />
          <div className="scrub__marks">
            {BEATS.map((b, i) => (
              <button
                key={b.t}
                className="scrub__mark"
                style={{ left: `${(b.t / player.duration) * 100}%`, top: i % 2 ? 13 : 0 }}
                onClick={() => {
                  player.pause();
                  player.seek(b.t);
                }}
                title={`${b.label} · ${b.t}s`}
              >
                <span>{b.label}</span>
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className="injectbar">
          <input
            className="field"
            value={draft}
            placeholder="Type what the caller says, then press Enter…"
            disabled={live.connection !== "live"}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && draft.trim()) {
                live.say(draft, "CALLER");
                setDraft("");
              }
            }}
          />
          <button
            className="btn"
            disabled={live.connection !== "live" || !draft.trim()}
            onClick={() => {
              live.say(draft, "CALLER");
              setDraft("");
            }}
          >
            <Send size={13} /> as caller
          </button>
          <button
            className="btn btn--ghost"
            disabled={live.connection !== "live" || !draft.trim()}
            onClick={() => {
              live.say(draft, "VICTIM");
              setDraft("");
            }}
          >
            as victim
          </button>
        </div>
      )}

      {source === "live" && live.error && (
        <div className="banner banner--bad" style={{ margin: "0 var(--s-4) var(--s-3)" }}>
          <div className="small">
            {live.error} — switch to <strong>Recorded</strong> to keep going.
          </div>
        </div>
      )}

      <main className="grid" ref={rootRef}>
        <section className="col col--left panel" data-reveal>
          <TranscriptPane
            transcript={frame?.transcript ?? { final: [], partial: null, partial_speaker: null }}
          />
        </section>

        <section className="col col--mid">
          <div className="panel pad" data-reveal>
            <ThreatMeter threat={frame?.threat ?? null} />
            <ThreatDrivers threat={frame?.threat ?? null} />
          </div>
          <div className="panel pad" data-reveal>
            <ForecastChip forecast={frame?.forecast ?? null} hitSeq={hitSeq} />
          </div>
          <div className="panel pad" data-reveal>
            <NarrationPanel frame={frame} />
          </div>
          <div className="panel pad" data-reveal>
            <CoercionSparkline coercion={frame?.coercion ?? null} />
          </div>
        </section>

        <section className="col col--right">
          <div className="panel pad" data-reveal>
            <ManipulationMap
              map={
                frame?.manipulation_map ?? {
                  authority: 0,
                  fear: 0,
                  isolation: 0,
                  urgency: 0,
                  compliance: 0,
                }
              }
            />
          </div>
          <div className="panel pad" data-reveal>
            <TrustPassport passport={frame?.trust_passport ?? null} />
          </div>
          <CoachCard coach={frame?.coach ?? null} />
        </section>
      </main>
    </div>
  );
}
