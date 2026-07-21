/**
 * Guardian — the screen where the score does something.
 *
 * A threat meter that only goes up is a dashboard. The guardian flow is what
 * makes it a product: a trusted contact is alerted when the call crosses into
 * HIGH, and a payment attempted during a coercive call is *held* rather than
 * executed.
 *
 * The hold is deliberately reversible and the override is deliberately
 * available. A circuit breaker that cannot be released by the account
 * holder's own trusted contact is one that people will route around
 * entirely — and a control people disable protects nobody. The asymmetry that
 * justifies the default is simple: a hold costs sixty seconds, a wrong
 * transfer costs the money.
 */

import { useState } from "react";
import {
  BellRing,
  Check,
  CircleDollarSign,
  Download,
  FileText,
  ShieldAlert,
  ShieldCheck,
  X,
} from "lucide-react";
import { useLiveSession } from "@/hooks/useLiveSession";
import { NarrationPanel } from "@/components/NarrationPanel";
import { pretty } from "@/lib/stages";
import { getReport, reportPdfUrl, reportUrl, type EvidencePackage } from "@/lib/api";

const ESCALATION = [
  { speaker: "CALLER" as const, text: "Main Delhi Cyber Crime se ACP Verma bol raha hoon." },
  { speaker: "CALLER" as const, text: "Aapke naam par money laundering ka case hai, arrest warrant 2 ghante mein issue hoga." },
  { speaker: "VICTIM" as const, text: "Sir please, mujhe bahut dar lag raha hai, main kya karu?" },
  { speaker: "CALLER" as const, text: "Ye matter confidential hai. Kisi ko mat bataiye, call disconnect mat kariye." },
  { speaker: "CALLER" as const, text: "Verification ke liye RBI supervised account mein paisa transfer karna hoga." },
];

export function Guardian() {
  const live = useLiveSession();
  const [step, setStep] = useState(0);
  const [amount, setAmount] = useState(450000);

  const frame = live.frame;
  const guardian = frame?.guardian;
  const payment = frame?.payment;
  const threat = frame?.threat;
  const started = !!live.sessionId;

  return (
    <div className="page">
      <header className="page__head">
        <p className="label">Monitor</p>
        <h1 className="page__title">Guardian</h1>
        <p className="page__lede">
          The intervention side. Escalate a call, watch the alert fire, then try
          to send money and see the circuit breaker hold it. Every button here
          hits the real API — nothing on this screen is mocked.
        </p>
      </header>

      {!started ? (
        <div className="card">
          <h2 className="card__title">Start a session</h2>
          <p className="muted small">
            Opens a live session against the analysis service, with Priya
            registered as the guardian contact.
          </p>
          <button
            className="btn2 btn2--primary"
            style={{ marginTop: "var(--s-4)" }}
            onClick={() => live.start("+91 98XXXX1234", "Priya (daughter)")}
          >
            <ShieldCheck size={15} /> Start guarded session
          </button>
          {live.error && (
            <div className="banner banner--bad" style={{ marginTop: "var(--s-4)" }}>
              <div className="small">{live.error}</div>
            </div>
          )}
        </div>
      ) : (
        <div className="grid2">
          <section className="stack">
            <div className="card">
              <h2 className="card__title">Escalate the call</h2>
              <p className="muted small" style={{ marginTop: 0 }}>
                Each line pushes the call one step further along the arc. Watch
                the threat score and the guardian state on the right.
              </p>
              <ol style={{ paddingLeft: "1.1rem", margin: "var(--s-4) 0 0" }}>
                {ESCALATION.map((line, i) => (
                  <li
                    key={line.text}
                    className="small"
                    style={{
                      marginBottom: 10,
                      color: i < step ? "var(--ink-faint)" : "var(--ink-muted)",
                      textDecoration: i < step ? "line-through" : "none",
                    }}
                  >
                    <span className="mono faint">{line.speaker}</span> — {line.text}
                  </li>
                ))}
              </ol>
              <div className="row" style={{ marginTop: "var(--s-4)" }}>
                <button
                  className="btn2"
                  disabled={step >= ESCALATION.length}
                  onClick={() => {
                    const line = ESCALATION[step];
                    live.say(line.text, line.speaker);
                    setStep((s) => s + 1);
                  }}
                >
                  Send next line ({step}/{ESCALATION.length})
                </button>
                <button
                  className="btn2 btn2--ghost"
                  onClick={async () => {
                    await live.stop();
                    setStep(0);
                    await live.start("+91 98XXXX1234", "Priya (daughter)");
                  }}
                >
                  Reset
                </button>
              </div>
            </div>

            <div className="card">
              <h2 className="card__title">Attempt a payment</h2>
              <p className="muted small" style={{ marginTop: 0 }}>
                Simulates the victim trying to send money right now. Above a
                threat of 55 the transfer is held instead of executed.
              </p>
              <div className="row" style={{ marginTop: "var(--s-4)" }}>
                <input
                  className="field"
                  style={{ maxWidth: 160 }}
                  type="number"
                  value={amount}
                  min={1}
                  onChange={(e) => setAmount(Number(e.target.value))}
                  aria-label="Amount in rupees"
                />
                <button
                  className="btn2 btn2--danger"
                  onClick={() => live.tryPayment(amount, "rbi.verify@okaxis")}
                >
                  <CircleDollarSign size={15} /> Send ₹{amount.toLocaleString("en-IN")}
                </button>
              </div>

              {payment?.state === "HELD" && (
                <div className="banner banner--bad" style={{ marginTop: "var(--s-4)", display: "block" }}>
                  <strong className="row" style={{ gap: 8 }}>
                    <ShieldAlert size={16} /> Payment held
                  </strong>
                  <p className="small" style={{ margin: "8px 0 0" }}>
                    {payment.held_reason}
                  </p>
                  <div className="row" style={{ marginTop: "var(--s-3)" }}>
                    <button className="btn2" onClick={() => live.cancelPayment()}>
                      <X size={14} /> Cancel the transfer
                    </button>
                    <button className="btn2 btn2--ghost" onClick={() => live.approvePayment()}>
                      <Check size={14} /> Release it anyway
                    </button>
                  </div>
                </div>
              )}

              {payment?.state === "CANCELLED" && (
                <div className="banner" style={{ marginTop: "var(--s-4)" }}>
                  <div className="small">
                    Transfer cancelled. In production this is the point where the
                    user is shown the 1930 helpline and the reporting flow.
                  </div>
                </div>
              )}

              {payment?.state === "APPROVED" && (
                <div className="banner" style={{ marginTop: "var(--s-4)" }}>
                  <div className="small">
                    Released by explicit guardian override. Recorded as such —
                    an override that is not logged is an override nobody can
                    review afterwards.
                  </div>
                </div>
              )}
            </div>
          </section>

          <section className="stack">
            <div className="card">
              <h2 className="card__title">Call state</h2>
              <dl className="kv">
                <dt>threat</dt>
                <dd>
                  {threat ? `${threat.score.toFixed(0)} / 100 — ${threat.level}` : "—"}
                </dd>
                <dt>stage</dt>
                <dd>{frame?.stage ? pretty(frame.stage.current) : "—"}</dd>
                <dt>guardian</dt>
                <dd>
                  <span
                    className="chip"
                    data-tone={
                      guardian?.state === "ALERTING"
                        ? "bad"
                        : guardian?.state === "ACKNOWLEDGED"
                          ? "ok"
                          : undefined
                    }
                  >
                    {guardian?.state ?? "—"}
                  </span>
                </dd>
                <dt>contact</dt>
                <dd>{guardian?.name ?? "—"}</dd>
                <dt>payment</dt>
                <dd>{payment?.state ?? "NONE"}</dd>
              </dl>

              {guardian?.state === "ALERTING" && (
                <div className="banner" style={{ marginTop: "var(--s-4)", display: "block" }}>
                  <strong className="row" style={{ gap: 8 }}>
                    <BellRing size={16} /> {guardian.name ?? "Your guardian"} has been
                    alerted
                  </strong>
                  <p className="small" style={{ margin: "8px 0 0" }}>
                    Fired at {guardian.alerted_at_s?.toFixed(0)}s, when the call
                    crossed into HIGH. In production this is a push notification
                    and a call-back.
                  </p>
                  <button
                    className="btn2"
                    style={{ marginTop: "var(--s-3)" }}
                    onClick={() => live.ackGuardian("Priya (daughter)")}
                  >
                    <Check size={14} /> Acknowledge as the guardian
                  </button>
                </div>
              )}
            </div>

            <div className="card">
              <NarrationPanel frame={frame} />
            </div>

            {live.sessionId && <EvidenceCard sessionId={live.sessionId} />}

            {frame?.coach && (
              <div className="card">
                <h2 className="card__title">What to say right now</h2>
                <p style={{ fontSize: "var(--t-md)", lineHeight: 1.5, margin: 0 }}>
                  “{frame.coach.line}”
                </p>
                <p className="small muted" style={{ marginTop: "var(--s-3)" }}>
                  <strong>{frame.coach.tactic}.</strong> {frame.coach.why}
                </p>
                {frame.coach.sources.length > 0 && (
                  <p className="mono faint" style={{ fontSize: "var(--t-2xs)", marginTop: 8 }}>
                    ↳ {frame.coach.sources.join(" · ")}
                  </p>
                )}
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  );
}

/**
 * Evidence package — the escalation artifact.
 *
 * "Preview" hits the JSON endpoint so a reader can see the report ID and the
 * count of named findings before downloading; the PDF button is a plain link
 * because the server sets Content-Disposition and the browser handles the save.
 * Both draw from the same server-built package, so the preview can never
 * disagree with the document that gets filed.
 */
function EvidenceCard({ sessionId }: { sessionId: string }) {
  const [pkg, setPkg] = useState<EvidencePackage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const preview = async () => {
    setLoading(true);
    setError(null);
    const res = await getReport(sessionId);
    setLoading(false);
    if (res.ok) setPkg(res.data);
    else setError(res.error);
  };

  return (
    <div className="card">
      <h2 className="card__title">Evidence package</h2>
      <p className="muted small" style={{ marginTop: 0 }}>
        A structured, citable package for escalation to the telecom provider or a
        cybercrime cell — the verdict, the named signals behind it, the identity
        and caller-number evidence, the transcript, and reporting guidance.
      </p>

      {pkg && (
        <dl className="kv" style={{ marginTop: "var(--s-3)" }}>
          <dt>report</dt>
          <dd className="mono">{pkg.report_id}</dd>
          <dt>incident</dt>
          <dd>{pkg.incident.type}</dd>
          <dt>peak threat</dt>
          <dd>
            {pkg.incident.peak_threat.toFixed(0)} / 100 — {pkg.incident.final_level}
          </dd>
          <dt>findings</dt>
          <dd>{pkg.evidence.length} cited</dd>
        </dl>
      )}

      {error && (
        <div className="banner banner--bad" style={{ marginTop: "var(--s-3)" }}>
          <div className="small">{error}</div>
        </div>
      )}

      <div className="row" style={{ marginTop: "var(--s-4)" }}>
        <button className="btn2" onClick={preview} disabled={loading}>
          <FileText size={14} /> {loading ? "Building…" : "Preview package"}
        </button>
        <a
          className="btn2 btn2--primary"
          href={reportPdfUrl(sessionId)}
          target="_blank"
          rel="noreferrer"
        >
          <Download size={14} /> Download PDF
        </a>
        <a
          className="btn2 btn2--ghost"
          href={reportUrl(sessionId)}
          target="_blank"
          rel="noreferrer"
        >
          View JSON
        </a>
      </div>
    </div>
  );
}
