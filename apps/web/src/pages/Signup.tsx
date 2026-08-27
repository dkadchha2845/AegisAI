/**
 * Create an account — §31.
 *
 * **There is no role picker, and that is the feature.** §19 is explicit that a
 * dropdown offering ADMIN is the vulnerability rather than the convenience; the
 * server creates a citizen and ignores anything else, so the form has nothing
 * to offer and nothing to have to safely discard. The copy beside it says so
 * out loud rather than leaving a visitor to wonder where the "I'm a police
 * officer" option went.
 *
 * **Validation is advisory here and enforced there.** The strength meter and
 * the match check exist so a person finds out before they submit; the same
 * rules run in `auth.password_problem` on the server, which is the one that
 * counts. The meter deliberately scores *length first* — a composition rule
 * ("one symbol!") measurably pushes people toward `Passw0rd!`, and length is
 * the property that actually resists a guess.
 *
 * Layout and chrome are `AuthShell`, shared with sign-in and the reset screens.
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
import { AuthShell } from "@/components/layout/AuthShell";
import { useAuth } from "@/context/AuthContext";

/** Mirrors `auth.password_problem` closely enough to be useful, and is trusted
 *  by nothing: the server re-runs every one of these. */
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
        ? "strong"
        : passed === 2
          ? "getting-there"
          : "weak",
  };
}

const PROMISES = [
  {
    title: "Your cases are yours",
    body: "An investigation you start is readable by you and by the investigators authorised to work it — not by other people with accounts.",
  },
  {
    title: "Nothing is stored unless you save it",
    body: "Paste something in to check it and it is analysed and forgotten. Preserving it is a deliberate action.",
  },
  {
    title: "You can erase a case at any time",
    body: "Erasure removes the rows and the stored bytes of every file you attached.",
  },
];

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
      <AuthShell
        title="Sign-up is closed"
        lede="This deployment doesn't accept public accounts. Ask an administrator to provision one for you."
      >
        <Link className="btn2 btn2--primary auth__submit" to="/login">
          Back to sign in <ArrowRight size={15} aria-hidden="true" />
        </Link>
      </AuthShell>
    );
  }

  const aside = (
    <>
      <h2 className="auth__pitch">
        Check anything suspicious.
        <br />
        Keep the evidence.
      </h2>
      <ul className="auth__points">
        {PROMISES.map((p) => (
          <li key={p.title}>
            <ShieldCheck size={16} aria-hidden="true" />
            <span>
              <strong>{p.title}.</strong> {p.body}
            </span>
          </li>
        ))}
      </ul>
      <p className="auth__note small faint">
        New accounts are <strong>citizen</strong> accounts. Investigator and
        administrator access is granted by an administrator after verification —
        never by choosing it on this form.
      </p>
    </>
  );

  return (
    <AuthShell
      aside={aside}
      title="Create your account"
      lede="Free, and takes a minute."
      footer={
        <p className="auth__switch small">
          Already have an account? <Link to="/login">Sign in</Link>
        </p>
      }
    >
      <form
        className="auth__form"
        data-reveal
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <label className="fieldlabel" htmlFor="su-name">Full name</label>
        <div className="auth__field">
          <UserRound size={15} className="auth__fieldicon" aria-hidden="true" />
          <input
            id="su-name"
            className="field"
            autoComplete="name"
            placeholder="Asha Verma"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            required
          />
        </div>

        <label className="fieldlabel" htmlFor="su-email">Email</label>
        <div className="auth__field">
          <Mail size={15} className="auth__fieldicon" aria-hidden="true" />
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

        <label className="fieldlabel" htmlFor="su-phone">
          Phone <span className="faint">(optional)</span>
        </label>
        <div className="auth__field">
          <Phone size={15} className="auth__fieldicon" aria-hidden="true" />
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

        <label className="fieldlabel" htmlFor="su-pw">Password</label>
        <div className="auth__field auth__field--toggle">
          <Lock size={15} className="auth__fieldicon" aria-hidden="true" />
          <input
            id="su-pw"
            className="field"
            type={showPw ? "text" : "password"}
            autoComplete="new-password"
            placeholder="At least 10 characters"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
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

        {password && (
          <div className="pwmeter">
            <div className="pwmeter__bar" aria-hidden="true">
              <i style={{ transform: `scaleX(${pw.score})` }} data-level={pw.label} />
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

        <label className="fieldlabel" htmlFor="su-confirm">Confirm password</label>
        <div className="auth__field">
          <Lock size={15} className="auth__fieldicon" aria-hidden="true" />
          <input
            id="su-confirm"
            className="field"
            type={showPw ? "text" : "password"}
            autoComplete="new-password"
            placeholder="Type it again"
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

        <label className="checkrow">
          <input
            type="checkbox"
            checked={accept}
            onChange={(e) => setAccept(e.target.checked)}
          />
          <span className="small">
            I understand how AegisAI handles what I submit — analysis is not stored
            unless I save it, and I can erase a saved case at any time.
          </span>
        </label>

        {error && (
          <div className="banner banner--bad" role="alert" style={{ marginTop: "var(--s-4)" }}>
            <div className="small">{error}</div>
          </div>
        )}

        <button className="btn2 btn2--primary auth__submit" type="submit" disabled={busy}>
          {busy ? "Creating your account…" : "Create account"}{" "}
          <ArrowRight size={15} aria-hidden="true" />
        </button>
      </form>
    </AuthShell>
  );
}
