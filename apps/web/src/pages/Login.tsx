/**
 * Login — the dedicated authentication screen and the gate into the console.
 *
 * The server runs open by default (the demo needs no *provisioning*), but the
 * client still gates the console behind a deliberate sign-in, so this screen is
 * the real doorway rather than a formality. It works in two modes and says which
 * it is in: when enforcement is off it offers a one-tap continue-as-owner plus a
 * role switcher (so RBAC is demonstrable); when enforcement is on it simply gates.
 * Either way a successful sign-in mints a token, updates the whole app, and
 * returns the user to wherever they were headed.
 *
 * Visually it shares the landing's WebGL backdrop and adds an entrance animation
 * and a 3D tilt on the card, so the product feels like one thing from the first
 * screen rather than a login bolted onto an app.
 */

import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { ArrowRight, Lock, ShieldCheck, User } from "lucide-react";
import { ThreatField } from "@/components/three/ThreatField";
import { useAuth } from "@/context/AuthContext";
import { useTilt } from "@/hooks/useTilt";
import { gsap, prefersReducedMotion } from "@/lib/gsap";

/** The seeded demo roster — one per role, so a judge can watch access change. */
const DEMO_ACCOUNTS: { role: string; email: string; blurb: string }[] = [
  { role: "owner", email: "admin@kavach.local", blurb: "Platform owner — every org, user management" },
  { role: "admin", email: "supervisor@kavach.local", blurb: "Org admin — users + audit log for their cell" },
  { role: "analyst", email: "analyst@kavach.local", blurb: "Analyst — save & read cases, no user admin" },
  { role: "viewer", email: "viewer@kavach.local", blurb: "Viewer — read-only" },
];
const DEMO_PASSWORD = "changeme";

export function Login() {
  const auth = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? "/dashboard";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const panelRef = useTilt<HTMLDivElement>({ max: 5, lift: 4 });
  const contentRef = useRef<HTMLDivElement>(null);

  // Already signed in and somehow back on /login → skip straight in.
  useEffect(() => {
    if (auth.authed && !auth.loading) navigate(from, { replace: true });
  }, [auth.authed, auth.loading, from, navigate]);

  useEffect(() => {
    if (prefersReducedMotion || !contentRef.current) return;
    const ctx = gsap.context(() => {
      gsap.from("[data-login-reveal]", {
        opacity: 0,
        y: 18,
        duration: 0.7,
        ease: "power3.out",
        stagger: 0.06,
      });
    }, contentRef);
    return () => ctx.revert();
  }, []);

  const go = (res: { ok: boolean; error?: string }) => {
    setBusy(false);
    if (res.ok) navigate(from, { replace: true });
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
    setBusy(true);
    setError(null);
    setEmail(acctEmail);
    setPassword(DEMO_PASSWORD);
    go(await auth.login(acctEmail, DEMO_PASSWORD));
  };

  return (
    <div className="login">
      <div className="login__bg">
        <ThreatField />
      </div>
      <div className="login__panel" ref={panelRef}>
        <div ref={contentRef} className="login__content">
          <div className="login__brand" data-login-reveal>
            <span className="brand2__mark" aria-hidden="true" />
            <span className="login__brandname">KAVACH</span>
          </div>
          <h1 className="login__title" data-login-reveal>Sign in to the console</h1>
          <p className="login__sub" data-login-reveal>
            Access the analyst tools, fraud intelligence, and case book.
          </p>

          {!auth.enforced && (
            <div className="login__note" data-login-reveal>
              <ShieldCheck size={15} />
              <div>
                <strong>Open demo mode.</strong> Pick a role below to see access
                control in action, or sign in with{" "}
                <span className="mono">admin@kavach.local</span> /{" "}
                <span className="mono">changeme</span>.
              </div>
            </div>
          )}

          {!auth.enforced && (
            <div className="login__roles" data-login-reveal>
              {DEMO_ACCOUNTS.map((a) => (
                <button
                  key={a.email}
                  className="login__role"
                  onClick={() => signInAs(a.email)}
                  disabled={busy}
                  title={a.blurb}
                >
                  <User size={13} />
                  <span className="login__rolename">{a.role}</span>
                  <span className="login__rolemail mono">{a.email}</span>
                </button>
              ))}
            </div>
          )}

          <label className="fieldlabel" data-login-reveal>Email</label>
          <input
            className="field"
            data-login-reveal
            type="email"
            autoComplete="username"
            placeholder="you@agency.gov.in"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit()}
          />
          <label className="fieldlabel" data-login-reveal style={{ marginTop: "var(--s-3)" }}>
            Password
          </label>
          <div className="login__pwd" data-login-reveal>
            <Lock size={14} />
            <input
              className="field"
              type="password"
              autoComplete="current-password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && submit()}
            />
          </div>

          {error && (
            <div className="banner banner--bad" style={{ marginTop: "var(--s-3)" }}>
              <div className="small">{error}</div>
            </div>
          )}

          <button
            className="btn2 btn2--primary login__submit"
            data-login-reveal
            onClick={submit}
            disabled={busy}
          >
            {busy ? "Signing in…" : "Sign in"} <ArrowRight size={15} />
          </button>

          {!auth.enforced && (
            <button
              className="btn2 btn2--ghost login__skip"
              data-login-reveal
              onClick={async () => {
                setBusy(true);
                setError(null);
                go(await auth.continueAsDemo());
              }}
              disabled={busy}
            >
              Continue as owner →
            </button>
          )}

          <p className="login__foot small faint" data-login-reveal>
            Citizens don't need an account — the{" "}
            <a href="/shield">fraud shield</a> is open to everyone.
          </p>
        </div>
      </div>
    </div>
  );
}
