/**
 * The citizen's dashboard — §24.
 *
 * What a worried person opening this needs is, in order: a way to start, what
 * they have already checked, and what is going around. Not system state, not
 * agent health, not the roster — an "internal administrative information" list
 * §24 asks to keep off this page, and which they could not read anyway.
 *
 * **Everything here is real.** The case list is `GET /api/investigations`,
 * which the server narrows to the caller's own rows; the saved reports are
 * `/api/reports`, narrowed the same way; the awareness figures are the same
 * aggregate Module 2 intelligence the landing page shows. There are no
 * placeholder tiles and no invented counts — an empty state says the list is
 * empty, which is a true thing to say on the day someone signs up.
 */

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Activity,
  ArrowRight,
  FolderArchive,
  ScanSearch,
  ShieldCheck,
  Siren,
  TrendingUp,
} from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState, SkeletonRows } from "@/components/ui/States";
import { useAuth } from "@/context/AuthContext";
import * as api from "@/lib/api";
import type { CaseSummary, InvestigationSummary } from "@/lib/api";

const ACTIONS = [
  {
    to: "/analyze",
    icon: ScanSearch,
    title: "Check something",
    body: "Paste a message, upload a screenshot, or verify a number or UPI ID.",
    tone: "primary",
  },
  {
    to: "/live",
    icon: Activity,
    title: "Live Protection",
    body: "On a suspicious call right now? Let AegisAI listen and guide you.",
    tone: "urgent",
  },
  {
    to: "/reports",
    icon: FolderArchive,
    title: "My reports",
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

export function CitizenDashboard() {
  const { user } = useAuth();
  const [cases, setCases] = useState<InvestigationSummary[] | null>(null);
  const [reports, setReports] = useState<CaseSummary[] | null>(null);
  const [trending, setTrending] = useState<
    { cluster_id: string; scam: string; size: number; risk: string }[]
  >([]);

  useEffect(() => {
    void (async () => {
      const [inv, rep, aware] = await Promise.all([
        api.listInvestigations({ limit: 6 }),
        api.listReports(),
        api.getAwareness(),
      ]);
      setCases(inv.ok ? inv.data.investigations : []);
      setReports(rep.ok ? rep.data.reports : []);
      if (aware.ok) setTrending(aware.data.trending_scams.slice(0, 4));
    })();
  }, []);

  const greeting = user?.display_name ? `Hello, ${user.display_name}` : "Your dashboard";

  return (
    <div className="page">
      <PageHeader
        title={greeting}
        lede="Check something suspicious, reopen an investigation, or see what's going around."
        actions={
          <Link className="btn2 btn2--primary" to="/analyze">
            New investigation <ArrowRight size={15} aria-hidden="true" />
          </Link>
        }
      />

      {/* The same card component the citizen Home page uses. Two dashboards
          with two implementations of one card is how a design system rots — and
          the classes already exist, styled and responsive. */}
      <div className="home-tasks">
        {ACTIONS.map((a) => (
          <Link key={a.to} to={a.to} className="home-task" data-tone={a.tone}>
            <span className="home-task__icon">
              <a.icon size={22} aria-hidden="true" />
            </span>
            <span className="home-task__text">
              <strong>{a.title}</strong>
              <span className="small faint">{a.body}</span>
            </span>
            <ArrowRight size={16} className="home-task__arrow" aria-hidden="true" />
          </Link>
        ))}
      </div>

      {/* --- My investigations ------------------------------------------- */}
      <section className="card">
        <h2 className="card__title">
          <ScanSearch size={16} aria-hidden="true" /> My investigations
        </h2>
        {!cases && <SkeletonRows rows={3} cols={4} />}
        {cases && cases.length === 0 && (
          <EmptyState
            inline
            title="Nothing investigated yet"
            body="Anything you submit for investigation appears here, and only you and the investigators authorised to work it can see it."
            action={
              <Link className="btn2 btn2--primary" to="/analyze">
                Check something now
              </Link>
            }
          />
        )}
        {cases && cases.length > 0 && (
          <div className="cb-tablewrap">
            <table className="cb-table">
              <thead>
                <tr>
                  <th>Case</th>
                  <th>Opened</th>
                  <th>Status</th>
                  <th>Risk</th>
                </tr>
              </thead>
              <tbody>
                {cases.map((c) => (
                  <tr key={c.case_id}>
                    <td className="mono small">{c.case_id}</td>
                    <td className="small muted">{fmt(c.created_at)}</td>
                    <td>
                      <span className="chip" data-tone={statusTone(c.status)}>
                        {c.status.toLowerCase()}
                      </span>
                    </td>
                    <td>
                      {/* Never rendered as 0 when it is absent. An unfinished
                          investigation with no score is not a safe one, and a
                          dial reading zero would say it was — the same refusal
                          `RiskDial` and `investigations/report.py` make. */}
                      {c.risk_score == null ? (
                        <span className="small faint">not scored yet</span>
                      ) : (
                        <span className="chip" data-tone={riskTone(c.risk_level)}>
                          {Math.round(c.risk_score)} · {(c.risk_level ?? "").toLowerCase()}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* --- Saved reports ------------------------------------------------ */}
      <section className="card">
        <h2 className="card__title">
          <FolderArchive size={16} aria-hidden="true" /> Saved reports
        </h2>
        {!reports && <SkeletonRows rows={2} cols={3} />}
        {reports && reports.length === 0 && (
          <EmptyState
            inline
            title="No saved reports"
            body="A check is analysed and forgotten unless you preserve it. Preserving one puts it here, ready to file with the police."
          />
        )}
        {reports && reports.length > 0 && (
          <ul className="factlist">
            {reports.slice(0, 5).map((r) => (
              <li key={r.report_id}>
                <strong className="mono">{r.report_id}</strong> — {r.incident_type ?? "incident"}{" "}
                <span className="faint small">{fmt(r.created_at)}</span>
              </li>
            ))}
          </ul>
        )}
        {reports && reports.length > 0 && (
          <Link className="btn2" to="/reports" style={{ marginTop: "var(--s-3)" }}>
            Open My Reports <ArrowRight size={14} aria-hidden="true" />
          </Link>
        )}
      </section>

      {/* --- What's going around ------------------------------------------ */}
      <section className="card">
        <h2 className="card__title">
          <TrendingUp size={16} aria-hidden="true" /> Going around right now
        </h2>
        <p className="small muted" style={{ marginTop: 0 }}>
          Aggregate patterns from the fraud-intelligence graph. No one's personal
          details appear here.
        </p>
        {trending.length === 0 ? (
          <p className="small faint">Nothing to report.</p>
        ) : (
          <ul className="factlist">
            {trending.map((t) => (
              <li key={t.cluster_id}>
                <strong>{t.scam}</strong> — {t.size} linked reports{" "}
                <span className="chip" data-tone={t.risk === "CRITICAL" ? "bad" : undefined}>
                  {t.risk.toLowerCase()}
                </span>
              </li>
            ))}
          </ul>
        )}
        <Link className="btn2" to="/learn" style={{ marginTop: "var(--s-3)" }}>
          <ShieldCheck size={14} aria-hidden="true" /> How these scams work
        </Link>
      </section>
    </div>
  );
}

function fmt(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

function riskTone(level: string | null): string | undefined {
  const l = (level ?? "").toUpperCase();
  if (l === "CRITICAL" || l === "HIGH") return "bad";
  if (l === "ELEVATED" || l === "WATCH") return "warn";
  return "ok";
}

function statusTone(status: string): string | undefined {
  const s = status.toUpperCase();
  if (s === "COMPLETE") return "ok";
  if (s === "FAILED") return "bad";
  return undefined;
}
