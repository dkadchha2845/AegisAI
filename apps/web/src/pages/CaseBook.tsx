/**
 * Case book — the platform surface: saved evidence packages, the activity log,
 * and (for admins) user management.
 *
 * It reads from the same server the whole app does, so in open mode it just
 * works as the seeded admin; when enforcement is on, the sign-in card gates it.
 * Sections the current role cannot see are not rendered at all rather than
 * shown disabled — a viewer never learns the audit log exists to be denied.
 */

import { useCallback, useEffect, useState } from "react";
import { FileText, LogIn, LogOut, RefreshCw, ShieldAlert } from "lucide-react";
import * as api from "@/lib/api";
import type { AuditEvent, AuthUser, CaseSummary } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

export function CaseBook() {
  const auth = useAuth();
  const isAdmin = auth.user?.role === "admin";

  return (
    <div className="page">
      <p className="eyebrow">Platform</p>
      <h1 className="page__title">Case book</h1>
      <p className="page__lede">
        Saved evidence packages, the append-only activity log, and user
        management. Everything here is scoped by role — an analyst can save and
        read cases; the audit log and user list are admin-only.
      </p>

      <IdentityCard />
      <SavedCases />
      {isAdmin && <AuditLog />}
      {isAdmin && <Users />}
    </div>
  );
}

/* ---------------------------------------------------------------- identity */

function IdentityCard() {
  const auth = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    setError(null);
    const res = await auth.login(email, password);
    setBusy(false);
    if (!res.ok) setError(res.error ?? "Login failed");
    else setPassword("");
  };

  return (
    <div className="card">
      <h2 className="card__title">
        <ShieldAlert size={16} /> Identity
      </h2>
      {auth.user ? (
        <div className="row" style={{ alignItems: "center", gap: "var(--s-3)" }}>
          <div style={{ flex: 1 }}>
            Signed in as <strong>{auth.user.email}</strong>{" "}
            <span className="chip" data-tone="ok">{auth.user.role}</span>
            <p className="small muted" style={{ margin: "4px 0 0" }}>
              {auth.enforced
                ? "Authentication is enforced."
                : "Open mode — no login required for the demo; you are acting as the seeded admin."}
            </p>
          </div>
          {auth.enforced && (
            <button className="btn2 btn2--ghost" onClick={auth.logout}>
              <LogOut size={14} /> Sign out
            </button>
          )}
        </div>
      ) : (
        <div className="row" style={{ gap: "var(--s-2)", flexWrap: "wrap" }}>
          <input
            className="field"
            placeholder="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            style={{ flex: "1 1 180px" }}
          />
          <input
            className="field"
            type="password"
            placeholder="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit()}
            style={{ flex: "1 1 160px" }}
          />
          <button className="btn2 btn2--primary" onClick={submit} disabled={busy}>
            <LogIn size={14} /> {busy ? "Signing in…" : "Sign in"}
          </button>
        </div>
      )}
      {error && (
        <div className="banner banner--bad" style={{ marginTop: "var(--s-3)" }}>
          <div className="small">{error}</div>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------- saved cases */

function SavedCases() {
  const [rows, setRows] = useState<CaseSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const res = await api.listReports();
    if (res.ok) setRows(res.data.reports);
    else setError(res.error);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="card">
      <h2 className="card__title">
        <FileText size={16} /> Saved cases
        <button className="btn2 btn2--ghost cb-refresh" onClick={load}>
          <RefreshCw size={13} /> Refresh
        </button>
      </h2>
      {error && <p className="small muted">{error}</p>}
      {rows && rows.length === 0 && (
        <p className="small muted">
          No saved cases yet. On the Guardian screen, save a live call's evidence
          package and it appears here.
        </p>
      )}
      {rows && rows.length > 0 && (
        <div className="cb-tablewrap">
          <table className="cb-table">
            <thead>
              <tr>
                <th>Report</th>
                <th>Incident</th>
                <th>Peak</th>
                <th>Caller</th>
                <th>By</th>
                <th>When</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.report_id}>
                  <td className="mono">{r.report_id}</td>
                  <td>{r.incident_type ?? "—"}</td>
                  <td>
                    {r.peak_threat != null ? `${r.peak_threat.toFixed(0)}` : "—"}
                    {r.final_level ? ` · ${r.final_level}` : ""}
                  </td>
                  <td className="mono">{r.caller_number ?? "—"}</td>
                  <td>{r.created_by ?? "—"}</td>
                  <td className="small muted">{fmt(r.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/* --------------------------------------------------------------- audit log */

function AuditLog() {
  const [rows, setRows] = useState<AuditEvent[] | null>(null);

  const load = useCallback(async () => {
    const res = await api.getAudit();
    if (res.ok) setRows(res.data.events);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="card">
      <h2 className="card__title">
        Activity log
        <button className="btn2 btn2--ghost cb-refresh" onClick={load}>
          <RefreshCw size={13} /> Refresh
        </button>
      </h2>
      {rows && rows.length === 0 && <p className="small muted">No activity recorded yet.</p>}
      {rows && rows.length > 0 && (
        <div className="cb-tablewrap">
          <table className="cb-table">
            <thead>
              <tr>
                <th>When</th>
                <th>Actor</th>
                <th>Action</th>
                <th>Target</th>
                <th>Detail</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((e) => (
                <tr key={e.id}>
                  <td className="small muted">{fmt(e.ts)}</td>
                  <td className="mono">{e.actor ?? "—"}</td>
                  <td>
                    <span className="chip" data-tone={toneFor(e.action)}>{e.action}</span>
                  </td>
                  <td className="mono small">{e.target ?? "—"}</td>
                  <td className="small muted">{e.detail ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------- users */

function Users() {
  const [rows, setRows] = useState<AuthUser[] | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("viewer");
  const [msg, setMsg] = useState<string | null>(null);

  const load = useCallback(async () => {
    const res = await api.listUsers();
    if (res.ok) setRows(res.data.users);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const add = async () => {
    setMsg(null);
    const res = await api.createUser(email, password, role);
    if (res.ok) {
      setEmail("");
      setPassword("");
      void load();
    } else {
      setMsg(res.error);
    }
  };

  return (
    <div className="card">
      <h2 className="card__title">Users</h2>
      {rows && (
        <div className="cb-tablewrap">
          <table className="cb-table">
            <thead>
              <tr>
                <th>Email</th>
                <th>Role</th>
                <th>Status</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((u) => (
                <tr key={u.id}>
                  <td className="mono">{u.email}</td>
                  <td>
                    <span className="chip" data-tone={u.role === "admin" ? "ok" : undefined}>
                      {u.role}
                    </span>
                  </td>
                  <td className="small">{u.disabled ? "disabled" : "active"}</td>
                  <td className="small muted">{fmt(u.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="row" style={{ gap: "var(--s-2)", marginTop: "var(--s-4)", flexWrap: "wrap" }}>
        <input
          className="field"
          placeholder="new user email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          style={{ flex: "1 1 180px" }}
        />
        <input
          className="field"
          type="password"
          placeholder="password (min 8)"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          style={{ flex: "1 1 140px" }}
        />
        <select className="field" value={role} onChange={(e) => setRole(e.target.value)}>
          <option value="viewer">viewer</option>
          <option value="analyst">analyst</option>
          <option value="admin">admin</option>
        </select>
        <button className="btn2 btn2--primary" onClick={add}>
          Add user
        </button>
      </div>
      {msg && (
        <div className="banner banner--bad" style={{ marginTop: "var(--s-3)" }}>
          <div className="small">{msg}</div>
        </div>
      )}
    </div>
  );
}

/* ----------------------------------------------------------------- helpers */

function fmt(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

function toneFor(action: string): string | undefined {
  if (action.startsWith("payment.override") || action === "login.failed") return "bad";
  if (action.startsWith("payment")) return "warn";
  if (action === "login" || action === "report.export") return "ok";
  return undefined;
}
