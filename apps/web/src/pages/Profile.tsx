/**
 * Profile — the account, and the settings that actually do something.
 *
 * Two things changed in the UI audit.
 *
 * **The tool list is gone.** This page was the *only* way to reach the
 * analyst tools, so it carried eight link rows duplicating what a sidebar is
 * for. `navGroups` now renders them as a navigation group for the roles that
 * can use them, which is where a person looks for a destination.
 *
 * **There are no invented settings.** The obvious way to fill a settings page
 * is eight sections of plausible-looking toggles — notifications, AI
 * preferences, API keys — and every one of them would be a control that
 * changes nothing. A switch that does not switch anything is a lie told in
 * the interface, and the same rule that keeps unmeasured latency out of the
 * copy keeps decorative toggles out of here. Every control below is wired to
 * real behaviour; the sections that are statements of fact are written as
 * statements of fact.
 */

import { Link } from "react-router-dom";
import { LogIn, LogOut, Monitor, Moon, ShieldCheck, Sun, Zap } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { useAuth } from "@/context/AuthContext";
import { useTheme } from "@/context/ThemeContext";
import { useMotionPreference } from "@/hooks/useMotionPreference";

export function Profile() {
  const { user, org, authed, logout } = useAuth();
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
            </dl>
            <button className="btn2" style={{ marginTop: "var(--s-4)" }} onClick={logout}>
              <LogOut size={14} aria-hidden="true" /> Sign out
            </button>
          </>
        ) : (
          <>
            <p className="small muted" style={{ marginTop: 0 }}>
              You don't need an account to check something or to get help. Sign in only if
              you're an analyst using the professional tools.
            </p>
            <Link className="btn2 btn2--primary" to="/login">
              <LogIn size={14} aria-hidden="true" /> Sign in
            </Link>
          </>
        )}
      </section>

      {/* --- Appearance ------------------------------------------------- */}
      <section className="card">
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
            <strong>Saved evidence is scoped to your organisation.</strong> Members of it can
            read the case; nobody outside it can — not even a platform owner.
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
