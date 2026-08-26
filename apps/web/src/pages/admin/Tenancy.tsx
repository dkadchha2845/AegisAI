/**
 * Tenant administration — organisations, the audit log, and users.
 *
 * These three panels used to live on **My Reports**, the citizen-facing page
 * whose own lede reads "every investigation you've saved". A person opening it
 * to find a complaint PDF was shown a table of platform tenants and a form for
 * creating user accounts, and `/admin` rendered a second, separate user table
 * with a second add-user form. One audience, one place: the panels moved here,
 * and the duplicate on `/admin` was deleted in favour of these.
 *
 * The role checks below mirror the route gate in App.tsx, which mirrors the
 * check the API already enforces on every `/api/auth/users` and org route.
 * They are UX — do not show someone a door that 403s — not the boundary.
 */

import { useCallback, useEffect, useState } from "react";
import { RefreshCw, UserPlus } from "lucide-react";
import { EmptyState, SkeletonRows } from "@/components/ui/States";
import * as api from "@/lib/api";
import type { AuditEvent, AuthUser } from "@/lib/api";

/* ---------------------------------------------------------- organizations */

export function Organizations() {
  const [rows, setRows] = useState<api.Organization[] | null>(null);
  const [name, setName] = useState("");
  const [msg, setMsg] = useState<string | null>(null);

  const load = useCallback(async () => {
    const res = await api.listOrgs();
    if (res.ok) setRows(res.data.organizations);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const add = async () => {
    setMsg(null);
    if (name.trim().length < 2) {
      setMsg("Enter an organisation name.");
      return;
    }
    const res = await api.createOrg(name.trim());
    if (res.ok) {
      setName("");
      void load();
    } else {
      setMsg(res.error);
    }
  };

  return (
    <div className="card">
      <h2 className="card__title">Organisations</h2>
      <p className="small muted" style={{ marginTop: 0 }}>
        Tenants on this platform. Users, saved cases, and the audit log are scoped
        to one of these; the fraud-intelligence graph is shared across all of them.
      </p>
      {!rows && <SkeletonRows rows={3} cols={5} />}
      {rows && (
        <div className="cb-tablewrap">
          <table className="cb-table">
            <thead>
              <tr><th>Organisation</th><th>Slug</th><th>Members</th><th>Cases</th><th>Created</th></tr>
            </thead>
            <tbody>
              {rows.map((o) => (
                <tr key={o.id}>
                  <td><strong>{o.name}</strong></td>
                  <td className="mono small">{o.slug}</td>
                  <td>{o.members ?? "—"}</td>
                  <td>{o.cases ?? "—"}</td>
                  <td className="small muted">{fmt(o.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <form
        className="adduser"
        onSubmit={(e) => {
          e.preventDefault();
          void add();
        }}
      >
        <div className="adduser__field">
          <label className="fieldlabel" htmlFor="new-org">New organisation</label>
          <input
            id="new-org"
            className="field"
            placeholder="e.g. Delhi Cyber Cell"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>
        <button className="btn2 btn2--primary adduser__go" type="submit">Create organisation</button>
      </form>
      {msg && (
        <div className="alert" data-tone="bad" role="alert" style={{ marginTop: "var(--s-3)" }}>
          <span>{msg}</span>
        </div>
      )}
    </div>
  );
}

/* --------------------------------------------------------------- audit log */

export function AuditLog() {
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
      {!rows && <SkeletonRows rows={4} cols={5} />}
      {rows && rows.length === 0 && (
        <EmptyState
          inline
          title="Nothing recorded yet"
          body="Sign-ins, exports and payment overrides appear here as they happen."
        />
      )}
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

export function Users() {
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
      <h2 className="card__title">
        <UserPlus size={16} aria-hidden="true" /> Users
      </h2>
      {!rows && <SkeletonRows rows={4} cols={6} />}
      {rows && (
        <div className="cb-tablewrap">
          <table className="cb-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Email</th>
                <th>Role</th>
                <th>Org</th>
                <th>Status</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((u) => (
                <tr key={u.id}>
                  <td className="mono small">#{u.id}</td>
                  <td className="mono">{u.email}</td>
                  <td>
                    <span
                      className="chip"
                      data-tone={u.role === "owner" || u.role === "admin" ? "ok" : undefined}
                    >
                      {u.role}
                    </span>
                  </td>
                  <td className="small muted">{u.org_id != null ? `#${u.org_id}` : "—"}</td>
                  <td className="small">{u.disabled ? "disabled" : "active"}</td>
                  <td className="small muted">{fmt(u.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <form
        className="adduser"
        onSubmit={(e) => {
          e.preventDefault();
          void add();
        }}
      >
        <div className="adduser__field">
          <label className="fieldlabel" htmlFor="nu-email">Email</label>
          <input
            id="nu-email"
            className="field"
            type="email"
            required
            placeholder="new.user@org.gov.in"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
        <div className="adduser__field">
          <label className="fieldlabel" htmlFor="nu-pwd">Temporary password</label>
          <input
            id="nu-pwd"
            className="field"
            type="password"
            required
            minLength={8}
            placeholder="At least 8 characters"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        <div className="adduser__field adduser__field--narrow">
          <label className="fieldlabel" htmlFor="nu-role">Role</label>
          <select id="nu-role" className="field" value={role} onChange={(e) => setRole(e.target.value)}>
            <option value="viewer">Viewer</option>
            <option value="analyst">Analyst</option>
            <option value="admin">Admin</option>
          </select>
        </div>
        <button className="btn2 btn2--primary adduser__go" type="submit">
          <UserPlus size={15} aria-hidden="true" /> Add user
        </button>
      </form>
      {msg && (
        <div className="alert" data-tone="bad" role="alert" style={{ marginTop: "var(--s-3)" }}>
          <span>{msg}</span>
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
