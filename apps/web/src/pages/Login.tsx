/**
 * Sign in — the doorway into the product. §32.
 *
 * The server runs open by default (the demo needs no *provisioning*), but the
 * client still gates everything behind a deliberate sign-in, so this screen is
 * the real doorway rather than a formality. It works in two modes and says
 * which it is in: when enforcement is off it offers a role switcher, so a judge
 * can watch access control change between one account and the next; when
 * enforcement is on it simply gates, and the switcher is not merely hidden —
 * `/api/auth/demo-accounts` returns nothing, because a deployment that enforces
 * auth must not have an endpoint that advertises credentials.
 *
 * **The demo roster is fetched, not written here.** It used to be a literal
 * array of four emails in this file, which is a second copy of the seed that
 * drifts the first time someone adds an account — and §43's "do not hard-code
 * users in React", read narrowly. The list, the password and whether to show
 * either all come from the server.
 *
 * Layout and chrome are `AuthShell`, shared with sign-up and the reset screens.
 */

import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { ArrowRight, Eye, EyeOff, Lock, Mail, ShieldCheck, Users } from "lucide-react";
import { AuthShell } from "@/components/layout/AuthShell";
import { useAuth } from "@/context/AuthContext";
import * as api from "@/lib/api";
import type { DemoAccount } from "@/lib/api";

/** What is behind the door, for the brand column. Deliberately about the work
 *  rather than the product — someone reaching this screen already knows what
 *  AegisAI is; what they want to know is what they get for signing in. */
const BEHIND_THE_DOOR = [
  {
    title: "Your investigations, kept",
    body: "Everything you submit stays readable to you — and to the investigators authorised to work it, and to nobody else.",
  },
  {
    title: "Evidence you can hand over",
    body: "A saved case exports as the same package a cybercrime complaint needs, with every signal that moved the number named.",
  },
  {
    title: "The tools your role gives you",
    body: "A citizen gets their own case book. An investigator gets the fraud graph, the live console and the intervention tools.",
  },
];

export function Login() {
  const auth = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? null;

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [demo, setDemo] = useState<{ password: string | null; accounts: DemoAccount[] }>({
    password: null,
    accounts: [],
  });

  // Already signed in and somehow back on /login → skip straight in, to the
  // page they were headed for or to their own role's dashboard.
  useEffect(() => {
    if (auth.authed && !auth.loading) navigate(from ?? auth.home, { replace: true });
  }, [auth.authed, auth.loading, auth.home, from, navigate]);

  useEffect(() => {
    void (async () => {
      const res = await api.listDemoAccounts();
      if (res.ok && res.data.open_mode) {
        setDemo({ password: res.data.password, accounts: res.data.accounts });
      }
    })();
  }, []);

  const go = (res: { ok: boolean; error?: string; home?: string }) => {
    setBusy(false);
    if (res.ok) navigate(from ?? res.home ?? auth.home, { replace: true });
    else setError(res.error ?? "Sign-in failed");
  };

  const submit = async () => {
    if (!email.trim() || !password) {
      setError("Enter your email and password.");
      return;
    }
    setBusy(true);
    setError(null);
    go(await auth.login(email.trim(), password));
  };

  const signInAs = async (acctEmail: string) => {
    if (!demo.password) return;
    setBusy(true);
    setError(null);
    setEmail(acctEmail);
    setPassword(demo.password);
    go(await auth.login(acctEmail, demo.password));
  };

  const aside = (
    <>
      <h2 className="auth__pitch">
        Welcome back.
      </h2>
      <ul className="auth__points">
        {BEHIND_THE_DOOR.map((p) => (
          <li key={p.title}>
            <ShieldCheck size={16} aria-hidden="true" />
            <span>
              <strong>{p.title}.</strong> {p.body}
            </span>
          </li>
        ))}
      </ul>
      <p className="auth__note small faint">
        Fraud in progress? Call <strong className="mono">1930</strong> — you don't
        need an account for that.
      </p>
    </>
  );

  return (
    <AuthShell
      aside={aside}
      title="Sign in"
      lede="Your investigations, your reports, and the tools your role gives you."
      footer={
        auth.status?.signup_enabled !== false ? (
          <p className="auth__switch small">
            Don't have an account? <Link to="/signup">Create one</Link>
          </p>
        ) : undefined
      }
    >
      {demo.accounts.length > 0 && (
        <div className="auth__demo" data-reveal>
          <div className="auth__notice">
            <ShieldCheck size={15} aria-hidden="true" />
            <div>
              <strong>Open demo mode.</strong> Pick a role to watch access control
              work — each one lands somewhere different and can do different things.
            </div>
          </div>

          <p className="label" style={{ marginBottom: "var(--s-2)" }}>
            <Users size={12} aria-hidden="true" style={{ verticalAlign: "-1px" }} /> Demo
            accounts
          </p>
          <div className="auth__roles">
            {demo.accounts.map((a) => (
              <button
                key={a.email}
                type="button"
                className="auth__role"
                onClick={() => signInAs(a.email)}
                disabled={busy}
                title={`${a.description} — ${a.org}`}
              >
                <span className="auth__rolename">{a.role}</span>
                <span className="auth__rolemail mono">{a.email}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      <form
        className="auth__form"
        data-reveal
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <label className="fieldlabel" htmlFor="login-email">Email</label>
        <div className="auth__field">
          <Mail size={15} className="auth__fieldicon" aria-hidden="true" />
          <input
            id="login-email"
            className="field"
            type="email"
            autoComplete="username"
            placeholder="you@agency.gov.in"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>

        <div className="auth__pwdrow">
          <label className="fieldlabel" htmlFor="login-password">Password</label>
          <Link className="auth__forgot" to="/forgot-password">
            Forgot password?
          </Link>
        </div>
        <div className="auth__field auth__field--toggle">
          <Lock size={15} className="auth__fieldicon" aria-hidden="true" />
          <input
            id="login-password"
            className="field"
            type={showPw ? "text" : "password"}
            autoComplete="current-password"
            placeholder="••••••••"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <button
            type="button"
            className="auth__reveal"
            onClick={() => setShowPw((v) => !v)}
            aria-label={showPw ? "Hide password" : "Show password"}
            aria-pressed={showPw}
            tabIndex={-1}
          >
            {showPw ? <EyeOff size={15} /> : <Eye size={15} />}
          </button>
        </div>

        {error && (
          <div className="banner banner--bad" role="alert" style={{ marginTop: "var(--s-4)" }}>
            <div className="small">{error}</div>
          </div>
        )}

        <button className="btn2 btn2--primary auth__submit" type="submit" disabled={busy}>
          {busy ? "Signing in…" : "Sign in"} <ArrowRight size={15} aria-hidden="true" />
        </button>
      </form>
    </AuthShell>
  );
}
