/**
 * Shield — the CFSRP citizen fraud shield (AegisAI Module 3), and the primary
 * "check something suspicious" entry point (Home's hero CTA points here).
 *
 * One continuous investigation, not three separate module pages. Every input
 * mode (paste, upload, screenshot, verify-only) feeds the same fused verdict
 * — Module 1 (is this coercive?), Module 2 (is this known fraud
 * infrastructure?), Module 3 (guidance + response) — from one call to
 * `api.shieldVerify`. The UI narrates that single response as seven short,
 * question-framed sections instead of a report dump.
 *
 * The "investigating…" loader is a real, honest pacing of the one network
 * call underneath: it never claims a step finished before the response
 * actually contains that data, and it holds on the last step (with a
 * spinner, not a fake checkmark) if the request is slow. Screenshot input
 * runs OCR up front, before the loader even starts, so the extracted text
 * can be reviewed — the loader always represents exactly the `shieldVerify`
 * call, regardless of how the text got there.
 */

import { useEffect, useRef, useState } from "react";
import {
  ChevronLeft,
  FileText,
  FileUp,
  Globe,
  Image as ImageIcon,
  IndianRupee,
  Info,
  Mail,
  MapPin,
  MessageSquare,
  Mic,
  Phone,
  Search,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import * as api from "@/lib/api";
import type { Hotspot, VerifyResult } from "@/lib/api";
import { CITY_OPTIONS } from "@/lib/stages";
import { InvestigatingLoader, INVESTIGATION_STEPS } from "@/components/report/InvestigatingLoader";
import { InvestigationReport } from "@/components/report/InvestigationReport";

type Entry = "picker" | "upload-picker" | "verify-picker" | "form";
type Mode = "text" | "file" | "image" | "audio";
type VerifyType = "phone" | "upi" | "email" | "website" | null;

const STEP_MS = 350;
const BURST_MS = 80;

export function Shield() {
  const [entry, setEntry] = useState<Entry>("picker");
  const [mode, setMode] = useState<Mode>("text");
  const [verifyType, setVerifyType] = useState<VerifyType>(null);
  const [text, setText] = useState("");
  const [number, setNumber] = useState("");
  const [upi, setUpi] = useState("");
  const [email, setEmail] = useState("");
  const [website, setWebsite] = useState("");
  const [city, setCity] = useState("");
  const [askCity, setAskCity] = useState(false);
  const [ocrBusy, setOcrBusy] = useState(false);
  const [ocrNote, setOcrNote] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const focusField = useRef<HTMLInputElement>(null);

  const [investigating, setInvestigating] = useState(false);
  const [stepIndex, setStepIndex] = useState(0);
  const [result, setResult] = useState<VerifyResult | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [awareness, setAwareness] = useState<
    { trending_scams: { cluster_id: string; scam: string; size: number; risk: string; states: string[] }[]; hotspot_states: Hotspot[] } | null
  >(null);

  useEffect(() => {
    void (async () => {
      const res = await api.getAwareness();
      if (res.ok) setAwareness(res.data);
    })();
  }, []);

  const startMessage = () => {
    setMode("text");
    setVerifyType(null);
    setEntry("form");
  };

  const startUpload = (m: Mode) => {
    setMode(m);
    setVerifyType(null);
    setEntry("form");
  };

  const startVerify = (t: Exclude<VerifyType, null>) => {
    setMode("text");
    setVerifyType(t);
    setEntry("form");
    setTimeout(() => focusField.current?.focus(), 0);
  };

  const backToPicker = () => {
    setEntry("picker");
    setResult(null);
    setToken(null);
    setText("");
    setNumber("");
    setUpi("");
    setEmail("");
    setWebsite("");
    setOcrNote(null);
    setVerifyType(null);
    setAskCity(false);
  };

  const runFileRead = async (file: File) => {
    setOcrBusy(true);
    setOcrNote(null);
    try {
      const content = await file.text();
      setText(content);
      setOcrNote(`Loaded from ${file.name}`);
      setMode("text");
    } catch {
      setOcrNote("Could not read this file — try again or paste the text manually.");
    } finally {
      setOcrBusy(false);
    }
  };

  const runImageOcr = async (file: File) => {
    setOcrBusy(true);
    setOcrNote(null);
    const res = await api.analyzeImage(file, { callerNumber: number || null });
    setOcrBusy(false);
    if (res.ok) {
      const ocr = res.data.ocr;
      const extracted = ocr?.text ?? "";
      setText(extracted);
      const bits: string[] = [];
      if (ocr) bits.push(`Read via OCR (${ocr.engine})`);
      if (ocr?.qr_payloads.length) bits.push("QR code detected");
      setOcrNote(bits.length ? bits.join(" · ") : "No text could be read from this image — you can type it below.");
      const qrUpi = ocr?.qr_payloads.find((p) => p.startsWith("upi://"));
      const m = qrUpi?.match(/[?&]pa=([^&]+)/);
      if (m) setUpi(decodeURIComponent(m[1]));
      // Only switch to text editing mode if OCR actually extracted content
      if (extracted.trim()) setMode("text");
    } else {
      setOcrNote(res.error ?? "Could not read this image — try again or use a different screenshot.");
    }
  };

  const runAudio = async (file: File) => {
    setOcrBusy(true);
    setOcrNote(null);
    const res = await api.analyzeAudio(file, { callerNumber: number || null });
    setOcrBusy(false);
    if (res.ok) {
      const asr = res.data.asr;
      if (asr?.text) {
        setText(asr.text);
        setOcrNote(`Transcribed with ${asr.backend}`);
        setMode("text");
      } else {
        setOcrNote(asr?.reason ?? "Couldn't transcribe this audio — try again or type what was said.");
      }
    } else {
      setOcrNote(res.error ?? "Could not process this audio — try again or use a different file.");
    }
  };

  const handleFile = (file: File, m: Mode) => {
    if (m === "image") void runImageOcr(file);
    else if (m === "audio") void runAudio(file);
    else void runFileRead(file);
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleFile(file, mode);
  };

  // Email/website verification has no dedicated backend field — fold the value
  // into the analyzed text, where entity extraction + intel.search pick it up.
  const artifactText = [text, email, website].map((s) => s.trim()).filter(Boolean).join(" ");
  const canSubmit = Boolean(artifactText || number.trim() || upi.trim());

  const verify = async () => {
    if (!canSubmit) return;
    setToken(null);
    setResult(null);
    setInvestigating(true);
    setStepIndex(0);

    let idx = 0;
    const timer = window.setInterval(() => {
      idx = Math.min(idx + 1, INVESTIGATION_STEPS.length - 1);
      setStepIndex(idx);
    }, STEP_MS);

    const res = await api.shieldVerify({
      text: artifactText,
      number: number || null,
      upi: upi || null,
      city: city || null,
    });

    window.clearInterval(timer);
    // Honest fast-forward: if the response beat the ticker, finish the
    // remaining steps quickly rather than claiming they were already done.
    while (idx < INVESTIGATION_STEPS.length - 1) {
      await new Promise((r) => setTimeout(r, BURST_MS));
      idx += 1;
      setStepIndex(idx);
    }
    await new Promise((r) => setTimeout(r, 220));

    setInvestigating(false);
    if (res.ok) setResult(res.data);
  };

  const preserve = async () => {
    setSaving(true);
    const res = await api.shieldPreserve({
      text: artifactText,
      number: number || null,
      upi: upi || null,
      city: city || null,
    });
    setSaving(false);
    if (res.ok) {
      setToken(res.data.token);
      setResult(res.data.result);
    }
  };

  return (
    <div className="page shield">
      <header className="page__head">
        <h1 className="page__title">Analyze something</h1>
        <p className="page__lede">
          Got a call or message that feels off? We'll investigate it the way
          an analyst would — a verdict, why we think so, and exactly what to
          do next. Nothing you enter leaves your control.
        </p>
      </header>

      <div className="shield-grid">
        {/* input */}
        <div className="card">
          {entry === "picker" && (
            <TaskPicker
              onChat={startMessage}
              onUpload={() => setEntry("upload-picker")}
              onVerify={() => setEntry("verify-picker")}
            />
          )}

          {entry === "upload-picker" && (
            <UploadPicker onBack={() => setEntry("picker")} onPick={startUpload} />
          )}

          {entry === "verify-picker" && (
            <VerifyPicker onBack={() => setEntry("picker")} onPick={startVerify} />
          )}

          {entry === "form" && (
            <>
              <button className="backlink" onClick={backToPicker}>
                <ChevronLeft size={14} /> Start over
              </button>
              <h2 className="card__title" style={{ marginTop: "var(--s-3)" }}>
                <ShieldAlert size={16} /> {FORM_TITLE[verifyType ?? mode] ?? "Check something suspicious"}
              </h2>

              {ocrNote && (
                <div className="banner" style={{ margin: "var(--s-3) 0" }}>
                  <Info size={16} />
                  <div className="small">{ocrNote}</div>
                </div>
              )}

              {/* Focused single-value verification */}
              {verifyType ? (
                <VerifyField
                  type={verifyType}
                  inputRef={focusField}
                  number={number}
                  upi={upi}
                  email={email}
                  website={website}
                  setNumber={setNumber}
                  setUpi={setUpi}
                  setEmail={setEmail}
                  setWebsite={setWebsite}
                  onSubmit={verify}
                />
              ) : (mode === "file" || mode === "image" || mode === "audio") && !text ? (
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
                    {ocrBusy ? (
                      <span className="spinner" style={{ width: 24, height: 24 }} />
                    ) : (
                      <UploadIcon mode={mode} />
                    )}
                    <strong style={{ fontSize: "var(--t-sm)" }}>
                      {ocrBusy ? DROP_BUSY[mode] : DROP_IDLE[mode]}
                    </strong>
                    <span className="small faint">{DROP_HINT[mode]}</span>
                  </div>
                  <input
                    ref={fileInput}
                    type="file"
                    hidden
                    accept={ACCEPT[mode]}
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file) handleFile(file, mode);
                    }}
                  />
                </>
              ) : (
                <>
                  <label className="fieldlabel">The message or what they said</label>
                  <textarea
                    className="field"
                    rows={5}
                    placeholder="e.g. 'Main CBI se bol raha hoon, aapke Aadhaar par drugs ka parcel mila hai. RBI account mein 50000 transfer kariye…'"
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                  />
                  <button
                    className="backlink"
                    style={{ marginTop: 8 }}
                    onClick={() => {
                      setMode("file");
                      setText("");
                      setTimeout(() => fileInput.current?.click(), 0);
                    }}
                  >
                    <FileText size={13} /> …or upload an exported chat
                  </button>
                  <input
                    ref={fileInput}
                    type="file"
                    hidden
                    accept={ACCEPT.file}
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file) handleFile(file, "file");
                    }}
                  />
                </>
              )}

              {/* Number / UPI are optional here — AegisAI extracts them from the
                  message itself. Shown only for the message/upload flows. */}
              {!verifyType && (mode === "text" || text) && (
                <div className="row" style={{ gap: "var(--s-2)", marginTop: "var(--s-3)" }}>
                  <div style={{ flex: "1 1 160px" }}>
                    <label className="fieldlabel">Caller number (optional)</label>
                    <input className="field" placeholder="e.g. 7042118830" value={number} onChange={(e) => setNumber(e.target.value)} />
                  </div>
                  <div style={{ flex: "1 1 160px" }}>
                    <label className="fieldlabel">UPI ID (optional)</label>
                    <input className="field" placeholder="e.g. cbi.verify@okaxis" value={upi} onChange={(e) => setUpi(e.target.value)} />
                  </div>
                </div>
              )}

              {/* Optional, dismissible city — never a blocking field. */}
              {!askCity ? (
                <button className="backlink" style={{ marginTop: "var(--s-3)" }} onClick={() => setAskCity(true)}>
                  <MapPin size={13} /> Add your city for local scam activity (optional)
                </button>
              ) : (
                <div style={{ marginTop: "var(--s-3)" }}>
                  <label className="fieldlabel">Your city (for local hotspot context)</label>
                  <select className="field" value={city} onChange={(e) => setCity(e.target.value)}>
                    <option value="">Prefer not to say</option>
                    {CITY_OPTIONS.map((c) => (
                      <option key={c} value={c}>
                        {c}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              <button
                className="btn2 btn2--primary"
                style={{ marginTop: "var(--s-4)", width: "100%" }}
                onClick={verify}
                disabled={investigating || ocrBusy || !canSubmit}
              >
                {investigating ? "Investigating…" : "Analyze"}
              </button>
              <p className="small faint" style={{ marginTop: "var(--s-3)" }}>
                This is guidance, not a substitute for reporting fraud on 1930 or at cybercrime.gov.in.
              </p>
            </>
          )}
        </div>

        {/* result */}
        <div className="stack">
          {!investigating && !result && (
            <div className="card shield-empty">
              <ShieldCheck size={30} />
              <p className="muted">Your verdict and next steps will appear here.</p>
            </div>
          )}

          {investigating && <InvestigatingLoader stepIndex={stepIndex} />}

          {!investigating && result && (
            <InvestigationReport result={result} onPreserve={preserve} saving={saving} token={token} />
          )}
        </div>
      </div>

      {/* awareness */}
      {awareness && (
        <div className="card" style={{ marginTop: "var(--s-6)" }}>
          <h2 className="card__title">
            <Sparkles size={16} /> What's circulating right now
          </h2>
          <p className="small muted" style={{ marginTop: 0 }}>
            The scam campaigns the network is seeing most, from Module 2 intelligence.
          </p>
          <div className="grid2">
            {awareness.trending_scams.map((s) => (
              <div key={s.cluster_id} className="awarerow">
                <span className="chip" data-risk={s.risk}>
                  {s.risk}
                </span>
                <strong className="small">{s.scam}</strong>
                <p className="small faint" style={{ margin: "2px 0 0" }}>
                  {s.size} linked cases · {s.states.join(", ")}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

const FORM_TITLE: Record<string, string> = {
  text: "Paste the message or chat",
  file: "Upload a document",
  image: "Upload a screenshot",
  audio: "Upload a recording",
  phone: "Verify a phone number",
  upi: "Verify a UPI ID",
  email: "Verify an email address",
  website: "Verify a website",
};

const DROP_IDLE: Record<string, string> = {
  file: "Drop a document, or click to choose",
  image: "Drop a screenshot, or click to choose",
  audio: "Drop a recording, or click to choose",
  text: "",
};
const DROP_BUSY: Record<string, string> = {
  file: "Reading the document…",
  image: "Reading the screenshot…",
  audio: "Transcribing the recording…",
  text: "",
};
const DROP_HINT: Record<string, string> = {
  file: ".txt · .json · .csv · .md · .vtt · .srt — up to 4MB",
  image: ".png · .jpg · .webp · .tiff — up to 4MB",
  audio: ".wav · .mp3 · .m4a · .ogg — up to 4MB",
  text: "",
};
const ACCEPT: Record<string, string> = {
  file: ".txt,.json,.csv,.md,.log,.vtt,.srt",
  image: ".png,.jpg,.jpeg,.webp,.bmp,.tiff,.gif",
  audio: ".wav,.mp3,.m4a,.ogg,.flac,.webm,.aac",
  text: ".txt,.json,.csv,.md,.log,.vtt,.srt",
};

function UploadIcon({ mode }: { mode: Mode }) {
  if (mode === "image") return <ImageIcon size={24} />;
  if (mode === "audio") return <Mic size={24} />;
  return <FileUp size={24} />;
}

function TaskPicker({ onChat, onUpload, onVerify }: { onChat: () => void; onUpload: () => void; onVerify: () => void }) {
  return (
    <>
      <h2 className="card__title">What would you like to analyze?</h2>
      <div className="task-picker">
        <button className="task-tile" onClick={onChat}>
          <MessageSquare size={20} />
          <strong>Message or Chat</strong>
          <span className="small faint">Paste what they said or sent</span>
        </button>
        <button className="task-tile" onClick={onUpload}>
          <FileUp size={20} />
          <strong>Upload Evidence</strong>
          <span className="small faint">A screenshot, document, or recording</span>
        </button>
        <button className="task-tile" onClick={onVerify}>
          <Search size={20} />
          <strong>Verify Something</strong>
          <span className="small faint">A phone number, UPI, email, or website</span>
        </button>
      </div>
    </>
  );
}

function UploadPicker({ onPick, onBack }: { onPick: (m: Mode) => void; onBack: () => void }) {
  return (
    <>
      <button className="backlink" onClick={onBack}>
        <ChevronLeft size={14} /> Back
      </button>
      <h2 className="card__title" style={{ marginTop: "var(--s-3)" }}>
        What kind of evidence?
      </h2>
      <div className="task-picker">
        <button className="task-tile" onClick={() => onPick("image")}>
          <ImageIcon size={20} />
          <strong>Screenshot</strong>
          <span className="small faint">A chat, notice, or payment screen</span>
        </button>
        <button className="task-tile" onClick={() => onPick("file")}>
          <FileText size={20} />
          <strong>Document</strong>
          <span className="small faint">A saved transcript or text file</span>
        </button>
        <button className="task-tile" onClick={() => onPick("audio")}>
          <Mic size={20} />
          <strong>Audio Recording</strong>
          <span className="small faint">A voice note or call recording</span>
        </button>
        <button className="task-tile" onClick={() => onPick("image")}>
          <ImageIcon size={20} />
          <strong>Image</strong>
          <span className="small faint">Any photo of the evidence</span>
        </button>
      </div>
    </>
  );
}

function VerifyPicker({ onPick, onBack }: { onPick: (t: Exclude<VerifyType, null>) => void; onBack: () => void }) {
  return (
    <>
      <button className="backlink" onClick={onBack}>
        <ChevronLeft size={14} /> Back
      </button>
      <h2 className="card__title" style={{ marginTop: "var(--s-3)" }}>
        What would you like to verify?
      </h2>
      <div className="task-picker">
        <button className="task-tile" onClick={() => onPick("phone")}>
          <Phone size={20} />
          <strong>Phone Number</strong>
          <span className="small faint">Who's calling, and is it known fraud?</span>
        </button>
        <button className="task-tile" onClick={() => onPick("upi")}>
          <IndianRupee size={20} />
          <strong>UPI ID</strong>
          <span className="small faint">Before you pay anyone</span>
        </button>
        <button className="task-tile" onClick={() => onPick("email")}>
          <Mail size={20} />
          <strong>Email</strong>
          <span className="small faint">A sender or address that looks off</span>
        </button>
        <button className="task-tile" onClick={() => onPick("website")}>
          <Globe size={20} />
          <strong>Website</strong>
          <span className="small faint">A link before you click it</span>
        </button>
      </div>
    </>
  );
}

function VerifyField({
  type,
  inputRef,
  number,
  upi,
  email,
  website,
  setNumber,
  setUpi,
  setEmail,
  setWebsite,
  onSubmit,
}: {
  type: Exclude<VerifyType, null>;
  inputRef: React.RefObject<HTMLInputElement>;
  number: string;
  upi: string;
  email: string;
  website: string;
  setNumber: (v: string) => void;
  setUpi: (v: string) => void;
  setEmail: (v: string) => void;
  setWebsite: (v: string) => void;
  onSubmit: () => void;
}) {
  const cfg = {
    phone: { label: "Phone number", placeholder: "e.g. 7042118830", value: number, set: setNumber },
    upi: { label: "UPI ID", placeholder: "e.g. cbi.verify@okaxis", value: upi, set: setUpi },
    email: { label: "Email address", placeholder: "e.g. refunds@sbi-verify.com", value: email, set: setEmail },
    website: { label: "Website", placeholder: "e.g. sbi-kyc-update.in", value: website, set: setWebsite },
  }[type];
  return (
    <div>
      <label className="fieldlabel">{cfg.label}</label>
      <input
        ref={inputRef}
        className="field"
        placeholder={cfg.placeholder}
        value={cfg.value}
        onChange={(e) => cfg.set(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && onSubmit()}
      />
    </div>
  );
}
