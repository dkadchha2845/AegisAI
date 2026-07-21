/**
 * Shield — the CFSRP citizen fraud shield (KAVACH Module 3).
 *
 * The one screen a frightened, non-technical person uses mid-scam. It fuses
 * Module 1 (is this message coercive?) with Module 2 (is this number known fraud
 * infrastructure?) into one verdict, then does the thing a leaflet cannot:
 * stage-aware guidance, a one-tap emergency response, evidence preservation, and
 * a ready-to-file cybercrime complaint.
 *
 * Deliberately calmer than the analyst instruments — big type, plain language,
 * the helpline never more than one tap away. Still a pure renderer: the verdict,
 * the guidance, and the emergency severity are all fields the API decided.
 */

import { useEffect, useState } from "react";
import {
  AlertTriangle,
  Phone,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Download,
  Save,
} from "lucide-react";
import * as api from "@/lib/api";
import type { Hotspot, VerifyResult } from "@/lib/api";
import { CITY_OPTIONS } from "@/lib/stages";

const VERDICT_COPY: Record<string, string> = {
  LIKELY_SCAM: "This is very likely a scam",
  SUSPICIOUS: "This looks suspicious",
  LIKELY_LEGITIMATE: "No scam patterns detected",
  INSUFFICIENT: "Not enough to judge yet",
};

export function Shield() {
  const [text, setText] = useState("");
  const [number, setNumber] = useState("");
  const [upi, setUpi] = useState("");
  const [city, setCity] = useState("");
  const [result, setResult] = useState<VerifyResult | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
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

  const verify = async () => {
    if (!text.trim() && !number.trim() && !upi.trim()) return;
    setBusy(true);
    setToken(null);
    const res = await api.shieldVerify({
      text,
      number: number || null,
      upi: upi || null,
      city: city || null,
    });
    setBusy(false);
    if (res.ok) setResult(res.data);
  };

  const preserve = async () => {
    setSaving(true);
    const res = await api.shieldPreserve({
      text,
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
        <p className="eyebrow">Module 3 · CFSRP</p>
        <h1 className="page__title">Citizen fraud shield</h1>
        <p className="page__lede">
          Got a call or message that feels off? Paste it here. You will get an
          instant verdict, exactly what to do right now, and — if you need it —
          one tap to the cyber-fraud helpline and a ready-to-file complaint.
          Nothing you enter leaves your control.
        </p>
      </header>

      <div className="shield-grid">
        {/* input */}
        <div className="card">
          <h2 className="card__title"><ShieldAlert size={16} /> Check something suspicious</h2>
          <label className="fieldlabel">The message or what they said</label>
          <textarea
            className="field"
            rows={5}
            placeholder="e.g. 'Main CBI se bol raha hoon, aapke Aadhaar par drugs ka parcel mila hai. RBI account mein 50000 transfer kariye…'"
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <div className="row" style={{ gap: "var(--s-2)", marginTop: "var(--s-3)" }}>
            <div style={{ flex: "1 1 160px" }}>
              <label className="fieldlabel">Caller number</label>
              <input className="field" placeholder="e.g. 7042118830" value={number}
                     onChange={(e) => setNumber(e.target.value)} />
            </div>
            <div style={{ flex: "1 1 160px" }}>
              <label className="fieldlabel">UPI ID they asked for</label>
              <input className="field" placeholder="e.g. cbi.verify@okaxis" value={upi}
                     onChange={(e) => setUpi(e.target.value)} />
            </div>
          </div>
          <div style={{ marginTop: "var(--s-3)" }}>
            <label className="fieldlabel">Your city (for local hotspot context)</label>
            <select className="field" value={city} onChange={(e) => setCity(e.target.value)}>
              <option value="">Prefer not to say</option>
              {CITY_OPTIONS.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <button className="btn2 btn2--primary" style={{ marginTop: "var(--s-4)", width: "100%" }}
                  onClick={verify} disabled={busy}>
            {busy ? "Checking…" : "Check now"}
          </button>
          <p className="small faint" style={{ marginTop: "var(--s-3)" }}>
            This is guidance, not a substitute for reporting fraud on 1930 or at
            cybercrime.gov.in.
          </p>
        </div>

        {/* result */}
        <div className="stack">
          {!result && (
            <div className="card shield-empty">
              <ShieldCheck size={30} />
              <p className="muted">Your verdict and next steps will appear here.</p>
            </div>
          )}

          {result && <ResultPanel result={result} onPreserve={preserve} saving={saving} token={token} />}
        </div>
      </div>

      {/* awareness */}
      {awareness && (
        <div className="card" style={{ marginTop: "var(--s-6)" }}>
          <h2 className="card__title"><Sparkles size={16} /> What's circulating right now</h2>
          <p className="small muted" style={{ marginTop: 0 }}>
            The scam campaigns the network is seeing most, from Module 2 intelligence.
          </p>
          <div className="grid2">
            {awareness.trending_scams.map((s) => (
              <div key={s.cluster_id} className="awarerow">
                <span className="chip" data-risk={s.risk}>{s.risk}</span>
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

function ResultPanel({
  result,
  onPreserve,
  saving,
  token,
}: {
  result: VerifyResult;
  onPreserve: () => void;
  saving: boolean;
  token: string | null;
}) {
  const em = result.emergency;
  return (
    <>
      {/* panic banner for critical/high */}
      {em.show_panic_banner && (
        <div className="panicbanner">
          <div className="panicbanner__head">
            <AlertTriangle size={18} /> {em.title}
          </div>
          <div className="panicbanner__helplines">
            {em.helplines.filter((h) => h.priority === "primary").map((h) => (
              <a key={h.value} className="helpbtn" href={h.action}
                 target={h.action.startsWith("http") ? "_blank" : undefined} rel="noreferrer">
                <Phone size={14} /> {h.value}
              </a>
            ))}
          </div>
        </div>
      )}

      {/* verdict */}
      <div className="verdict" data-v={result.verdict}>
        <div className="verdict__head">
          <span className="verdict__label">{VERDICT_COPY[result.verdict] ?? result.verdict}</span>
          <span className="verdict__score">{Math.round(result.score)}</span>
        </div>
        <p className="verdict__summary">{result.summary}</p>
        <div className="row" style={{ gap: 6, marginTop: "var(--s-3)" }}>
          <span className="chip" data-risk={result.level}>{result.level}</span>
          {result.stage !== "BENIGN" && (
            <span className="chip">Stage: {result.stage.replace(/_/g, " ").toLowerCase()}</span>
          )}
          {result.intel.known_infrastructure && (
            <span className="chip" data-tone="bad">⚠ Known fraud infrastructure</span>
          )}
        </div>
      </div>

      {/* module 2 corroboration */}
      {result.intel.clusters.length > 0 && (
        <div className="card">
          <h3 className="card__title" style={{ fontSize: "var(--t-base)" }}>Linked to known fraud networks</h3>
          {result.intel.clusters.map((c) => (
            <div key={c.cluster_id} className="linkedcluster">
              <span className="mono small">{c.cluster_id}</span>
              <span className="small">{c.primary_scam}</span>
              <span className="chip" data-risk={c.risk} style={{ marginLeft: "auto" }}>{c.risk}</span>
              <p className="small faint" style={{ width: "100%", margin: "4px 0 0" }}>
                This identifier appears in a {c.size}-case network across {c.states.join(", ")}.
              </p>
            </div>
          ))}
        </div>
      )}

      {/* guidance */}
      <div className="card guidance-card">
        <h3 className="card__title" style={{ fontSize: "var(--t-base)" }}>
          {result.guidance.headline}
        </h3>
        <ul className="actions">
          {result.guidance.actions.map((a, i) => <li key={i}>{a}</li>)}
        </ul>
        {result.guidance.coach_line && (
          <div className="coachline">
            <span className="label">Say this, out loud</span>
            <p className="coachline__quote">"{result.guidance.coach_line}"</p>
            {result.guidance.coach_why && <p className="small faint">{result.guidance.coach_why}</p>}
          </div>
        )}
      </div>

      {/* emergency checklist */}
      <div className="card">
        <h3 className="card__title" style={{ fontSize: "var(--t-base)" }}>
          {em.severity === "urgent" ? "Do this now" : "Immediate checklist"}
        </h3>
        <ul className="checklist">
          {em.checklist.map((c, i) => <li key={i}>{c}</li>)}
        </ul>
        <div className="row" style={{ gap: "var(--s-2)", marginTop: "var(--s-3)" }}>
          {em.helplines.map((h) => (
            <a key={h.value} className="btn2" href={h.action}
               target={h.action.startsWith("http") ? "_blank" : undefined} rel="noreferrer">
              <Phone size={13} /> {h.name} · {h.value}
            </a>
          ))}
        </div>
      </div>

      {/* nearby hotspots */}
      {result.nearby_hotspots.length > 0 && (
        <div className="card">
          <h3 className="card__title" style={{ fontSize: "var(--t-base)" }}>Fraud activity near you</h3>
          <div className="stack" style={{ gap: 6 }}>
            {result.nearby_hotspots.map((h) => (
              <div key={h.name} className="row" style={{ justifyContent: "space-between" }}>
                <span className="small">{h.name}</span>
                <span className="chip" data-risk={h.risk}>{h.cases} cases · {h.risk}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* preserve + complaint */}
      <div className="card">
        <h3 className="card__title" style={{ fontSize: "var(--t-base)" }}>Preserve evidence &amp; report</h3>
        {!token ? (
          <>
            <p className="small muted" style={{ marginTop: 0 }}>
              Save this to a secure evidence vault and generate a structured
              cybercrime complaint you can file at cybercrime.gov.in.
            </p>
            <button className="btn2 btn2--primary" onClick={onPreserve} disabled={saving}>
              <Save size={14} /> {saving ? "Preserving…" : "Preserve & prepare complaint"}
            </button>
          </>
        ) : (
          <>
            <div className="banner" style={{ marginBottom: "var(--s-3)" }}>
              <div className="small">
                Evidence preserved. Keep this reference to reopen it:{" "}
                <span className="mono">{token.slice(0, 12)}…</span>
              </div>
            </div>
            <a className="btn2 btn2--primary" href={api.complaintPdfUrl(token)} target="_blank" rel="noreferrer">
              <Download size={14} /> Download complaint package (PDF)
            </a>
          </>
        )}
      </div>
    </>
  );
}
