/**
 * The risk badge — colour **and** label **and** number from one `level` and
 * one `score` (DESIGN_SYSTEM.md §3, gap G-08).
 *
 * Until this existed every page wrote the chip markup itself, and the three
 * parts drifted: a colour with no label for a colour-blind reader, a number
 * with no band. This renders all three from contract fields and decides
 * nothing — the band is `level` as the server sent it, never derived from the
 * number here (invariant 2).
 *
 * Unscored is not zero. `score == null` renders "Not scored" in a neutral
 * chip, the same refusal `RiskDial` and `investigations/report.py` make.
 */

const LABEL: Record<string, string> = {
  CALM: "Calm",
  WATCH: "Watch",
  ELEVATED: "Elevated",
  HIGH: "High",
  CRITICAL: "Critical",
};

interface Props {
  /** The band from the contract: CALM · WATCH · ELEVATED · HIGH · CRITICAL. */
  level: string | null | undefined;
  /** 0–100, or null when nothing was scored. */
  score?: number | null;
  /** Label only — for dense tables where the number sits in its own column. */
  hideScore?: boolean;
}

export function RiskBadge({ level, score, hideScore }: Props) {
  const scored = typeof score === "number" && Number.isFinite(score) && !!level;
  if (!scored && !level) {
    return (
      <span className="chip chip--caps riskbadge" data-risk="NONE">
        Not scored
      </span>
    );
  }
  const band = (level ?? "").toUpperCase();
  const label = LABEL[band] ?? band;
  const number = scored ? Math.round(score as number) : null;
  return (
    <span
      className="chip chip--caps riskbadge"
      data-risk={band}
      aria-label={number === null ? `Risk level ${label}` : `Risk ${number} of 100, ${label}`}
    >
      <span aria-hidden="true">{label}</span>
      {number !== null && !hideScore && (
        <span className="riskbadge__score mono" aria-hidden="true">
          {number}
        </span>
      )}
    </span>
  );
}
