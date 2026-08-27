/**
 * Create an account — §31.
 *
 * **There is no role picker, and that is the feature.** §19 is explicit that a
 * dropdown offering ADMIN is the vulnerability rather than the convenience; the
 * server creates a citizen and ignores anything else, so the form has nothing
 * to offer and nothing to have to safely discard. The copy says so out loud
 * rather than leaving a visitor to wonder where the "I'm a police officer"
 * option went.
 *
 * **Validation is advisory here and enforced there.** The strength meter and
 * the match check exist so a person finds out before they submit; the same
 * rules run in `auth.password_problem` on the server, which is the one that
 * counts. The meter deliberately scores *length first* — a composition rule
 * ("one symbol!") measurably pushes people toward `Passw0rd!`, and length is
 * the property that actually resists a guess.
 *
 * The layout is the two-column form §31 asks for: brand and argument on the
 * left, the form on the right, collapsing to one column on a phone.
 */

import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  ArrowRight,
  Check,
  Eye,
  EyeOff,
  Lock,
  Mail,
  Phone,
  ShieldCheck,
  UserRound,
  X,
} from "lucide-react";
import { Logo, LogoMark } from "@/components/brand/Logo";
import { ThreatField } from "@/components/three/ThreatField";
import { useAuth } from "@/context/AuthContext";

/** Mirrors `auth.password_problem` closely enough to be useful, and is not
 *  trusted by anything: the server re-runs every one of these. */
function strength(password: string, email: string, name: string) {
  const local = email.split("@")[0].toLowerCase();
  const lowered = password.toLowerCase();
  const checks = [
    { label: "At least 10 characters", ok: password.length >= 10 },
    { label: "At least 5 different characters", ok: new Set(password).size >= 5 },
    {
      label: "Doesn't contain your name or email",
      ok:
        !(local.length >= 4 && lowered.includes(local)) &&
        !name
          .toLowerCase()
          .split(/\s+/)
          .some((p) => p.length >= 4 && lowered.includes(p)),
    },
  ];
  const passed = checks.filter((c) => c.ok).length;
  return {
    checks,
    score: password ? passed / checks.length : 0,
    label: !password
      ? ""
      : passed === checks.length
        ? "Strong"
        : passed === 2
          ? "Getting there"
          : "Weak",
  };
}

export function Signup() {
  const auth = useAuth();
  const navigate = useNavigate();

  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [accept, setAccept] = useState(false);
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const pw = useMemo(() => strength(password, email, fullName), [password, email, fullName]);
  const mismatch = confirm.length > 0 && confirm !== password;

  const submit = async () => {
    setError(null);
    if (fullName.trim().length < 2) return setError("Tell us your name.");
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim()))
      return setError("That doesn't look like an email address.");
    if (password !== confirm) return setError("The two passwords don't match.");
    if (!accept) return setError("Please accept the privacy notice to continue.");

    setBusy(true);
    const res = await auth.signup({
      full_name: fullName.trim(),
      email: email.trim(),
      phone: phone.trim() || null,
      password,
      confirm_password: confirm,
      accept_terms: accept,
    });
    setBusy(false);
    if (res.ok) navigate(res.home ?? "/dashboard", { replace: true });
    else setError(res.error ?? "We couldn't create that account.");
  };

  if (auth.status && !auth.status.signup_enabled) {
    return (
      <div className="login">
        <div className="login__bg">
          <ThreatField />
        </div>
        <div className="login__panel">
          <div className="login__content">
            <Link to="/" className="login__brand" aria-label="AegisAI home">
              <Logo size={24} />
            </Link>
            <h1 className="login__title">Sign-up is closed</h1>
            <p className="login__sub">
              This deployment doesn't accept public accounts. Ask an administrator
              to provision one for you.
            </p>
            <Link className="btn2 btn2--primary login__submit" to="/login">
              Back to sign in <ArrowRight size={15} aria-hidden="true" />
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="login login--split">
      <div className="login__bg">
        <ThreatField />
      </div>

      {/* Left: what the account is for. A sign-up form with no argument beside
          it is a form; with one, it is a decision. */}
      <aside className="signup__aside">
        <Link to="/" className="signup__brand" aria-label="AegisAI home">
          <LogoMark size={40} />
          <span className="signup__brandname">AegisAI</span>
        </Link>
        <h2 className="signup__pitch">
          Check anything suspicious.<br />Keep the evidence.
        </h2>
        <ul className="signup__points">
          <li>
            <ShieldCheck size={15} aria-hidden="true" />
            <span>
              <strong>Your cases are yours.</strong> An investigation you start is
              readable by you and by the investigators authorised to work it — not
              by other people with accounts.
            </span>
          </li>
          <li>
            <ShieldCheck size={15} aria-hidden="true" />
            <span>
              <strong>Nothing is stored unless you save it.</strong> Paste something
              in to check it and it is analysed and forgotten. Preserving it is a
              deliberate action.
            </span>
          </li>
          <li>
            <ShieldCheck size={15} aria-hidden="true" />
            <span>
              <strong>You can erase a case at any time</strong>, including the stored
              bytes of every file you attached.
            </span>
          </li>
        </ul>
        <p className="signup__note small faint">
          New accounts are <strong>citizen</strong> accounts. Investigator and
          administrator access is granted by an administrator after verification —
          never by choosing it on this form.
        </p>
      </aside>

      {/* Right: the form. */}
      <div className="login__panel signup__panel">
        <div className="login__content">
          <h1 className="login__title" data-reveal>Create your account</h1>
          <p className="login__sub" data-reveal>
            Free, and takes a minute.
          </p>

          <form
            className="login__form"
            onSubmit={(e) => {
              e.preventDefault();
              void submit();
            }}
          >
            <label className="fieldlabel" htmlFor="su-name" data-reveal>Full name</label>
            <div className="login__pwd" data-reveal>
              <UserRound size={14} className="login__pwd-lock" aria-hidden="true" />
              <input
                id="su-name"
                className="field"
                autoComplete="name"
                placeholder="Dhrumil Kadchha"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                required
              />
            </div>

            <label className="fieldlabel" htmlFor="su-email" data-reveal>Email</label>
            <div className="login__pwd" data-reveal>
              <Mail size={14} className="login__pwd-lock" aria-hidden="true" />
              <input
                id="su-email"
                className="field"
                type="email"
                autoComplete="email"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>

            <label className="fieldlabel" htmlFor="su-phone" data-reveal>
              Phone <span className="faint">(optional)</span>
            </label>
            <div className="login__pwd" data-reveal>
              <Phone size={14} className="login__pwd-lock" aria-hidden="true" />
              <input
                id="su-phone"
                className="field"
                type="tel"
                autoComplete="tel"
                placeholder="+91 98765 43210"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
              />
            </div>

            <label className="fieldlabel" htmlFor="su-pw" data-reveal>Password</label>
            <div className="login__pwd" data-reveal>
              <Lock size={14} className="login__pwd-lock" aria-hidden="true" />
              <input
                id="su-pw"
                className="field"
                type={showPw ? "text" : "password"}
                autoComplete="new-password"
                placeholder="••••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
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

            {password && (
              <div className="pwmeter" data-reveal>
                <div className="pwmeter__bar" aria-hidden="true">
                  <i
                    style={{ transform: `scaleX(${pw.score})` }}
                    data-level={pw.label.toLowerCase().replace(/\s+/g, "-")}
                  />
                </div>
                <ul className="pwmeter__list">
                  {pw.checks.map((c) => (
                    <li key={c.label} data-ok={c.ok || undefined}>
                      {c.ok ? <Check size={12} aria-hidden="true" /> : <X size={12} aria-hidden="true" />}
                      {c.label}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <label className="fieldlabel" htmlFor="su-confirm" data-reveal>
              Confirm password
            </label>
            <div className="login__pwd" data-reveal>
              <Lock size={14} className="login__pwd-lock" aria-hidden="true" />
              <input
                id="su-confirm"
                className="field"
                type={showPw ? "text" : "password"}
                autoComplete="new-password"
                placeholder="••••••••••"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                aria-invalid={mismatch || undefined}
                required
              />
            </div>
            {mismatch && (
              <p className="small" style={{ color: "var(--critical)", marginTop: "var(--s-1)" }}>
                The two passwords don't match.
              </p>
            )}

            <label className="checkrow" data-reveal>
              <input
                type="checkbox"
                checked={accept}
                onChange={(e) => setAccept(e.target.checked)}
              />
              <span className="small">
                I understand how AegisAI handles what I submit — analysis is not
                stored unless I save it, and I can erase a saved case at any time.
              </span>
            </label>

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
              {busy ? "Creating your account…" : "Create account"}{" "}
              <ArrowRight size={15} aria-hidden="true" />
            </button>
          </form>

          <p className="login__switch small" data-reveal>
            Already have an account? <Link to="/login">Sign in</Link>
          </p>
        </div>
      </div>
    </div>
  );
}
