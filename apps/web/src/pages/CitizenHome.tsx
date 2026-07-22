/**
 * Home — the citizen's starting point.
 *
 * Not a dashboard of system state (that's the analyst's Dashboard, now behind
 * Profile). This asks one question — "how can we help?" — and offers the four
 * things a worried person actually wants to do, in their own words. The scam
 * alerts underneath come from the same Module 2 intelligence that powers the
 * fraud graph, but a citizen just sees "what's going around right now".
 */

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Activity, ArrowRight, FolderArchive, ScanSearch, Siren } from "lucide-react";
import * as api from "@/lib/api";
import type { Hotspot, ScamPoint } from "@/lib/api";
import { ScamMap } from "@/components/map/ScamMap";
import { useAuth } from "@/context/AuthContext";

const TASKS = [
  {
    to: "/live",
    icon: Activity,
    title: "Live Protection",
    body: "On a suspicious call right now? Let KAVACH listen and guide you.",
    tone: "urgent",
  },
  {
    to: "/analyze",
    icon: ScanSearch,
    title: "Analyze Something",
    body: "Paste a message, upload a screenshot, or check a number or UPI ID.",
    tone: "primary",
  },
  {
    to: "/reports",
    icon: FolderArchive,
    title: "My Reports",
    body: "Reopen a saved investigation or file it with the police.",
    tone: "calm",
  },
  {
    to: "/emergency",
    icon: Siren,
    title: "Emergency",
    body: "Money already sent, or need help this minute? Start here.",
    tone: "bad",
  },
];

export function CitizenHome() {
  const { user, authed } = useAuth();
  const [awareness, setAwareness] = useState<{
    trending_scams: { cluster_id: string; scam: string; size: number; risk: string; states: string[] }[];
    hotspot_states: Hotspot[];
  } | null>(null);
  const [points, setPoints] = useState<ScamPoint[]>([]);
  const [scamTypes, setScamTypes] = useState<{ id: string; name: string }[]>([]);

  useEffect(() => {
    void (async () => {
      const res = await api.getAwareness();
      if (res.ok) setAwareness(res.data);
    })();
    void (async () => {
      const res = await api.getPoints();
      if (res.ok) {
        setPoints(res.data.points);
        setScamTypes(res.data.scam_types);
      }
    })();
  }, []);

  // Personalise only for a real signed-in session. In open mode /me returns a
  // seeded ambient identity with no token — greeting a citizen "Hello, Admin"
  // off that would be both wrong and confusing.
  const name = authed && user?.email ? user.email.split("@")[0].split(/[._]/)[0] : null;
  const greeting = name ? `Hello, ${name.charAt(0).toUpperCase()}${name.slice(1)} 👋` : "Hello 👋";

  return (
    <div className="page">
      <header className="page__head">
        <h1 className="page__title">{greeting}</h1>
        <p className="page__lede">How can we help today?</p>
      </header>

      <div className="home-tasks">
        {TASKS.map((t) => (
          <Link key={t.to} to={t.to} className="home-task" data-tone={t.tone}>
            <span className="home-task__icon">
              <t.icon size={22} />
            </span>
            <span className="home-task__text">
              <strong>{t.title}</strong>
              <span className="small faint">{t.body}</span>
            </span>
            <ArrowRight size={16} className="home-task__arrow" />
          </Link>
        ))}
      </div>

      {awareness && (
        <>
          <div className="card" style={{ marginTop: "var(--s-6)" }}>
            <h2 className="card__title">Scams going around right now</h2>
            <p className="small muted" style={{ marginTop: 0 }}>
              The kinds of scams the most people are reporting this week.
            </p>
            <div className="grid2">
              {awareness.trending_scams.map((s) => (
                <div key={s.cluster_id} className="awarerow">
                  <span className="chip" data-risk={s.risk}>
                    {s.risk}
                  </span>
                  <strong className="small">{s.scam}</strong>
                  <p className="small faint" style={{ margin: "2px 0 0" }}>
                    Reported {s.size} times · {s.states.join(", ")}
                  </p>
                </div>
              ))}
            </div>
          </div>

        </>
      )}

      {points.length > 0 && (
        <div className="card">
          <h2 className="card__title">Scam hotspots near you</h2>
          <p className="small muted" style={{ marginTop: 0, marginBottom: "var(--s-3)" }}>
            Every dot is a reported scam. Tap “Scams near me” to see what&apos;s active around you,
            or filter by type and by how recent.
          </p>
          <ScamMap
            points={points}
            scamTypes={scamTypes}
            height={420}
            enableFilters
            showUserLocation
          />
        </div>
      )}

      <p className="small faint" style={{ marginTop: "var(--s-5)" }}>
        KAVACH gives guidance — it's not a substitute for reporting fraud on{" "}
        <strong className="mono">1930</strong> or at{" "}
        <a href="https://cybercrime.gov.in" target="_blank" rel="noreferrer">
          cybercrime.gov.in
        </a>
        .
      </p>
    </div>
  );
}
