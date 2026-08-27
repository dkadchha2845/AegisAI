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
import { Ban, RefreshCw, ShieldCheck, UserPlus } from "lucide-react";
import { EmptyState, SkeletonRows } from "@/components/ui/States";
import * as api from "@/lib/api";
import type { AuditEvent, AuthUser, RoleInfo } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

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
          body="Sign-ins, failed sign-ins, role changes, exports and payment overrides appear here as they happen."
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
                <th>Resource</th>
                <th>From</th>
                <th>Detail</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((e) => (
                <tr key={e.id} data-failed={!e.success || undefined}>
                  <td className="small muted">{fmt(e.ts)}</td>
                  <td className="mono">{e.actor ?? "—"}</td>
                  <td>
                    {/* Failure is a first-class outcome here. A log that only
                        records successes cannot answer the question an audit
                        log is usually opened to answer. */}
                    <span className="chip" data-tone={e.success ? toneFor(e.action) : "bad"}>
                      {e.action}
                      {!e.success && " ✕"}
                    </span>
                  </td>
                  <td className="mono small">
                    {e.resource_type ? (
                      <>
                        {e.resource_type}
                        {e.resource_id ? ` #${e.resource_id}` : ""}
                      </>
                    ) : (
                      e.target ?? "—"
                    )}
                  </td>
                  <td className="mono small faint">{e.ip ?? "—"}</td>
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

/**
 * The roster, and the two things an administrator does to it: provision an
 * account, and change what an existing one can do.
 *
 * **The role list is fetched, not written here.** `/api/auth/roles` returns
 * every role with its description and its grant, so the dropdown cannot drift
 * from `permissions.py` and the admin reading it sees what each role actually
 * means rather than a bare word. §7's "rather than hard-coding role names
 * throughout the frontend", taken literally.
 *
 * **Roles at or above your own are not offered.** The server refuses them
 * (`outranks`), so this is UX — an option that always 403s is a trap — and the
 * refusal is still the server's.
 */
export function Users() {
  const { user: me, can } = useAuth();
  const [rows, setRows] = useState<AuthUser[] | null>(null);
  const [roles, setRoles] = useState<RoleInfo[]>([]);
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("viewer");
  const [msg, setMsg] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);

  const load = useCallback(async () => {
    const res = await api.listUsers();
    if (res.ok) setRows(res.data.users);
  }, []);

  useEffect(() => {
    void load();
    void (async () => {
      const res = await api.listRoles();
      if (res.ok) setRoles(res.data.roles);
    })();
  }, [load]);

  const myRank = roles.find((r) => r.name === me?.role)?.rank ?? 0;
  /** Only roles strictly below the signed-in administrator's own. */
  const grantable = roles.filter((r) => r.rank < myRank);

  useEffect(() => {
    if (grantable.length && !grantable.some((r) => r.name === role)) {
      setRole(grantable[0].name);
    }
  }, [grantable, role]);

  const add = async () => {
    setMsg(null);
    setOk(null);
    const res = await api.createUser({ email, password, role, full_name: fullName });
    if (res.ok) {
      setEmail("");
      setFullName("");
      setPassword("");
      setOk(`${res.data.user.email} created as ${res.data.user.role}.`);
      void load();
    } else {
      setMsg(res.error);
    }
  };

  const change = async (id: number, patch: { role?: string; disabled?: boolean }) => {
    setMsg(null);
    setOk(null);
    const res = await api.updateUser(id, patch);
    if (res.ok) {
      const ended = res.data.sessions_ended ?? 0;
      setOk(
        `${res.data.user.email}: ${res.data.changed.join("; ")}` +
          (ended ? ` — ${ended} session(s) signed out.` : ""),
      );
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
      <p className="small muted" style={{ marginTop: 0 }}>
        Changing a role or disabling an account signs that person out everywhere —
        a demotion that leaves the old session working is not a demotion.
      </p>
      {!rows && <SkeletonRows rows={4} cols={6} />}
      {rows && (
        <div className="cb-tablewrap">
          <table className="cb-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Name</th>
                <th>Email</th>
                <th>Role</th>
                <th>Org</th>
                <th>Last seen</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((u) => {
                const targetRank = roles.find((r) => r.name === u.role)?.rank ?? 0;
                // You cannot act on yourself, or on a peer or a superior. The
                // server enforces all three; this stops the UI offering them.
                const editable =
                  can("ROLE_MANAGE") && u.id !== me?.id && targetRank < myRank;
                return (
                  <tr key={u.id}>
                    <td className="mono small">#{u.id}</td>
                    <td>{u.full_name ?? <span className="faint">—</span>}</td>
                    <td className="mono">{u.email}</td>
                    <td>
                      {editable ? (
                        <select
                          className="field field--inline"
                          value={u.role}
                          aria-label={`Role for ${u.email}`}
                          onChange={(e) => void change(u.id, { role: e.target.value })}
                        >
                          {grantable.map((r) => (
                            <option key={r.name} value={r.name} title={r.description}>
                              {r.name}
                            </option>
                          ))}
                        </select>
                      ) : (
                        <span
                          className="chip"
                          data-tone={u.role === "owner" || u.role === "admin" ? "ok" : undefined}
                        >
                          {u.role}
                        </span>
                      )}
                    </td>
                    <td className="small muted">{u.org_id != null ? `#${u.org_id}` : "—"}</td>
                    <td className="small muted">{fmt(u.last_login_at)}</td>
                    <td className="small">
                      {editable ? (
                        <button
                          className="btn2 btn2--ghost btn2--sm"
                          onClick={() => void change(u.id, { disabled: !u.disabled })}
                        >
                          {u.disabled ? (
                            <>
                              <ShieldCheck size={13} aria-hidden="true" /> Enable
                            </>
                          ) : (
                            <>
                              <Ban size={13} aria-hidden="true" /> Disable
                            </>
                          )}
                        </button>
                      ) : (
                        <span className={u.disabled ? "chip" : "small faint"} data-tone={u.disabled ? "bad" : undefined}>
                          {u.disabled ? "disabled" : "active"}
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
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
          <label className="fieldlabel" htmlFor="nu-name">Full name</label>
          <input
            id="nu-name"
            className="field"
            placeholder="Asha Verma"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
          />
        </div>
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
            minLength={10}
            placeholder="At least 10 characters"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        <div className="adduser__field adduser__field--narrow">
          <label className="fieldlabel" htmlFor="nu-role">Role</label>
          <select id="nu-role" className="field" value={role} onChange={(e) => setRole(e.target.value)}>
            {grantable.map((r) => (
              <option key={r.name} value={r.name} title={r.description}>
                {r.name}
              </option>
            ))}
          </select>
        </div>
        <button className="btn2 btn2--primary adduser__go" type="submit">
          <UserPlus size={15} aria-hidden="true" /> Add user
        </button>
      </form>
      {roles.length > 0 && (
        <p className="small faint" style={{ marginTop: "var(--s-2)" }}>
          {grantable.find((r) => r.name === role)?.description}
        </p>
      )}
      {msg && (
        <div className="alert" data-tone="bad" role="alert" style={{ marginTop: "var(--s-3)" }}>
          <span>{msg}</span>
        </div>
      )}
      {ok && (
        <div className="alert" data-tone="ok" role="status" style={{ marginTop: "var(--s-3)" }}>
          <span>{ok}</span>
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
