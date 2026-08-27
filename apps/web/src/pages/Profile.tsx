/**
 * Profile — the account, and the settings that actually do something.
 *
 * **There are no invented settings.** The obvious way to fill a settings page
 * is eight sections of plausible-looking toggles — notifications, AI
 * preferences, API keys — and every one of them would be a control that changes
 * nothing. A switch that does not switch anything is a lie told in the
 * interface, and the same rule that keeps unmeasured latency out of the copy
 * keeps decorative toggles out of here. Every control below is wired to real
 * behaviour; the sections that are statements of fact are written as statements
 * of fact.
 *
 * What the account section can and cannot change is itself a security decision.
 * **Name and phone, and nothing else.** Not the role, not the organisation, not
 * whether the account is enabled — those are the fields whose self-service edit
 * would be a privilege escalation, and they are absent from the request the
 * client can even construct (`PATCH /api/auth/me` has no such fields), not
 * merely disabled in the markup.
 *
 * The sessions list is the visible half of revocable sessions: signing out
 * everywhere is only a considered action if you can see what you are signing
 * out of.
 */

import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Check,
  KeyRound,
  LogIn,
  LogOut,
  Monitor,
  Moon,
  ShieldCheck,
  Sun,
  Zap,
} from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { SkeletonRows } from "@/components/ui/States";
import { useAuth } from "@/context/AuthContext";
import { useTheme } from "@/context/ThemeContext";
import { useMotionPreference } from "@/hooks/useMotionPreference";
import * as api from "@/lib/api";
import type { UserSession } from "@/lib/api";

export function Profile() {
  const { user, org, authed, logout, apply, status } = useAuth();
  const { theme, toggle } = useTheme();
  const motion = useMotionPreference();

  return (
    <div className="page page--doc">
      <PageHeader
        title="Profile"
        lede="Your account, how AegisAI looks and moves, and what it does with what you give it."
      />

      {/* --- Account --------------------------------------------------- */}
      <section className="card">
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
              {user.last_login_at && (
                <>
                  <dt>Last signed in</dt>
                  <dd>{fmt(user.last_login_at)}</dd>
                </>
              )}
            </dl>
            <ProfileForm
              initialName={user.full_name ?? ""}
              initialPhone={user.phone ?? ""}
              onSaved={apply}
            />
            <button
              className="btn2"
              style={{ marginTop: "var(--s-4)" }}
              onClick={() => void logout()}
            >
              <LogOut size={14} aria-hidden="true" /> Sign out
            </button>
          </>
        ) : (
          <>
            <p className="small muted" style={{ marginTop: 0 }}>
              You don't need an account to check something or to get help. Sign in
              to keep your investigations, or create one in a minute.
            </p>
            <div className="row" style={{ gap: "var(--s-2)" }}>
              <Link className="btn2 btn2--primary" to="/login">
                <LogIn size={14} aria-hidden="true" /> Sign in
              </Link>
              <Link className="btn2" to="/signup">
                Create an account
              </Link>
            </div>
          </>
        )}
      </section>

      {authed && user && <PasswordSection minLength={status?.min_password_length ?? 10} />}
      {authed && user && <SessionsSection />}

      {/* --- Appearance ------------------------------------------------- */}
      <section className="card" id="settings">
        <h2 className="card__title">Appearance</h2>

        <div className="setting">
          <div className="setting__text">
            <strong className="setting__name">Theme</strong>
            <p className="setting__desc">
              Dark is the default: the threat scale was designed against a near-black
              ground. Light exists for a bright room, which is a real failure mode, not
              a preference.
            </p>
          </div>
          <button
            className="btn2 setting__control"
            onClick={toggle}
            aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
          >
            {theme === "dark" ? <Sun size={15} aria-hidden="true" /> : <Moon size={15} aria-hidden="true" />}
            {theme === "dark" ? "Dark" : "Light"}
          </button>
        </div>

        <div className="setting">
          <div className="setting__text">
            <strong className="setting__name">Motion</strong>
            <p className="setting__desc">
              {motion.systemPrefersReduced
                ? "Your device asks for reduced motion, so animation is already off. You can override that here."
                : "Entrances and transitions. Turning this off leaves every reading and every control exactly where it is — motion is never how this interface says something."}
            </p>
          </div>
          <div className="segmented setting__control" role="radiogroup" aria-label="Motion">
            {(["system", "full", "reduced"] as const).map((value) => (
              <button
                key={value}
                role="radio"
                aria-checked={motion.preference === value}
                className="tab"
                data-active={motion.preference === value || undefined}
                onClick={() => motion.set(value)}
              >
                {value === "system" ? <Monitor size={13} aria-hidden="true" /> : null}
                {value === "full" ? <Zap size={13} aria-hidden="true" /> : null}
                {value === "system" ? "System" : value === "full" ? "Full" : "Reduced"}
              </button>
            ))}
          </div>
        </div>
      </section>

      {/* --- Privacy & data ---------------------------------------------
          Statements, not switches. Everything here is behaviour the system
          already has; a toggle beside any of it would be decoration. */}
      <section className="card">
        <h2 className="card__title">
          <ShieldCheck size={16} aria-hidden="true" /> Privacy and your data
        </h2>
        <ul className="factlist">
          <li>
            <strong>Live audio is transcribed on your device.</strong> Live Protection uses
            your browser's speech recognition; the audio itself is never uploaded.
          </li>
          <li>
            <strong>A check is not stored unless you save it.</strong> Paste something into
            Analyze and it is analysed and forgotten. Preserving it is a deliberate action
            that puts it in My Reports.
          </li>
          <li>
            <strong>Your investigations are yours.</strong> A case you open is readable by
            you and by the investigators your organisation authorises — not by other
            people who happen to have accounts.
          </li>
          <li>
            <strong>Your password is stored only as a hash.</strong>{" "}
            {status?.password_hash ? (
              <>
                This deployment hashes with <span className="mono">{status.password_hash}</span>.
              </>
            ) : null}{" "}
            Nobody, including an administrator, can read it back.
          </li>
          <li>
            <strong>Text pulled out of a screenshot is data, never instructions.</strong> It is
            quoted into the models as untrusted input, so a message that tells the system
            what to do is treated as a message that tells the system what to do.
          </li>
          <li>
            <strong>You can erase a case at any time.</strong> Erasure removes the rows and
            the stored bytes of every artefact. An audit entry recording that you erased it
            is kept.
          </li>
        </ul>
      </section>
    </div>
  );
}

/* ------------------------------------------------------------------ profile */

function ProfileForm({
  initialName,
  initialPhone,
  onSaved,
}: {
  initialName: string;
  initialPhone: string;
  onSaved: (s: api.SessionResponse) => void;
}) {
  const [name, setName] = useState(initialName);
  const [phone, setPhone] = useState(initialPhone);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const dirty = name !== initialName || phone !== initialPhone;

  const save = async () => {
    setBusy(true);
    setError(null);
    setSaved(false);
    const res = await api.updateMe({ full_name: name.trim(), phone: phone.trim() });
    setBusy(false);
    if (res.ok) {
      onSaved(res.data);
      setSaved(true);
    } else {
      setError(res.error);
    }
  };

  return (
    <form
      className="adduser"
      style={{ marginTop: "var(--s-4)" }}
      onSubmit={(e) => {
        e.preventDefault();
        void save();
      }}
    >
      <div className="adduser__field">
        <label className="fieldlabel" htmlFor="pf-name">Full name</label>
        <input
          id="pf-name"
          className="field"
          value={name}
          onChange={(e) => {
            setName(e.target.value);
            setSaved(false);
          }}
          minLength={2}
        />
      </div>
      <div className="adduser__field">
        <label className="fieldlabel" htmlFor="pf-phone">Phone</label>
        <input
          id="pf-phone"
          className="field"
          type="tel"
          value={phone}
          onChange={(e) => {
            setPhone(e.target.value);
            setSaved(false);
          }}
          placeholder="+91 98765 43210"
        />
      </div>
      <button className="btn2 adduser__go" type="submit" disabled={busy || !dirty}>
        {saved ? (
          <>
            <Check size={14} aria-hidden="true" /> Saved
          </>
        ) : busy ? (
          "Saving…"
        ) : (
          "Save"
        )}
      </button>
      {error && (
        <div className="alert" data-tone="bad" role="alert" style={{ gridColumn: "1 / -1" }}>
          <span>{error}</span>
        </div>
      )}
    </form>
  );
}

/* ----------------------------------------------------------------- password */

function PasswordSection({ minLength }: { minLength: number }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);

  const submit = async () => {
    setResult(null);
    if (next !== confirm) {
      setResult({ ok: false, text: "The two new passwords don't match." });
      return;
    }
    setBusy(true);
    const res = await api.changePassword(current, next, confirm);
    setBusy(false);
    if (res.ok) {
      setCurrent("");
      setNext("");
      setConfirm("");
      setResult({
        ok: true,
        text:
          res.data.other_sessions_ended > 0
            ? `Password changed. ${res.data.other_sessions_ended} other session(s) were signed out.`
            : "Password changed.",
      });
    } else {
      setResult({ ok: false, text: res.error });
    }
  };

  return (
    <section className="card">
      <h2 className="card__title">
        <KeyRound size={16} aria-hidden="true" /> Password
      </h2>
      <p className="small muted" style={{ marginTop: 0 }}>
        At least {minLength} characters. Changing it signs out every other session
        on this account — a password change that leaves a stolen session working
        has not recovered anything.
      </p>
      <form
        className="adduser"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <div className="adduser__field">
          <label className="fieldlabel" htmlFor="pw-current">Current password</label>
          <input
            id="pw-current"
            className="field"
            type="password"
            autoComplete="current-password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            required
          />
        </div>
        <div className="adduser__field">
          <label className="fieldlabel" htmlFor="pw-new">New password</label>
          <input
            id="pw-new"
            className="field"
            type="password"
            autoComplete="new-password"
            minLength={minLength}
            value={next}
            onChange={(e) => setNext(e.target.value)}
            required
          />
        </div>
        <div className="adduser__field">
          <label className="fieldlabel" htmlFor="pw-confirm">Confirm new password</label>
          <input
            id="pw-confirm"
            className="field"
            type="password"
            autoComplete="new-password"
            minLength={minLength}
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            required
          />
        </div>
        <button className="btn2 btn2--primary adduser__go" type="submit" disabled={busy}>
          {busy ? "Changing…" : "Change password"}
        </button>
      </form>
      {result && (
        <div
          className="alert"
          data-tone={result.ok ? "ok" : "bad"}
          role={result.ok ? "status" : "alert"}
          style={{ marginTop: "var(--s-3)" }}
        >
          <span>{result.text}</span>
        </div>
      )}
    </section>
  );
}

/* ----------------------------------------------------------------- sessions */

function SessionsSection() {
  const [rows, setRows] = useState<UserSession[] | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const load = useCallback(async () => {
    const res = await api.listMySessions();
    if (res.ok) setRows(res.data.sessions);
    else setRows([]);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const signOutAll = async () => {
    const res = await api.signOutEverywhere();
    if (res.ok) {
      setMsg(
        res.data.revoked === 0
          ? "There were no other sessions to sign out."
          : `Signed out of ${res.data.revoked} other session(s).`,
      );
      void load();
    } else {
      setMsg(res.error);
    }
  };

  return (
    <section className="card">
      <h2 className="card__title">Active sessions</h2>
      <p className="small muted" style={{ marginTop: 0 }}>
        Every device currently signed in to this account. Signing out everywhere
        ends them all except this one.
      </p>
      {!rows && <SkeletonRows rows={2} cols={3} />}
      {rows && rows.length === 0 && (
        <p className="small faint">
          No server-side sessions — this deployment is running in open demo mode.
        </p>
      )}
      {rows && rows.length > 0 && (
        <div className="cb-tablewrap">
          <table className="cb-table">
            <thead>
              <tr>
                <th>Started</th>
                <th>Last used</th>
                <th>From</th>
                <th>Device</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((s) => (
                <tr key={s.id}>
                  <td className="small muted">{fmt(s.created_at)}</td>
                  <td className="small muted">{fmt(s.last_seen_at)}</td>
                  <td className="mono small">{s.ip ?? "—"}</td>
                  <td className="small muted">{shortUa(s.user_agent)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {rows && rows.length > 0 && (
        <button className="btn2" style={{ marginTop: "var(--s-3)" }} onClick={() => void signOutAll()}>
          <LogOut size={14} aria-hidden="true" /> Sign out everywhere else
        </button>
      )}
      {msg && (
        <div className="alert" data-tone="ok" role="status" style={{ marginTop: "var(--s-3)" }}>
          <span>{msg}</span>
        </div>
      )}
    </section>
  );
}

/* ------------------------------------------------------------------ helpers */

function fmt(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

/** A user agent is long and attacker-controlled. Show the browser and platform
 *  a person would recognise, and nothing they would have to parse. */
function shortUa(ua: string | null): string {
  if (!ua) return "—";
  const browser =
    /Firefox\/[\d.]+/.exec(ua)?.[0] ??
    /Edg\/[\d.]+/.exec(ua)?.[0] ??
    /Chrome\/[\d.]+/.exec(ua)?.[0] ??
    /Safari\/[\d.]+/.exec(ua)?.[0] ??
    ua.slice(0, 32);
  const platform = /\(([^;)]+)/.exec(ua)?.[1] ?? "";
  return platform ? `${browser.split("/")[0]} · ${platform}` : browser.split("/")[0];
}
