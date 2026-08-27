/**
 * Sign in — the doorway into the product.
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
 * Visually it shares the landing's WebGL backdrop and the same brand lockup as
 * the sign-up screen beside it, so the auth flow reads as part of AegisAI
 * rather than a template bolted on.
 */

import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { ArrowRight, Eye, EyeOff, Lock, Mail, ShieldCheck, UserRound } from "lucide-react";
import { Logo } from "@/components/brand/Logo";
import { ThreatField } from "@/components/three/ThreatField";
import { useAuth } from "@/context/AuthContext";
import { useTilt } from "@/hooks/useTilt";
import * as api from "@/lib/api";
import type { DemoAccount } from "@/lib/api";

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

  const panelRef = useTilt<HTMLDivElement>({ max: 5, lift: 4 });

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

  // Entrance motion is a pure CSS keyframe (see .login__content [data-reveal]),
  // not a GSAP tween. That is deliberate for the one screen you cannot afford to
  // leave half-rendered: the browser's animation engine always drives a keyframe
  // to completion, so — unlike a JS tween whose ticker sleeps when the tab is
  // backgrounded — the fields can never freeze at opacity 0 with no way in.

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

  return (
    <div className="login">
      <div className="login__bg">
        <ThreatField />
      </div>
      <div className="login__panel" ref={panelRef}>
        <div className="login__content">
          <Link to="/" className="login__brand" data-reveal aria-label="AegisAI home">
            <Logo size={24} />
          </Link>
          <h1 className="login__title" data-reveal>Sign in</h1>
          <p className="login__sub" data-reveal>
            Your investigations, your reports, and the tools your role gives you.
          </p>

          {demo.accounts.length > 0 && (
            <>
              <div className="login__note" data-reveal>
                <ShieldCheck size={15} />
                <div>
                  <strong>Open demo mode.</strong> Pick a role to see access control
                  in action — each one lands somewhere different and can do
                  different things.
                </div>
              </div>

              <div className="login__roles" data-reveal>
                {demo.accounts.map((a) => (
                  <button
                    key={a.email}
                    type="button"
                    className="login__role"
                    onClick={() => signInAs(a.email)}
                    disabled={busy}
                    title={`${a.description} — ${a.org}`}
                  >
                    <UserRound size={13} aria-hidden="true" />
                    <span className="login__rolename">{a.role}</span>
                    <span className="login__rolemail mono">{a.email}</span>
                  </button>
                ))}
              </div>
            </>
          )}

          <form
            className="login__form"
            onSubmit={(e) => {
              e.preventDefault();
              void submit();
            }}
          >
            <label className="fieldlabel" htmlFor="login-email" data-reveal>Email</label>
            <div className="login__pwd" data-reveal>
              <Mail size={14} className="login__pwd-lock" aria-hidden="true" />
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

            <div className="login__pwdrow" data-reveal>
              <label className="fieldlabel" htmlFor="login-password">Password</label>
              <Link className="login__forgot" to="/forgot-password">
                Forgot password?
              </Link>
            </div>
            <div className="login__pwd" data-reveal>
              <Lock size={14} className="login__pwd-lock" aria-hidden="true" />
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
                className="login__pwd-toggle"
                onClick={() => setShowPw((v) => !v)}
                aria-label={showPw ? "Hide password" : "Show password"}
                aria-pressed={showPw}
                tabIndex={-1}
              >
                {showPw ? <EyeOff size={15} /> : <Eye size={15} />}
              </button>
            </div>

            {error && (
              <div className="banner banner--bad" role="alert" style={{ marginTop: "var(--s-3)" }}>
                <div className="small">{error}</div>
              </div>
            )}

            <button
              className="btn2 btn2--primary login__submit"
              data-reveal
              type="submit"
              disabled={busy}
            >
              {busy ? "Signing in…" : "Sign in"} <ArrowRight size={15} aria-hidden="true" />
            </button>
          </form>

          {auth.status?.signup_enabled !== false && (
            <p className="login__switch small" data-reveal>
              Don't have an account? <Link to="/signup">Create one</Link>
            </p>
          )}

          <p className="login__foot small faint" data-reveal>
            Fraud in progress? Call <strong className="mono">1930</strong> — you don't
            need an account for that.
          </p>
        </div>
      </div>
    </div>
  );
}
