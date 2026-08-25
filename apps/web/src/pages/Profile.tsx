/**
 * Profile — the citizen's account, and the doorway to the analyst tools.
 *
 * The three research modules (RSSIE / FIGAE / CFSRP) and the instruments an
 * investigator uses to demo them — the live-ops dashboard, the raw fraud
 * graph, the audit analyzer, the model card — still exist and matter for the
 * paper and the presentation. They just don't belong in a citizen's primary
 * navigation. They live here, clearly labelled as the professional side.
 */

import { Link } from "react-router-dom";
import {
  Activity,
  BarChart3,
  LogIn,
  LogOut,
  Network,
  ScanLine,
  ScanSearch,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { useAuth } from "@/context/AuthContext";

const TOOLS = [
  { to: "/investigate", icon: ScanSearch, label: "Investigate", blurb: "Submit evidence to the agent graph and watch each node complete." },
  { to: "/dashboard", icon: BarChart3, label: "Operations dashboard", blurb: "System state, live metrics, and what's degraded." },
  { to: "/analyst/console", icon: Activity, label: "Live console (analyst)", blurb: "The full instrument view — threat meter, digital twin, manipulation map." },
  { to: "/intel", icon: Network, label: "Fraud intelligence graph", blurb: "The full knowledge graph, clusters, and hotspot analytics." },
  { to: "/analyzer", icon: ScanLine, label: "Analyzer (audit view)", blurb: "The raw, line-by-line detector output with driver weights." },
  { to: "/guardian", icon: ShieldCheck, label: "Guardian", blurb: "The intervention console — hold a payment, alert a contact." },
  { to: "/model", icon: Sparkles, label: "Model card", blurb: "Architecture, training data, and where the model is weak." },
];

export function Profile() {
  const { user, org, authed, logout } = useAuth();

  return (
    <div className="page">
      <header className="page__head">
        <h1 className="page__title">Profile</h1>
        <p className="page__lede">Your account and the professional tools behind AegisAI.</p>
      </header>

      <div className="card">
        <h2 className="card__title">Account</h2>
        {authed && user ? (
          <>
            <dl className="kv" style={{ marginTop: "var(--s-2)" }}>
              <dt>Signed in as</dt>
              <dd>{user.email}</dd>
              <dt>Role</dt>
              <dd style={{ textTransform: "capitalize" }}>{user.role}</dd>
              {org?.name && (
                <>
                  <dt>Organisation</dt>
                  <dd>{org.name}</dd>
                </>
              )}
            </dl>
            <button className="btn2" style={{ marginTop: "var(--s-4)" }} onClick={logout}>
              <LogOut size={14} /> Sign out
            </button>
          </>
        ) : (
          <>
            <p className="small muted" style={{ marginTop: 0 }}>
              You don't need an account to check something or get help. Sign in only if
              you're an analyst using the professional tools.
            </p>
            <Link className="btn2 btn2--primary" to="/login">
              <LogIn size={14} /> Sign in
            </Link>
          </>
        )}
      </div>

      <div className="card">
        <h2 className="card__title">Analyst tools</h2>
        <p className="small muted" style={{ marginTop: 0 }}>
          The professional side of AegisAI — the instruments an investigator uses. These
          need a sign-in.
        </p>
        <div className="tool-list">
          {(user?.role === "admin" || user?.role === "owner") && (
            <Link to="/admin" className="tool-row" style={{ borderColor: "color-mix(in srgb, var(--accent) 45%, transparent)" }}>
              <BarChart3 size={18} />
              <span className="tool-row__text">
                <strong className="small">Admin dashboard</strong>
                <span className="small faint">
                  Platform health, fraud analytics, hotspot monitoring, and user management.
                </span>
              </span>
            </Link>
          )}
          {TOOLS.map((t) => (
            <Link key={t.to} to={t.to} className="tool-row">
              <t.icon size={18} />
              <span className="tool-row__text">
                <strong className="small">{t.label}</strong>
                <span className="small faint">{t.blurb}</span>
              </span>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
