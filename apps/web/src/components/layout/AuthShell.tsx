/**
 * The frame every authentication screen sits in — §31, §32, §40.
 *
 * One component for sign-in, sign-up and both halves of the password reset,
 * because four screens that are the same screen with different fields in it
 * should not be four layouts. Before this each one built its own centred card,
 * which is how the sign-in screen ended up a 430px strip in a 1440px window
 * with the submit button below the fold and the rest of the viewport empty.
 *
 * **Full-bleed, two columns, neither of them an island.** The brand side
 * carries the WebGL field and the argument and fills its half edge to edge; the
 * form side is a solid surface with the form optically centred in it. Nothing
 * is capped to a width that leaves dead margins at the sides, which is what
 * made the old layout read as cropped.
 *
 * **The form column scrolls, not the page.** The sign-in screen carries nine
 * demo accounts above its fields in open mode, which is taller than a laptop
 * viewport — so the column that contains them owns the overflow. The submit
 * button is then always reachable by scrolling *the form*, and the brand side
 * never moves.
 *
 * Below 920px it becomes one column: brand first as a compact header, then the
 * form. The argument is not hidden on a phone — a person deciding whether to
 * create an account needs it there more than anywhere.
 */

import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { Logo } from "@/components/brand/Logo";
import { ThreatField } from "@/components/three/ThreatField";

interface Props {
  /** The pitch beside the form. Omitted on the short screens (reset), which
   *  then render a single centred column rather than a half-empty split. */
  aside?: ReactNode;
  title: string;
  /** One line under the title. */
  lede?: ReactNode;
  children: ReactNode;
  /** Below the form — the "already have an account?" switch and the footnote. */
  footer?: ReactNode;
}

export function AuthShell({ aside, title, lede, children, footer }: Props) {
  return (
    <div className="auth" data-split={aside ? "" : undefined}>
      <aside className="auth__aside">
        <div className="auth__bg" aria-hidden="true">
          <ThreatField />
        </div>
        <div className="auth__asideinner">
          <Link to="/" className="auth__brand" aria-label="AegisAI home">
            <Logo size={26} />
          </Link>
          {aside}
        </div>
      </aside>

      <main className="auth__main">
        <div className="auth__card">
          <h1 className="auth__title" data-reveal>{title}</h1>
          {lede && <p className="auth__lede" data-reveal>{lede}</p>}
          {children}
          {footer}
        </div>
      </main>
    </div>
  );
}
