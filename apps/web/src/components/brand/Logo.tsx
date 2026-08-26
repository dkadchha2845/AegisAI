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
 * Colour: the mark is `currentColor` by default so it inherits from whatever
 * chrome it sits in. It deliberately does *not* follow `--threat-color`.
 * Tying the logo to the threat ramp meant a CRITICAL call turned the brand
 * red, which spends the ramp's most urgent colour on something that carries
 * no reading — the same reason the sidebar's active state uses the accent.
 * The one exception is `live`, which the console opts into: there, a pulsing
 * threat-coloured mark *is* a status readout the analyst is watching for.
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
          16px where a crest with shoulders turns to mush. */}
      <path
        d="M12 2.2 20.2 5.1v6.6c0 4.7-3.2 8.6-8.2 10.1-5-1.5-8.2-5.4-8.2-10.1V5.1L12 2.2Z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
      {/* The instrument line: one diagonal cut, rising left to right. Two
          weights so it reads as a measurement, not a decoration. */}
      <path
        d="M8.1 14.4 11 11.2l2.1 2.3 3.1-4"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity="0.95"
      />
      <circle cx="16.2" cy="9.5" r="1.35" fill="currentColor" />
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
