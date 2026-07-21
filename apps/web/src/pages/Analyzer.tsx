/**
 * Analyzer — paste or upload anything suspicious and get a scored verdict.
 *
 * This is the screen that makes the product usable by someone who is not
 * watching a live call: an SMS forward, a screenshot's text, a transcript, a
 * UPI ID a caller just read out. All four go to the same engine that scores
 * live calls, because two implementations of "what counts as a scam" would be
 * two products, and the one the user did not see would be the wrong one.
 *
 * The result is deliberately shaped as an audit rather than a badge. A
 * verdict the user cannot interrogate is one they are right to ignore, so
 * every score shows its drivers, its mechanical findings, the per-line stage
 * labels, and the sources behind each claim.
 */

import { useCallback, useRef, useState } from "react";
import {
  AlertTriangle,
  FileUp,
  Image as ImageIcon,
  Loader2,
  Paperclip,
  ScanLine,
  Sparkles,
} from "lucide-react";
import * as api from "@/lib/api";
import type { AnalysisResult } from "@/lib/api";
import { pretty, stageColor } from "@/lib/stages";
import { useHealth } from "@/hooks/useHealth";

type Mode = "text" | "upi" | "file" | "image";

/** Communication channels the analyzer accepts. Sets the `kind` on the request
 *  so a report can say where a message arrived — the module's multi-channel
 *  input (SMS, WhatsApp, Telegram, Email, chat logs). */
const CHANNELS: [string, string][] = [
  ["text", "Transcript / other"],
  ["sms", "SMS"],
  ["whatsapp", "WhatsApp"],
  ["telegram", "Telegram"],
  ["email", "Email"],
];

const SAMPLES: { label: string; mode: Mode; value: string }[] = [
  {
    label: "Digital-arrest call",
    mode: "text",
    value: `Caller: Main CBI Mumbai crime branch se Inspector Sharma bol raha hoon.
Victim: Ji sir, boliye.
Caller: Aapke Aadhaar par ek parcel mila hai jisme drugs hain. Money laundering ka case register ho chuka hai.
Victim: Kya? Mujhe kuch nahi pata sir, mujhe dar lag raha hai.
Caller: Ye matter confidential hai, kisi ko batana mana hai. Call disconnect mat kariye warna arrest warrant issue ho jayega.
Caller: Verification ke liye RBI supervised account mein 4,50,000 transfer karna hoga. Ye refundable hai.`,
  },
  {
    label: "Refund QR scam",
    mode: "text",
    value:
      "Sir aapka refund approved ho gaya hai. Ye QR code scan kijiye aur apna UPI PIN daaliye, paisa turant aa jayega.",
  },
  {
    label: "Genuine bank reminder",
    mode: "text",
    value:
      "Sir aapki credit card payment due hai, ye sirf reminder call hai. Hum kabhi OTP nahi maangte. Aap branch mein aakar bhi kar sakte hain, koi jaldi nahi hai.",
  },
  {
    label: "Impersonating UPI ID",
    mode: "upi",
    value: "upi://pay?pa=rbi.verify@okaxis&pn=Ramesh Traders&am=450000",
  },
];

export function Analyzer() {
  const [mode, setMode] = useState<Mode>("text");
  const [channel, setChannel] = useState("text");
  const [text, setText] = useState("");
  const [claimed, setClaimed] = useState("");
  const [useLlm, setUseLlm] = useState(false);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const health = useHealth();

  const run = useCallback(
    async (override?: { mode?: Mode; value?: string }) => {
      const activeMode = override?.mode ?? mode;
      const value = override?.value ?? text;
      if (!value.trim()) return;
      setBusy(true);
      setError(null);
      const res =
        activeMode === "upi"
          ? await api.analyzeUpi(value, claimed || null)
          : await api.analyzeText(value, {
              // In text mode the channel (sms/whatsapp/…) is the kind, so a
              // verdict carries where the message arrived.
              kind: activeMode === "text" ? channel : activeMode,
              claimedIdentity: claimed || null,
              explain: useLlm,
            });
      setBusy(false);
      if (res.ok) setResult(res.data);
      else {
        setError(res.error);
        setResult(null);
      }
    },
    [mode, channel, text, claimed, useLlm],
  );

  const runUpload = useCallback(
    async (file: File, asImage: boolean) => {
      setBusy(true);
      setError(null);
      const res = asImage
        ? await api.analyzeImage(file, { claimedIdentity: claimed || null })
        : await api.analyzeFile(file);
      setBusy(false);
      if (res.ok) setResult(res.data);
      else {
        setError(res.error);
        setResult(null);
      }
    },
    [claimed],
  );

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) runUpload(file, mode === "image");
  };

  return (
    <div className="page">
      <header className="page__head">
        <p className="label">Investigate</p>
        <h1 className="page__title">Analyzer</h1>
        <p className="page__lede">
          Paste a message, a call transcript, or a UPI ID — or drop a transcript
          file. You get a score, the signals behind it, per-line stage labels,
          and the sources every claim rests on.
        </p>
      </header>

      <div className="analyzer">
        <section className="stack">
          <div className="card">
            <div className="tabs" role="tablist">
              {(
                [
                  ["text", "Message or transcript"],
                  ["upi", "UPI ID or QR"],
                  ["file", "Upload a file"],
                  ["image", "Screenshot"],
                ] as [Mode, string][]
              ).map(([m, label]) => (
                <button
                  key={m}
                  role="tab"
                  className="tab"
                  data-active={mode === m || undefined}
                  aria-selected={mode === m}
                  onClick={() => setMode(m)}
                >
                  {label}
                </button>
              ))}
            </div>

            <div style={{ marginTop: "var(--s-4)" }}>
              {mode === "file" || mode === "image" ? (
                <>
                  <div
                    className="dropzone"
                    data-over={dragging || undefined}
                    onClick={() => fileInput.current?.click()}
                    onDragOver={(e) => {
                      e.preventDefault();
                      setDragging(true);
                    }}
                    onDragLeave={() => setDragging(false)}
                    onDrop={onDrop}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => e.key === "Enter" && fileInput.current?.click()}
                  >
                    {mode === "image" ? <ImageIcon size={24} /> : <FileUp size={24} />}
                    <strong style={{ fontSize: "var(--t-sm)" }}>
                      {mode === "image"
                        ? "Drop a screenshot, or click to choose"
                        : "Drop a transcript, or click to choose"}
                    </strong>
                    <span className="small faint">
                      {mode === "image"
                        ? ".png · .jpg · .webp · .tiff — up to 4MB"
                        : ".txt · .json · .csv · .md · .vtt · .srt — up to 4MB"}
                    </span>
                  </div>
                  <input
                    ref={fileInput}
                    type="file"
                    hidden
                    accept={
                      mode === "image"
                        ? ".png,.jpg,.jpeg,.webp,.bmp,.tiff,.gif"
                        : ".txt,.json,.csv,.md,.log,.vtt,.srt"
                    }
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file) runUpload(file, mode === "image");
                    }}
                  />
                  {mode === "image" && (
                    <p className="small faint" style={{ marginTop: "var(--s-3)" }}>
                      OCR reads a fake police notice, a payment screenshot, or a QR
                      code, then scores the text. If the server has no OCR engine
                      installed it says so and asks you to type the text — it never
                      guesses at an empty read.
                    </p>
                  )}
                </>
              ) : (
                <textarea
                  className="field"
                  rows={mode === "upi" ? 3 : 10}
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  placeholder={
                    mode === "upi"
                      ? "someone@okaxis  —  or a full upi://pay?pa=…&pn=…&am=… payload"
                      : "Paste the message, or the conversation.\n\nCaller: …\nVictim: …"
                  }
                />
              )}
            </div>

            {mode !== "file" && mode !== "image" && (
              <>
                <div className="row" style={{ marginTop: "var(--s-4)" }}>
                  <label className="small faint" style={{ flex: "1 1 220px" }}>
                    Who do they claim to be? (optional — enables the strongest
                    UPI check)
                    <input
                      className="field"
                      style={{ marginTop: 6 }}
                      value={claimed}
                      onChange={(e) => setClaimed(e.target.value)}
                      placeholder="e.g. RBI, SBI, Delhi Cyber Crime"
                    />
                  </label>
                  {mode === "text" && (
                    <label className="small faint" style={{ flex: "0 1 160px" }}>
                      Channel
                      <select
                        className="field"
                        style={{ marginTop: 6 }}
                        value={channel}
                        onChange={(e) => setChannel(e.target.value)}
                      >
                        {CHANNELS.map(([v, label]) => (
                          <option key={v} value={v}>
                            {label}
                          </option>
                        ))}
                      </select>
                    </label>
                  )}
                </div>

                <div className="row" style={{ marginTop: "var(--s-4)" }}>
                  <button
                    className="btn2 btn2--primary"
                    onClick={() => run()}
                    disabled={busy || !text.trim()}
                  >
                    {busy ? <Loader2 size={15} className="spin" /> : <ScanLine size={15} />}
                    {busy ? "Analysing…" : "Analyse"}
                  </button>
                  <label
                    className="small faint row"
                    style={{ gap: 6, cursor: health.data?.llm.configured ? "pointer" : "not-allowed" }}
                    title={
                      health.data?.llm.configured
                        ? "Ask the configured LLM to phrase the explanation. The score is unchanged — the model only rewords a finished result."
                        : "No LLM backend is configured. Set PRESAGE_LLM and restart the API."
                    }
                  >
                    <input
                      type="checkbox"
                      checked={useLlm}
                      disabled={!health.data?.llm.configured}
                      onChange={(e) => setUseLlm(e.target.checked)}
                    />
                    <Sparkles size={13} /> Explain in plain language
                  </label>
                </div>
              </>
            )}
          </div>

          <div className="card">
            <h2 className="card__title">Try one of these</h2>
            <div className="row">
              {SAMPLES.map((sample) => (
                <button
                  key={sample.label}
                  className="btn2 btn2--ghost"
                  onClick={() => {
                    setMode(sample.mode);
                    setText(sample.value);
                    setClaimed(sample.mode === "upi" ? "RBI" : "");
                    run({ mode: sample.mode, value: sample.value });
                  }}
                >
                  <Paperclip size={14} /> {sample.label}
                </button>
              ))}
            </div>
            <p className="small faint" style={{ marginTop: "var(--s-3)" }}>
              The genuine bank reminder is here on purpose. A detector that only
              ever gets shown scams tells you nothing about its false-alarm rate.
            </p>
          </div>
        </section>

        <section className="stack">
          {error && (
            <div className="banner banner--bad">
              <AlertTriangle size={18} />
              <div>{error}</div>
            </div>
          )}

          {!result && !error && (
            <div className="card">
              <p className="muted small" style={{ margin: 0 }}>
                Results appear here. Nothing is uploaded anywhere but your own
                local analysis service — there is no third-party call in this
                path unless you tick the plain-language explanation.
              </p>
            </div>
          )}

          {result && <ResultPanel result={result} />}
        </section>
      </div>
    </div>
  );
}

const VERDICT_LABEL: Record<string, string> = {
  LIKELY_SCAM: "Likely a scam",
  SUSPICIOUS: "Suspicious",
  LIKELY_LEGITIMATE: "Nothing detected",
  INSUFFICIENT: "Not enough to judge",
};

function ResultPanel({ result }: { result: AnalysisResult }) {
  return (
    <>
      <div className="verdict" data-v={result.verdict}>
        <div className="verdict__head">
          <span className="verdict__label">
            {VERDICT_LABEL[result.verdict] ?? result.verdict}
          </span>
          <span className="verdict__score mono">{result.score.toFixed(0)}</span>
        </div>
        <p className="verdict__summary">{result.explanation ?? result.summary}</p>
        {result.explanation_source === "template" && result.explanation !== result.summary && (
          <p className="small faint" style={{ marginTop: 8 }}>
            Templated explanation — the LLM was unavailable.
          </p>
        )}
        {result.filename && (
          <p className="small faint" style={{ marginTop: 8 }}>
            from <span className="mono">{result.filename}</span>
          </p>
        )}
      </div>

      {result.ocr && (
        <div className="card">
          <h2 className="card__title">
            Read from the image{" "}
            <span className="mono faint small">OCR · {result.ocr.engine}</span>
          </h2>
          {result.ocr.text ? (
            <pre
              className="small"
              style={{ whiteSpace: "pre-wrap", margin: 0, fontFamily: "inherit" }}
            >
              {result.ocr.text}
            </pre>
          ) : (
            <p className="small muted" style={{ margin: 0 }}>
              No text could be read from this image.
            </p>
          )}
          {result.ocr.qr_payloads.length > 0 && (
            <p className="small faint mono" style={{ marginTop: 8 }}>
              QR: {result.ocr.qr_payloads.join(" · ")}
            </p>
          )}
        </div>
      )}

      {result.recommended_actions.length > 0 && (
        <div className="card">
          <h2 className="card__title">What to do</h2>
          <ul className="actions">
            {result.recommended_actions.map((action) => (
              <li key={action}>
                <span>{action}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {result.findings.length > 0 && (
        <div className="card">
          <h2 className="card__title">Checks that fired</h2>
          <ul className="findings">
            {result.findings.map((finding, i) => (
              <li className="finding" data-v={finding.verdict} key={`${finding.label}-${i}`}>
                <div className="finding__label">{finding.label}</div>
                <p className="finding__detail">{finding.detail}</p>
                {finding.source && <div className="finding__src">↳ {finding.source}</div>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {result.drivers.length > 0 && (
        <div className="card">
          <h2 className="card__title">What drove the score</h2>
          <ul className="findings">
            {result.drivers.map((driver) => (
              <li className="finding" data-v="UNKNOWN" key={driver.label}>
                <div className="finding__label">
                  {driver.label}{" "}
                  <span className="mono faint small">
                    +{(driver.contribution * 100).toFixed(0)}
                  </span>
                </div>
                <p className="finding__detail">{driver.detail}</p>
              </li>
            ))}
          </ul>
        </div>
      )}

      {result.upi?.valid_format && (
        <div className="card">
          <h2 className="card__title">UPI identifier</h2>
          <dl className="kv">
            <dt>VPA</dt>
            <dd>{result.upi.vpa}</dd>
            <dt>handle</dt>
            <dd>@{result.upi.handle}</dd>
            {result.upi.payee_name && (
              <>
                <dt>registered to</dt>
                <dd>{result.upi.payee_name}</dd>
              </>
            )}
            {result.upi.amount != null && (
              <>
                <dt>amount</dt>
                <dd>₹{result.upi.amount.toLocaleString("en-IN")}</dd>
              </>
            )}
          </dl>
        </div>
      )}

      {result.lines.length > 1 && (
        <div className="card">
          <h2 className="card__title">Line by line</h2>
          <div className="lines">
            {result.lines.map((line) => (
              <div className="linerow" key={line.index}>
                <span className="linerow__who">{line.speaker}</span>
                <span className="linerow__text">{line.text}</span>
                <span
                  className="linerow__stage"
                  style={{ ["--stage-color" as string]: stageColor(line.stage) }}
                  title={
                    line.confidence
                      ? `${(line.confidence * 100).toFixed(0)}% confident`
                      : undefined
                  }
                >
                  {line.stage === "—" ? "—" : pretty(line.stage)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {result.trust_passport && result.trust_passport.checks.length > 0 && (
        <div className="card">
          <h2 className="card__title">
            Trust passport{" "}
            <span className="mono faint small">
              {result.trust_passport.final_trust_pct.toFixed(0)}%
            </span>
          </h2>
          {result.trust_passport.claimed_identity && (
            <p className="small muted" style={{ marginTop: 0 }}>
              Claims to be {result.trust_passport.claimed_identity}.
            </p>
          )}
          <ul className="findings">
            {result.trust_passport.checks.map((check) => (
              <li className="finding" data-v={check.verdict} key={check.name}>
                <div className="finding__label">
                  {check.name}{" "}
                  <span className="mono faint small">{check.verdict}</span>
                </div>
                <p className="finding__detail">{check.detail}</p>
                {check.source && <div className="finding__src">↳ {check.source}</div>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {result.citations.length > 0 && (
        <div className="card">
          <h2 className="card__title">Sources</h2>
          <ul className="small muted" style={{ paddingLeft: "1.1rem", margin: 0 }}>
            {result.citations.map((c) => (
              <li key={c} className="mono" style={{ marginBottom: 4, fontSize: "var(--t-2xs)" }}>
                {c}
              </li>
            ))}
          </ul>
        </div>
      )}

      {result.degraded.length > 0 && (
        <div className="banner">
          <AlertTriangle size={16} />
          <div className="small">
            Produced in a degraded mode:{" "}
            <span className="mono">{result.degraded.join(", ")}</span>. See the
            dashboard for what each of these means.
          </div>
        </div>
      )}
    </>
  );
}
