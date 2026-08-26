/**
 * Emergency — the one screen for someone who needs help this minute.
 *
 * No analysis, no forms. The helpline directory comes from Module 3's static,
 * verifiable response data (the same 1930 / cybercrime.gov.in / 112 the shield
 * surfaces), presented as big, tappable actions, followed by the do-this-now
 * checklist for a payment that's already in motion.
 */

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, ArrowRight, Phone } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import * as api from "@/lib/api";
import type { Helpline } from "@/lib/api";

const CHECKLIST = [
  "Hang up now. No real officer keeps you on a call to move money.",
  "Do not share any OTP, PIN, Aadhaar number, or account detail.",
  "If you've already paid or shared something, call 1930 immediately — the first hour is when money can still be frozen.",
  "Tell a family member what happened. Scammers rely on you staying isolated.",
  "Take screenshots of everything before you delete or block anything.",
];

export function Emergency() {
  const [helplines, setHelplines] = useState<Helpline[]>([]);

  useEffect(() => {
    void (async () => {
      const res = await api.getHelplines();
      if (res.ok) setHelplines(res.data.helplines);
    })();
  }, []);

  return (
    <div className="page">
      <PageHeader
        title="Emergency help"
        lede="If money is being moved right now, act first and read later. Call the helpline — reporting within the first hour is what gets a payment frozen."
      />

      <div className="emergency-lines">
        {helplines.map((h) => (
          <a
            key={h.value}
            className="emergency-line"
            data-priority={h.priority}
            href={h.action}
            target={h.action.startsWith("http") ? "_blank" : undefined}
            rel="noreferrer"
          >
            <Phone size={18} />
            <span className="emergency-line__text">
              <strong>{h.name}</strong>
              <span className="small faint">{h.detail}</span>
            </span>
            <span className="emergency-line__value mono">{h.value}</span>
          </a>
        ))}
      </div>

      <div className="card" style={{ marginTop: "var(--s-5)" }}>
        <h2 className="card__title">
          <AlertTriangle size={16} /> If a scam is in progress
        </h2>
        <ul className="checklist">
          {CHECKLIST.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ul>
      </div>

      <div className="card">
        <h2 className="card__title">Not sure if it's a scam?</h2>
        <p className="small muted" style={{ marginTop: 0 }}>
          If you have a moment, run the message or number through a quick check first.
        </p>
        <Link className="btn2 btn2--primary" to="/analyze">
          Analyze it <ArrowRight size={14} />
        </Link>
      </div>
    </div>
  );
}
