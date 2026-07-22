/**
 * Live Protection — the citizen's real-time shield for a call in progress.
 *
 * Completely different from Analyze: no forms, no file types. The user presses
 * one button, and KAVACH listens and guides. Everything the analyst console
 * shows as instruments (manipulation map, digital twin, trust-passport table,
 * coercion sparkline) is deliberately hidden — a frightened person needs a
 * verdict, a timeline they can read, and one clear instruction, not a cockpit.
 *
 * Two ways to run it, one renderer:
 *   • "Start Live Protection" opens a real backend session and streams the
 *     device microphone through Web-Speech (hi-IN) into it. A browser can only
 *     hear the user's own mic — so this is for a call on speakerphone.
 *   • "Try a demo call" replays the recorded scenario, so a presentation never
 *     depends on live speech recognition.
 *
 * When the call ends, both paths transition **in place** into the exact same
 * InvestigationReport the Analyze journey produces — one investigation, two
 * entry points.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  Mic,
  MicOff,
  PhoneOff,
  Play,
  Radio,
  ShieldCheck,
  Wifi,
} from "lucide-react";
import * as api from "@/lib/api";
import type { VerifyResult } from "@/lib/api";
import type { PresageEvent, StateFrame } from "@/types/contract";
import { useStreamPlayer } from "@/hooks/useStreamPlayer";
import { useLiveSession } from "@/hooks/useLiveSession";
import { useVoice } from "@/hooks/useVoice";
import { InvestigationReport } from "@/components/report/InvestigationReport";
import { pretty } from "@/lib/stages";

type Phase = "idle" | "live" | "report";
type Source = "mic" | "demo" | null;

/** The four words a citizen reads, mapped from the contract's five bands. */
const RAMP = ["LOW", "MEDIUM", "HIGH", "CRITICAL"] as const;
function rampIndex(level?: string): number {
  switch (level) {
    case "CRITICAL":
      return 3;
    case "HIGH":
      return 2;
    case "ELEVATED":
      return 1;
    default:
      return 0; // CALM / WATCH
  }
}

function eventLine(e: PresageEvent): string | null {
  const p = e.payload as Record<string, unknown>;
  switch (e.kind) {
    case "STAGE_CHANGED":
      return `Caller moved to ${pretty(String(p.to ?? "")).toLowerCase()}`;
    case "THRESHOLD_CROSSED":
      return `Risk rose to ${RAMP[rampIndex(String(p.level))]}`;
    case "GUARDIAN_ALERTED":
      return "A trusted contact was alerted";
    case "PAYMENT_HELD":
      return "A payment was held before it could go through";
    case "COACH_URGENT":
      return "Urgent warning issued";
    default:
      return null;
  }
}

function mmss(t: number): string {
  const m = Math.floor(t / 60);
  const s = Math.floor(t % 60);
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

const PHONE_RE = /\b\d{10}\b/g;
const UPI_RE = /\b[\w.-]{2,}@[a-z]{2,}\b/gi;

export function LiveProtection() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [source, setSource] = useState<Source>(null);
  const [events, setEvents] = useState<PresageEvent[]>([]);
  const [report, setReport] = useState<VerifyResult | null>(null);
  const [reportBusy, setReportBusy] = useState(false);
  const [reportError, setReportError] = useState<string | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [intelMatches, setIntelMatches] = useState<
    { kind: string; value: string; case_count: number; clusters: string[] }[]
  >([]);

  const player = useStreamPlayer(false, 1);
  const live = useLiveSession();
  const voice = useVoice((text) => live.say(text, "CALLER"));

  const frame: StateFrame | null = source === "mic" ? live.frame : player.frame;
  const onEvent = source === "mic" ? live.onEvent : player.onEvent;

  const searched = useRef(new Set<string>());
  const endedRef = useRef(false);

  // Threat level → <html data-threat> so the ambient vignette reacts, same as
  // the analyst console.
  useEffect(() => {
    const level = frame?.threat?.level;
    if (level) document.documentElement.dataset.threat = level;
    return () => {
      delete document.documentElement.dataset.threat;
    };
  }, [frame?.threat?.level]);

  const endCall = useCallback(async () => {
    if (endedRef.current) return;
    endedRef.current = true;
    setReportBusy(true);
    setReportError(null);
    setPhase("report");
    if (source === "mic") {
      voice.stop();
      const sid = live.sessionId;
      await live.stop();
      const res = sid ? await api.investigateSession(sid) : null;
      if (res?.ok) setReport(res.data);
      else setReportError("This call was too short to analyse. Try Analyze to paste what was said.");
    } else {
      // Demo: assemble the transcript from the last frame and run it through
      // the very same verify() the Analyze page uses.
      const f = player.frame;
      const transcript = (f?.transcript.final ?? [])
        .map((u) => `${u.speaker}: ${u.text}`)
        .join("\n");
      player.pause();
      if (!transcript.trim()) {
        setReportError("The call ended before there was anything to analyse. Start a call and let it run a little.");
      } else {
        const res = await api.shieldVerify({ text: transcript, number: f?.call.caller_number ?? null });
        if (res.ok) setReport(res.data);
        else setReportError(res.error);
      }
    }
    setReportBusy(false);
  }, [source, live, player, voice]);

  // Persist events into the timeline, and auto-end when the call ends.
  useEffect(() => {
    if (phase !== "live") return;
    return onEvent((e: PresageEvent) => {
      if (e.kind === "CALL_ENDED") {
        void endCall();
        return;
      }
      if (eventLine(e)) setEvents((prev) => [...prev, e]);
    });
  }, [onEvent, phase, endCall]);

  // Live "has this happened before" — mine the running transcript for a caller
  // number / UPI and cross-reference Module 2, debounced by a searched-set so a
  // value is looked up once, not every frame.
  useEffect(() => {
    if (phase !== "live" || !frame) return;
    const text =
      (frame.call.caller_number ?? "") +
      " " +
      frame.transcript.final.map((u) => u.text).join(" ");
    const values = new Set<string>([
      ...(text.match(PHONE_RE) ?? []),
      ...(text.match(UPI_RE) ?? []),
    ]);
    values.forEach((v) => {
      if (searched.current.has(v)) return;
      searched.current.add(v);
      void api.searchIntel(v).then((res) => {
        if (!res.ok) return;
        const hits = res.data.matches.filter((m) => m.clusters.length > 0);
        if (hits.length) {
          setIntelMatches((prev) => {
            const seen = new Set(prev.map((p) => `${p.kind}:${p.value}`));
            const add = hits
              .filter((h) => !seen.has(`${h.kind}:${h.value}`))
              .map((h) => ({ kind: h.kind, value: h.value, case_count: h.case_count, clusters: h.clusters }));
            return [...prev, ...add];
          });
        }
      });
    });
  }, [frame, phase]);

  const resetAll = () => {
    setPhase("idle");
    setSource(null);
    setEvents([]);
    setReport(null);
    setReportError(null);
    setIntelMatches([]);
    setToken(null);
    endedRef.current = false;
    searched.current = new Set();
  };

  const startDemo = () => {
    resetAll();
    setSource("demo");
    setPhase("live");
    endedRef.current = false;
    player.restart();
  };

  const startMic = async () => {
    resetAll();
    setSource("mic");
    setPhase("live");
    endedRef.current = false;
    await live.start();
    voice.toggle();
  };

  const preserve = async () => {
    // Re-run through preserve using the assembled transcript so the citizen can
    // save the live call as evidence + generate a complaint, exactly like Analyze.
    const f = frame;
    const transcript = (f?.transcript.final ?? []).map((u) => `${u.speaker}: ${u.text}`).join("\n");
    setSaving(true);
    const res = await api.shieldPreserve({ text: transcript, number: f?.call.caller_number ?? null });
    setSaving(false);
    if (res.ok) {
      setToken(res.data.token);
      setReport(res.data.result);
    }
  };

  // -- render ---------------------------------------------------------------

  if (phase === "report") {
    return (
      <div className="page">
        <header className="page__head">
          <h1 className="page__title">Your investigation</h1>
        </header>
        {reportBusy ? (
          <div className="card shield-empty">
            <span className="spinner" style={{ width: 26, height: 26 }} />
            <p className="muted">Putting your call together…</p>
          </div>
        ) : reportError || !report ? (
          <div className="card shield-empty">
            <ShieldCheck size={28} />
            <p className="muted">{reportError ?? "Nothing to show for this call."}</p>
            <button className="btn2" onClick={resetAll}>
              Start another call
            </button>
          </div>
        ) : (
          <>
            <InvestigationReport
              result={report}
              onPreserve={preserve}
              saving={saving}
              token={token}
              note="Generated from your live call."
            />
            <button className="btn2" style={{ marginTop: "var(--s-5)" }} onClick={resetAll}>
              Start another call
            </button>
          </>
        )}
      </div>
    );
  }

  if (phase === "idle") {
    return (
      <div className="page">
        <header className="page__head">
          <h1 className="page__title">Live Protection</h1>
          <p className="page__lede">
            On a suspicious call right now? Put it on speaker and let KAVACH listen. It names the
            danger as it unfolds, warns you the moment it turns, and tells you exactly what to say.
          </p>
        </header>

        <div className="live-start">
          <button className="btn2 btn2--primary btn2--lg" onClick={startMic}>
            <Mic size={18} /> Start Live Protection
          </button>
          <button className="btn2 btn2--lg" onClick={startDemo}>
            <Play size={16} /> Try a demo call
          </button>
        </div>
        <p className="small faint" style={{ marginTop: "var(--s-4)" }}>
          KAVACH listens through your device microphone, so put the call on speakerphone. Nothing is
          uploaded — the audio is transcribed on your device. Works best in Chrome. Not sure? Try the
          demo call first.
        </p>
      </div>
    );
  }

  // phase === "live"
  const level = frame?.threat?.level;
  const ri = rampIndex(level);
  const critical = ri >= 3 || frame?.stage?.current?.startsWith("PAYMENT");
  const claimed = frame?.trust_passport?.claimed_identity;
  const trustPct = frame?.trust_passport?.final_trust_pct;
  const coachLine = frame?.coach?.line;
  const interim = voice.interimTranscript;
  const lastLines = (frame?.transcript.final ?? []).slice(-3);

  return (
    <div className="page live-protect">
      <header className="page__head">
        <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
          <h1 className="page__title" style={{ margin: 0 }}>
            <span className="live-dot" /> {source === "demo" ? "Demo call" : "Listening…"}
          </h1>
          <span className="chip" data-tone={source === "mic" ? "ok" : undefined}>
            {source === "mic" ? <Wifi size={13} /> : <Radio size={13} />}{" "}
            {source === "mic" ? (voice.isListening ? "mic on" : "mic paused") : "recorded"}
          </span>
        </div>
      </header>

      {critical && (
        <div className="panicbanner" style={{ marginBottom: "var(--s-4)" }}>
          <div className="panicbanner__head">
            <AlertTriangle size={18} /> Hang up now. This looks like a scam.
          </div>
          <p className="small" style={{ margin: "var(--s-2) 0 0" }}>
            Do not share any OTP or Aadhaar number, and do not transfer money. No real officer keeps
            you on a call to move money.
          </p>
        </div>
      )}

      {/* the three things a citizen watches */}
      <div className="live-grid">
        <div className="card live-stat">
          <p className="label">Threat</p>
          <div className="threat-ramp">
            {RAMP.map((word, i) => (
              <span key={word} className="threat-ramp__step" data-on={i <= ri || undefined} data-risk={word}>
                {word}
              </span>
            ))}
          </div>
        </div>
        <div className="card live-stat">
          <p className="label">Conversation stage</p>
          <strong className="live-stat__v">{frame?.stage ? pretty(frame.stage.current) : "Listening…"}</strong>
        </div>
        <div className="card live-stat">
          <p className="label">Identity</p>
          <strong className="live-stat__v">{claimed ?? "Unknown"}</strong>
          {claimed && trustPct != null && (
            <span className="small" data-tone={trustPct < 50 ? "bad" : undefined}>
              {trustPct < 50 ? "Unverified — likely fake" : "Checks out so far"}
            </span>
          )}
        </div>
      </div>

      {/* what to say now */}
      {coachLine && (
        <div className="card guidance-card" style={{ marginTop: "var(--s-4)" }}>
          <h2 className="card__title">
            <ShieldCheck size={16} /> What to do now
          </h2>
          <p className="coachline__quote" style={{ margin: "var(--s-2) 0 0" }}>
            {coachLine}
          </p>
          {frame?.coach?.why && <p className="small faint">{frame.coach.why}</p>}
        </div>
      )}

      <div className="live-grid live-grid--2" style={{ marginTop: "var(--s-4)" }}>
        {/* timeline */}
        <div className="card">
          <h2 className="card__title">What's happened so far</h2>
          {events.length === 0 ? (
            <p className="small muted" style={{ margin: 0 }}>
              Nothing alarming yet. KAVACH will note each turn of the call here.
            </p>
          ) : (
            <ul className="live-timeline">
              {events.map((e, i) => (
                <li key={`${e.seq}-${i}`}>
                  <span className="live-timeline__t mono">{mmss(e.t)}</span>
                  <span>{eventLine(e)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* has this happened before */}
        <div className="card">
          <h2 className="card__title">Has this happened before?</h2>
          {intelMatches.length === 0 ? (
            <p className="small muted" style={{ margin: 0 }}>
              Checking as the call goes… nothing matched to a known fraud network yet.
            </p>
          ) : (
            <div className="stack" style={{ gap: 6 }}>
              {intelMatches.map((m) => (
                <div key={`${m.kind}-${m.value}`} className="row" style={{ justifyContent: "space-between" }}>
                  <span className="small">
                    Known {m.kind}: <span className="mono">{m.value}</span>
                  </span>
                  <span className="chip" data-tone="bad">
                    {m.case_count} report{m.case_count === 1 ? "" : "s"}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* live transcript tail */}
      <div className="card" style={{ marginTop: "var(--s-4)" }}>
        <h2 className="card__title">Live transcript</h2>
        <div className="stack" style={{ gap: 6 }}>
          {lastLines.map((u) => (
            <p key={u.id} className="small" style={{ margin: 0 }}>
              <span className="mono faint" style={{ marginRight: 8 }}>
                {u.speaker}
              </span>
              {u.text}
            </p>
          ))}
          {interim && (
            <p className="small faint" style={{ margin: 0, fontStyle: "italic" }}>
              {interim}…
            </p>
          )}
          {lastLines.length === 0 && !interim && (
            <p className="small muted" style={{ margin: 0 }}>
              {source === "mic" ? "Say something, or wait for the caller…" : "Starting…"}
            </p>
          )}
        </div>
      </div>

      <div className="row" style={{ gap: "var(--s-2)", marginTop: "var(--s-5)" }}>
        <button className="btn2 btn2--danger" onClick={endCall}>
          <PhoneOff size={15} /> End &amp; get my report
        </button>
        {source === "mic" && (
          <button className="btn2" onClick={voice.toggle}>
            {voice.isListening ? <MicOff size={15} /> : <Mic size={15} />}
            {voice.isListening ? "Pause mic" : "Resume mic"}
          </button>
        )}
      </div>
      {voice.error && source === "mic" && (
        <p className="small faint" style={{ marginTop: "var(--s-3)" }}>
          Microphone: {voice.error}. You can still try the demo call, or use Analyze to paste what was said.
        </p>
      )}
    </div>
  );
}
