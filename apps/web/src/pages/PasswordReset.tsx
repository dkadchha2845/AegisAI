/**
 * Forgot password / reset password — §30.
 *
 * Two screens in one file because they are two halves of one flow and share
 * every piece of chrome.
 *
 * **The request screen tells you nothing about the account.** It shows the same
 * confirmation whether the address has an account or not, because the server
 * answers the same way for both — an endpoint that says "no such user" is an
 * account-existence oracle that needs no password at all to query.
 *
 * **There is no mail transport in this project, and the screen says so.** The
 * honest development story is that the token goes to the API's log, where an
 * operator can read it; `AEGIS_DEV_PASSWORD_RESET=1` additionally returns it in
 * the response for local work, and when it does, this screen renders it inside
 * a clearly-labelled development block rather than pretending an email went
 * out. Nothing here invents a "check your inbox" that could never arrive.
 */

import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ArrowRight, Eye, EyeOff, KeyRound, Lock, Mail, TerminalSquare } from "lucide-react";
import { Logo } from "@/components/brand/Logo";
import { ThreatField } from "@/components/three/ThreatField";
import * as api from "@/lib/api";

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="login">
      <div className="login__bg">
        <ThreatField />
      </div>
      <div className="login__panel">
        <div className="login__content">
          <Link to="/" className="login__brand" data-reveal aria-label="AegisAI home">
            <Logo size={24} />
          </Link>
          {children}
        </div>
      </div>
    </div>
  );
}

export function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState<{ message: string; devToken?: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setError(null);
    setBusy(true);
    const res = await api.forgotPassword(email.trim());
    setBusy(false);
    if (res.ok) setSent({ message: res.data.message, devToken: res.data.dev_token });
    else setError(res.error);
  };

  if (sent) {
    return (
      <Shell>
        <h1 className="login__title">Check your email</h1>
        <p className="login__sub">{sent.message}</p>

        {sent.devToken && (
          <div className="devblock" role="note">
            <p className="devblock__head">
              <TerminalSquare size={14} aria-hidden="true" /> Development mode
            </p>
            <p className="small">
              No mail transport is configured, and{" "}
              <span className="mono">AEGIS_DEV_PASSWORD_RESET</span> is on, so the
              token is shown here instead. This never happens when{" "}
              <span className="mono">AEGIS_AUTH=1</span>.
            </p>
            <code className="devblock__token">{sent.devToken}</code>
            <Link
              className="btn2 btn2--primary"
              to={`/reset-password?token=${encodeURIComponent(sent.devToken)}`}
            >
              Continue to reset <ArrowRight size={15} aria-hidden="true" />
            </Link>
          </div>
        )}

        <p className="login__switch small">
          <Link to="/login">Back to sign in</Link>
        </p>
      </Shell>
    );
  }

  return (
    <Shell>
      <h1 className="login__title">Reset your password</h1>
      <p className="login__sub">
        Enter the email on your account and we'll issue a single-use reset link.
      </p>
      <form
        className="login__form"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <label className="fieldlabel" htmlFor="fp-email">Email</label>
        <div className="login__pwd">
          <Mail size={14} className="login__pwd-lock" aria-hidden="true" />
          <input
            id="fp-email"
            className="field"
            type="email"
            autoComplete="username"
            placeholder="you@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </div>
        {error && (
          <div className="banner banner--bad" role="alert" style={{ marginTop: "var(--s-3)" }}>
            <div className="small">{error}</div>
          </div>
        )}
        <button className="btn2 btn2--primary login__submit" type="submit" disabled={busy}>
          {busy ? "Sending…" : "Send reset link"} <ArrowRight size={15} aria-hidden="true" />
        </button>
      </form>
      <p className="login__switch small">
        Remembered it? <Link to="/login">Sign in</Link>
      </p>
    </Shell>
  );
}

export function ResetPassword() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const tokenFromUrl = params.get("token") ?? "";

  const [token, setToken] = useState(tokenFromUrl);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  useEffect(() => setToken(tokenFromUrl), [tokenFromUrl]);

  const mismatch = useMemo(
    () => confirm.length > 0 && confirm !== password,
    [confirm, password],
  );

  const submit = async () => {
    setError(null);
    if (!token.trim()) return setError("Paste the reset token from your link.");
    if (password !== confirm) return setError("The two passwords don't match.");
    setBusy(true);
    const res = await api.resetPassword(token.trim(), password, confirm);
    setBusy(false);
    if (res.ok) setDone(true);
    else setError(res.error);
  };

  if (done) {
    return (
      <Shell>
        <h1 className="login__title">Password changed</h1>
        <p className="login__sub">
          Every other session on this account has been signed out. Sign in with your
          new password.
        </p>
        <button
          className="btn2 btn2--primary login__submit"
          onClick={() => navigate("/login", { replace: true })}
        >
          Sign in <ArrowRight size={15} aria-hidden="true" />
        </button>
      </Shell>
    );
  }

  return (
    <Shell>
      <h1 className="login__title">Choose a new password</h1>
      <p className="login__sub">
        Reset links are single use and expire — if this one has, request another.
      </p>
      <form
        className="login__form"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        {!tokenFromUrl && (
          <>
            <label className="fieldlabel" htmlFor="rp-token">Reset token</label>
            <div className="login__pwd">
              <KeyRound size={14} className="login__pwd-lock" aria-hidden="true" />
              <input
                id="rp-token"
                className="field mono"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                placeholder="Paste it from your reset link"
                required
              />
            </div>
          </>
        )}

        <label className="fieldlabel" htmlFor="rp-pw">New password</label>
        <div className="login__pwd">
          <Lock size={14} className="login__pwd-lock" aria-hidden="true" />
          <input
            id="rp-pw"
            className="field"
            type={showPw ? "text" : "password"}
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="At least 10 characters"
            required
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

        <label className="fieldlabel" htmlFor="rp-confirm">Confirm new password</label>
        <div className="login__pwd">
          <Lock size={14} className="login__pwd-lock" aria-hidden="true" />
          <input
            id="rp-confirm"
            className="field"
            type={showPw ? "text" : "password"}
            autoComplete="new-password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            aria-invalid={mismatch || undefined}
            required
          />
        </div>

        {(error || mismatch) && (
          <div className="banner banner--bad" role="alert" style={{ marginTop: "var(--s-3)" }}>
            <div className="small">{error ?? "The two passwords don't match."}</div>
          </div>
        )}

        <button className="btn2 btn2--primary login__submit" type="submit" disabled={busy}>
          {busy ? "Saving…" : "Set new password"} <ArrowRight size={15} aria-hidden="true" />
        </button>
      </form>
      <p className="login__switch small">
        <Link to="/forgot-password">Request a new link</Link> ·{" "}
        <Link to="/login">Sign in</Link>
      </p>
    </Shell>
  );
}
