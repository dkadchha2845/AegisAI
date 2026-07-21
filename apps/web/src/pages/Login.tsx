/**
 * Login — the dedicated authentication screen.
 *
 * The server runs open by default (the demo needs no login), so this screen is
 * usable in two modes and says which one it is in: when enforcement is off it
 * explains that and offers a one-tap continue-as-admin; when enforcement is on it
 * gates the platform. Either way it wires straight to AuthContext, so a
 * successful login updates the whole app and redirects back to wherever the user
 * was headed.
 *
 * Visually it shares the landing's WebGL backdrop so the product feels like one
 * thing from the first screen, not a login bolted onto an app.
 */

import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { ArrowRight, Lock, ShieldCheck } from "lucide-react";
import { ThreatField } from "@/components/three/ThreatField";
import { useAuth } from "@/context/AuthContext";

export function Login() {
  const auth = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? "/dashboard";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!email.trim() || !password) {
      setError("Enter your email and password.");
      return;
    }
    setBusy(true);
    setError(null);
    const res = await auth.login(email.trim(), password);
    setBusy(false);
    if (res.ok) navigate(from, { replace: true });
    else setError(res.error ?? "Login failed");
  };

  return (
    <div className="login">
      <div className="login__bg">
        <ThreatField />
      </div>
      <div className="login__panel">
        <div className="login__brand">
          <span className="brand2__mark" aria-hidden="true" />
          <span className="login__brandname">KAVACH</span>
        </div>
        <h1 className="login__title">Sign in to the console</h1>
        <p className="login__sub">
          Access the analyst tools, fraud intelligence, and case book.
        </p>

        {!auth.enforced && (
          <div className="login__note">
            <ShieldCheck size={15} />
            <div>
              <strong>Open demo mode.</strong> Authentication is not enforced on
              this server — you can continue straight to the console, or sign in
              with the seeded admin (<span className="mono">admin@kavach.local</span> /{" "}
              <span className="mono">changeme</span>).
            </div>
          </div>
        )}

        <label className="fieldlabel">Email</label>
        <input
          className="field"
          type="email"
          autoComplete="username"
          placeholder="you@agency.gov.in"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
        />
        <label className="fieldlabel" style={{ marginTop: "var(--s-3)" }}>Password</label>
        <div className="login__pwd">
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

        <button className="btn2 btn2--primary login__submit" onClick={submit} disabled={busy}>
          {busy ? "Signing in…" : "Sign in"} <ArrowRight size={15} />
        </button>

        {!auth.enforced && (
          <button className="btn2 btn2--ghost login__skip" onClick={() => navigate(from, { replace: true })}>
            Continue to the console →
          </button>
        )}

        <p className="login__foot small faint">
          Citizens don't need an account — the{" "}
          <a href="/shield">fraud shield</a> is open to everyone.
        </p>
      </div>
    </div>
  );
}
