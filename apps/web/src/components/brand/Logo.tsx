/**
 * The AegisAI mark — one drawing, used everywhere.
 *
 * Before this there were four brand marks: a 9px rounded square in the app
 * top bar, a second 9px square with a different border-radius in the console,
 * a third in the login panel, and a fourth on the landing header. Three of
 * them tracked the live threat colour and one did not, so the "brand" changed
 * hue depending on which screen you were on.
 *
 * The drawing is a shield whose interior is cut by a single diagonal — the
 * aegis, and the line an instrument draws through it. A geometric mark rather
 * than an illustration: it has to survive at 16px in a browser tab, which
 * anything with interior detail does not.
 *
 * Colour: two tones, both from tokens. The shield takes `currentColor`, so it
 * inherits the ink of whatever chrome holds it; the instrument line and its
 * dot take `--accent`. The pairing is the same one the interface uses
 * everywhere else, and it is what makes the mark legible as *this* mark at
 * 16px in a tab strip rather than as a generic shield glyph.
 *
 * It deliberately does *not* follow `--threat-color`. Tying the logo to the
 * threat ramp meant a CRITICAL call turned the brand red, which spends the
 * ramp's most urgent colour on something that carries no reading — the same
 * reason the sidebar's active state uses the accent. The one exception is
 * `live`, which the console opts into: there, a pulsing threat-coloured mark
 * *is* a status readout the analyst is watching for, and it overrides both
 * tones so the mark reads as one signal.
 */

import type { CSSProperties } from "react";

export type LogoVariant = "full" | "compact";

interface LogoProps {
  /** `full` renders mark + wordmark; `compact` is the mark alone. */
  variant?: LogoVariant;
  /** Mark size in px. The wordmark scales from it. */
  size?: number;
  /** Track `--threat-color` and pulse. Console only — see the note above. */
  live?: boolean;
  className?: string;
  style?: CSSProperties;
}

/** The mark on its own, for favicons, avatars and the collapsed sidebar. */
export function LogoMark({ size = 20, live = false, className, style }: Omit<LogoProps, "variant">) {
  return (
    <svg
      className={["logo__mark", live ? "logo__mark--live" : "", className ?? ""]
        .filter(Boolean)
        .join(" ")}
      style={style}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
      focusable="false"
    >
      {/* Shield silhouette. Flat top, tapered base — reads as protection at
          16px where a crest with shoulders turns to mush. Takes the ink of
          whatever chrome it sits in. */}
      <path
        className="logo__shield"
        d="M12 2.2 20.2 5.1v6.6c0 4.7-3.2 8.6-8.2 10.1-5-1.5-8.2-5.4-8.2-10.1V5.1L12 2.2Z"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
      {/* The instrument line: one diagonal cut, rising left to right, carrying
          the accent. Two colours rather than one because the mark then says
          both halves of the name — the shield is Aegis, the reading inside it
          is the AI — and because a single-weight monochrome glyph at 16px is
          indistinguishable from every other shield icon in a tab strip. */}
      <path
        className="logo__spark"
        d="M8.1 14.4 11 11.2l2.1 2.3 3.1-4"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle className="logo__dot" cx="16.2" cy="9.5" r="1.35" />
    </svg>
  );
}

export function Logo({ variant = "full", size = 20, live = false, className, style }: LogoProps) {
  return (
    <span
      className={["logo", className ?? ""].filter(Boolean).join(" ")}
      style={{ ...style, ["--logo-size" as string]: `${size}px` }}
    >
      <LogoMark size={size} live={live} />
      {variant === "full" && <span className="logo__word">AegisAI</span>}
    </span>
  );
}
