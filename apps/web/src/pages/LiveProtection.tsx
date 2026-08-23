/**
 * Live Protection — the citizen's real-time shield for a call in progress.
 *
 * Same engine as the analyst Live Console, same instrument aesthetic (the
 * topbar, the threat gauge, the vignette, the panel grid) — but every technical
 * readout is re-voiced for a frightened person. "Authority impersonation node"
 * becomes "The caller claims to be from a government office." A trust passport
 * becomes an Identity Check. The manipulation map becomes "What we're noticing."
 * The wow of the cockpit stays; the cognitive load comes off.
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
import gsap from "gsap";
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
import type { Hotspot, VerifyResult } from "@/lib/api";
import type { ManipulationMap, AegisEvent, StateFrame } from "@/types/contract";
import { useStreamPlayer } from "@/hooks/useStreamPlayer";
import { useLiveSession } from "@/hooks/useLiveSession";
import { useVoice } from "@/hooks/useVoice";
import { ThreatMeter } from "@/components/ThreatMeter";
import { TranscriptPane } from "@/components/TranscriptPane";
import { ScamMap } from "@/components/map/ScamMap";
import { InvestigationReport } from "@/components/report/InvestigationReport";

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

/** One plain-language verdict for the big number, so a citizen never has to
 *  interpret "ELEVATED" vs "WATCH". */
function threatVerdict(level?: string): string {
  switch (level) {
    case "CRITICAL":
      return "Scam — hang up now";
    case "HIGH":
      return "Very likely a scam";
    case "ELEVATED":
      return "This looks suspicious";
    case "WATCH":
      return "Be careful";
    default:
      return "Nothing alarming yet";
  }
}

/** Conversation stage, said the way a person would describe it. */
const STAGE_PLAIN: Record<string, string> = {
  GREETING: "Just getting started",
  AUTHORITY_CLAIM: "Claiming to be an official",
  FEAR_INDUCTION: "Trying to scare you",
  ISOLATION: "Telling you to keep it secret",
  VERIFICATION_DEMAND: "Asking for codes or details",
  PAYMENT_SETUP: "Setting up a money transfer",
  PAYMENT_EXECUTION: "Pushing you to pay now",
  BENIGN: "Normal conversation",
};

/** What each tactic *is*, in one sentence. Drives "What we're noticing". */
const TACTIC_SENTENCE: Array<[keyof ManipulationMap, string]> = [
  ["authority", "The caller claims to be from a bank, the police, or a government office."],
  ["fear", "The caller is trying to frighten you into acting."],
  ["isolation", "The caller wants you to stay on the line and tell no one."],
  ["urgency", "The caller is rushing you to act immediately."],
  ["compliance", "The caller is walking you step-by-step into doing what they say."],
];

/** The next move, phrased as a prediction a person can act on. */
const NEXT_PLAIN: Record<string, string> = {
  GREETING: "make small talk to build trust",
  AUTHORITY_CLAIM: "claim to be an official",
  FEAR_INDUCTION: "try to frighten you",
  ISOLATION: "tell you to keep this secret",
  VERIFICATION_DEMAND: "ask for codes or personal details",
  PAYMENT_SETUP: "set up a money transfer",
  PAYMENT_EXECUTION: "push you to pay right now",
  BENIGN: "carry on normally",
};

/** Identity Check verdict from the trust percentage (which counts *down* from
 *  ~97 as claims fail). */
function identityVerdict(pct?: number | null): { text: string; bad: boolean } {
  if (pct == null) return { text: "Checking the caller's story…", bad: false };
  if (pct < 25) return { text: "This is almost certainly fake.", bad: true };
  if (pct < 50) return { text: "We can't verify this — treat it as fake.", bad: true };
  if (pct < 80) return { text: "Some of this doesn't add up.", bad: true };
  return { text: "Nothing disproven yet — stay careful.", bad: false };
}

function eventLine(e: AegisEvent): string | null {
  const p = e.payload as Record<string, unknown>;
  switch (e.kind) {
    case "STAGE_CHANGED":
      return `Caller moved to “${STAGE_PLAIN[String(p.to ?? "")] ?? "a new stage"}”`;
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
  const [events, setEvents] = useState<AegisEvent[]>([]);
  const [report, setReport] = useState<VerifyResult | null>(null);
  const [reportBusy, setReportBusy] = useState(false);
  const [reportError, setReportError] = useState<string | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [hotspots, setHotspots] = useState<Hotspot[]>([]);
  const [intelMatches, setIntelMatches] = useState<
    { kind: string; value: string; case_count: number; clusters: string[] }[]
  >([]);

  const [language, setLanguage] = useState<string>("hi-IN");
  const player = useStreamPlayer(false, 1);
  const live = useLiveSession();
  const voice = useVoice((text) => live.say(text, "CALLER"), language);

  const frame: StateFrame | null = source === "mic" ? live.frame : player.frame;
  const onEvent = source === "mic" ? live.onEvent : player.onEvent;

  const searched = useRef(new Set<string>());
  const endedRef = useRef(false);
  const cockpitRef = useRef<HTMLDivElement>(null);

  // GSAP animation for panel entrance
  useEffect(() => {
    if (phase === "live" && cockpitRef.current) {
      const panels = cockpitRef.current.querySelectorAll(".panel");
      gsap.fromTo(
        panels,
        { opacity: 0, y: 20 },
        { opacity: 1, y: 0, duration: 0.6, stagger: 0.05, ease: "power3.out" }
      );
    }
  }, [phase]);

  // Threat level → <html data-threat> so the ambient vignette and the gauge hue
  // react, exactly as they do on the analyst console. Only while a call is live
  // — the report and idle screens are ordinary chrome and must not stay tinted.
  useEffect(() => {
    const level = frame?.threat?.level;
    if (phase === "live" && level) document.documentElement.dataset.threat = level;
    else delete document.documentElement.dataset.threat;
    return () => {
      delete document.documentElement.dataset.threat;
    };
  }, [frame?.threat?.level, phase]);

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
    return onEvent((e: AegisEvent) => {
      if (e.kind === "CALL_ENDED") {
        void endCall();
        return;
      }
      if (eventLine(e)) setEvents((prev) => [...prev, e]);
    });
  }, [onEvent, phase, endCall]);

  // Nearby scam activity — pulled once when the call opens. District-level if we
  // have it, else cities; either way it's the real Module 2 geo feed.
  useEffect(() => {
    if (phase !== "live") return;
    let alive = true;
    void api.getGeo().then((res) => {
      if (!alive || !res.ok) return;
      const list = res.data.districts?.length ? res.data.districts : res.data.cities ?? [];
      setHotspots(list.slice(0, 14));
    });
    return () => {
      alive = false;
    };
  }, [phase]);

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
    setHotspots([]);
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
            On a suspicious call right now? Put it on speaker and let AegisAI listen. It names the
            danger as it unfolds, warns you the moment it turns, and tells you exactly what to say.
          </p>
        </header>

        <div className="live-lang">
          <label className="label" htmlFor="live-lang">
            Call language
          </label>
          <select
            id="live-lang"
            className="field"
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
          >
            <option value="hi-IN">Hindi / Hinglish</option>
            <option value="en-IN">English</option>
            <option value="en-US">English (US)</option>
          </select>
          <span className="small faint">
            Sets what AegisAI listens for. Hindi / Hinglish handles code-mixed calls.
          </span>
        </div>

        <div className="live-start">
          <button className="btn2 btn2--primary btn2--lg" onClick={startMic}>
            <Mic size={18} /> Start Live Protection
          </button>
          <button className="btn2 btn2--lg" onClick={startDemo}>
            <Play size={16} /> Try a demo call
          </button>
        </div>
        <p className="small faint" style={{ marginTop: "var(--s-4)" }}>
          AegisAI listens through your device microphone, so put the call on speakerphone. Nothing is
          uploaded — the audio is transcribed on your device. Works best in Chrome. Not sure? Try the
          demo call first.
        </p>
      </div>
    );
  }

  // phase === "live"
  const level = frame?.threat?.level;
  const ri = rampIndex(level);
  const stageCur = frame?.stage?.current;
  const paymentStage = stageCur === "PAYMENT_SETUP" || stageCur === "PAYMENT_EXECUTION";
  // Prominent "hang up" only when confidence is genuinely high — CRITICAL, or
  // HIGH while money is being set up.
  const hangUp = ri >= 3 || (ri >= 2 && paymentStage);
  const hot = level === "HIGH" || level === "CRITICAL";

  const claimed = frame?.trust_passport?.claimed_identity;
  const trustPct = frame?.trust_passport?.final_trust_pct;
  const idv = identityVerdict(trustPct);
  const idChecks = frame?.trust_passport?.checks ?? [];

  const mmap = frame?.manipulation_map;
  const noticing = mmap
    ? TACTIC_SENTENCE.map(([k, sentence]) => ({ k, sentence, v: mmap[k] })).filter((n) => n.v > 0.05)
        .sort((a, b) => b.v - a.v)
    : [];

  const forecast = frame?.forecast;
  const coach = frame?.coach;

  // Feed the mic's in-flight words into the transcript's partial slot so the
  // one transcript component shows both recorded and live speech.
  const transcript = frame?.transcript
    ? {
        ...frame.transcript,
        partial:
          frame.transcript.partial ?? (source === "mic" ? voice.interimTranscript || null : null),
      }
    : { final: [], partial: null, partial_speaker: null };

  return (
    <div className="page live-cockpit" ref={cockpitRef}>
      <div className="vignette" data-on={hot || undefined} />

      {/* topbar — the console's call header, re-voiced */}
      <header className="cockpit-top">
        <p className="cockpit-top__title">
          <span className="live-dot" /> {source === "demo" ? "Live Protection · demo call" : "Live Protection"}
        </p>
        <div className="cockpit-top__meta">
          <span className="chip" data-tone={source === "mic" ? "ok" : undefined}>
            {source === "mic" ? <Wifi size={13} /> : <Radio size={13} />}{" "}
            {source === "mic" ? (voice.isListening ? "listening" : "mic paused") : "recorded"}
          </span>
          {frame?.call.caller_number && <span className="mono">{frame.call.caller_number}</span>}
          <span className="mono">{mmss(frame?.t ?? 0)}</span>
        </div>
        <div className="cockpit-top__ctrls">
          {source === "mic" && (
            <button className="btn2 btn2--sm" onClick={voice.toggle}>
              {voice.isListening ? <MicOff size={14} /> : <Mic size={14} />}
              {voice.isListening ? "Pause" : "Resume"}
            </button>
          )}
          <button className="btn2 btn2--sm btn2--danger" onClick={endCall}>
            <PhoneOff size={14} /> End &amp; get report
          </button>
        </div>
      </header>

      {hangUp && (
        <div className="panicbanner cockpit-banner">
          <div className="panicbanner__head">
            <AlertTriangle size={18} /> Hang up now. This is a scam.
          </div>
          <p className="small" style={{ margin: "var(--s-2) 0 0" }}>
            Do not share any OTP or Aadhaar number, and do not transfer money. No real officer or bank
            keeps you on a call to move money “for safety”.
          </p>
        </div>
      )}

      <div className="cockpit-grid">
        {/* ---- main column: the conversation itself ---- */}
        <div className="cockpit-col">
          <section className="panel cockpit-transcript">
            <TranscriptPane transcript={transcript} />
          </section>

          <section className="panel pad">
            <p className="label">What&apos;s happened so far</p>
            {events.length === 0 ? (
              <p className="small muted" style={{ margin: "var(--s-2) 0 0" }}>
                Nothing alarming yet. AegisAI will note each turn of the call here.
              </p>
            ) : (
              <ul className="live-timeline" style={{ marginTop: "var(--s-3)" }}>
                {events.map((e, i) => (
                  <li key={`${e.seq}-${i}`}>
                    <span className="live-timeline__t mono">{mmss(e.t)}</span>
                    <span>{eventLine(e)}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>

        {/* ---- middle column: how dangerous, where we are, what's next ---- */}
        <div className="cockpit-col">
          <section className="panel pad">
            <p className="label">Current threat level</p>
            <ThreatMeter threat={frame?.threat ?? null} />
            <p className="threat-verdict">{threatVerdict(level)}</p>
          </section>

          <section className="panel pad">
            <p className="label">Conversation stage</p>
            <strong className="live-stat__v" style={{ display: "block", marginTop: 6 }}>
              {stageCur ? STAGE_PLAIN[stageCur] ?? "Listening…" : "Listening…"}
            </strong>
          </section>

          <section className="panel pad whatnext">
            <p className="label">What may happen next</p>
            {forecast ? (
              <p className="whatnext__line">
                {forecast.eta_to_payment_s != null ? (
                  <>
                    If this continues, the caller will likely ask you to move money in about{" "}
                    <span className="whatnext__eta">~{Math.round(forecast.eta_to_payment_s)}s</span>.
                  </>
                ) : (
                  <>Next, expect the caller to {NEXT_PLAIN[forecast.next_stage] ?? "escalate"}.</>
                )}
              </p>
            ) : (
              <p className="small muted" style={{ margin: "var(--s-2) 0 0" }}>
                No escalation predicted yet.
              </p>
            )}
          </section>
        </div>

        {/* ---- right column: what to do, who they claim to be, the tactics ---- */}
        <div className="cockpit-col">
          <section className="panel pad guidance-card">
            <p className="label">
              <ShieldCheck size={13} style={{ verticalAlign: "-2px", marginRight: 6 }} />
              What to do right now
            </p>
            {coach ? (
              <>
                <p className="coachline__quote" style={{ margin: "var(--s-2) 0 0" }}>
                  {coach.line}
                </p>
                {coach.why && <p className="small faint" style={{ margin: "6px 0 0" }}>{coach.why}</p>}
              </>
            ) : (
              <p className="small muted" style={{ margin: "var(--s-2) 0 0" }}>
                Stay on the line and don&apos;t share anything yet. AegisAI will tell you what to say.
              </p>
            )}
          </section>

          <section className="panel pad">
            <p className="label">Identity check</p>
            {claimed ? (
              <p className="passport__claim" style={{ marginTop: "var(--s-2)" }}>
                Claims to be <strong>{claimed}</strong>
              </p>
            ) : (
              <p className="small muted" style={{ margin: "var(--s-2) 0 0" }}>
                The caller hasn&apos;t claimed an identity yet.
              </p>
            )}
            <p className="idcheck__verdict" data-bad={idv.bad || undefined}>
              {idv.text}
            </p>
            {idChecks.length > 0 && (
              <ul className="passport__checks" style={{ marginTop: "var(--s-3)" }}>
                {idChecks.map((c) => (
                  <li className="passport__check" key={c.name} data-verdict={c.verdict}>
                    <span className="passport__mark" aria-hidden="true">
                      {c.verdict === "FAIL" ? "✕" : c.verdict === "PASS" ? "✓" : "?"}
                    </span>
                    <span className="passport__name">{c.name}</span>
                    <span className="passport__detail">{c.detail}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="panel pad">
            <p className="label">What we&apos;re noticing</p>
            {noticing.length === 0 ? (
              <p className="small muted" style={{ margin: "var(--s-2) 0 0" }}>
                No scam tactics spotted yet.
              </p>
            ) : (
              <ul className="notice-list" style={{ marginTop: "var(--s-3)" }}>
                {noticing.map((n) => (
                  <li className="notice-row" key={n.k}>
                    <span className="notice-row__text">{n.sentence}</span>
                    <span className="notice-track" aria-hidden="true">
                      <i style={{ transform: `scaleX(${Math.min(1, n.v)})` }} />
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      </div>

      {/* ---- wide row: the two "is this real / am I alone" questions ---- */}
      <div className="cockpit-grid cockpit-grid--wide">
        <section className="panel pad">
          <p className="label">Has this happened before?</p>
          {intelMatches.length === 0 ? (
            <p className="small muted" style={{ margin: "var(--s-2) 0 0" }}>
              Checking as the call goes… nothing matched to a known fraud network yet.
            </p>
          ) : (
            <div className="stack" style={{ gap: 6, marginTop: "var(--s-3)" }}>
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
        </section>

        <section className="panel pad">
          <p className="label">Nearby scam activity</p>
          {hotspots.length === 0 ? (
            <p className="small muted" style={{ margin: "var(--s-2) 0 0" }}>
              Loading the latest reports near you…
            </p>
          ) : (
            <>
              <p className="small faint" style={{ margin: "var(--s-2) 0 var(--s-2)" }}>
                Areas reporting the most scam calls right now.
              </p>
              <ScamMap hotspots={hotspots} height={260} />
            </>
          )}
        </section>
      </div>

      {voice.error && source === "mic" && (
        <p className="small faint" style={{ marginTop: "var(--s-3)" }}>
          Microphone: {voice.error}. You can still try the demo call, or use Analyze to paste what was said.
        </p>
      )}
    </div>
  );
}
