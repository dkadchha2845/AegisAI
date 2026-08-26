/**
 * The risk readout — a segmented arc, the score, the level, and the
 * confidence beneath it.
 *
 * Design notes, in the order they mattered:
 *
 * **Segments, not a smooth ring.** A continuous progress ring implies a
 * continuous, precise quantity. This score is not that: it is a fused figure
 * whose useful resolution is the band it lands in. Twenty ticks say "this is
 * a scale with bands" and stop the reader from over-reading 68 versus 71.
 *
 * **The unfilled arc stays visible.** A ring that only draws the filled part
 * gives no sense of where 92 sits on the range. The track is always there.
 *
 * **Confidence is separate and never multiplied in.** How sure the system is
 * and how bad the thing is are two different facts, and folding one into the
 * other is how a hedged number becomes a confident-looking one. They sit
 * next to each other, labelled.
 *
 * **Unscored is not zero.** `score == null` renders as an explicit "not
 * scored" state with an empty track — never as a dial reading 0, which would
 * be a claim the system has not made. This mirrors the same refusal in
 * `investigations/report.py`.
 *
 * This component performs no threat maths. `score`, `level` and `confidence`
 * are contract fields; the only arithmetic is turning a 0–100 number into an
 * arc length, which is drawing, not judgement.
 */

const SEGMENTS = 20;
const START = -220;   // degrees; 0° is 3 o'clock, so this opens at lower-left
const SWEEP = 260;    // leaves a gap at the bottom for the label

type Level = string | null | undefined;

interface Props {
  /** 0–100, or null when the judgement tier has not scored this. */
  score: number | null | undefined;
  /** CALM · WATCH · ELEVATED · HIGH · CRITICAL, or a case risk level. */
  level: Level;
  /** 0–1. Omitted when the system does not report one. */
  confidence?: number | null;
  /** Sentence under the dial — what the level means, in the reader's terms. */
  caption?: string;
  size?: number;
}

/** Maps a level onto the ramp already defined in tokens.css. */
function levelVar(level: Level): string {
  switch ((level ?? "").toUpperCase()) {
    case "CRITICAL": return "var(--critical)";
    case "HIGH": return "var(--high)";
    case "ELEVATED":
    case "MEDIUM": return "var(--elevated)";
    case "WATCH": return "var(--watch)";
    case "LOW":
    case "CALM":
    case "SAFE": return "var(--calm)";
    default: return "var(--ink-faint)";
  }
}

export function RiskDial({ score, level, confidence, caption, size = 168 }: Props) {
  const scored = typeof score === "number" && Number.isFinite(score);
  const pct = scored ? Math.max(0, Math.min(100, score)) : 0;
  const lit = Math.round((pct / 100) * SEGMENTS);
  const colour = scored ? levelVar(level) : "var(--ink-faint)";

  const r = size / 2 - 12;
  const cx = size / 2;
  const cy = size / 2;

  return (
    <div className="riskdial" style={{ ["--dial-color" as string]: colour }}>
      <div className="riskdial__gauge" style={{ width: size, height: size }}>
        <svg
          width={size}
          height={size}
          viewBox={`0 0 ${size} ${size}`}
          role="img"
          aria-label={
            scored
              ? `Risk ${Math.round(pct)} out of 100, level ${level ?? "unknown"}`
              : "Not scored"
          }
        >
          {Array.from({ length: SEGMENTS }, (_, i) => {
            const angle = START + (SWEEP / (SEGMENTS - 1)) * i;
            const rad = (angle * Math.PI) / 180;
            const inner = r - 9;
            return (
              <line
                key={i}
                x1={cx + Math.cos(rad) * inner}
                y1={cy + Math.sin(rad) * inner}
                x2={cx + Math.cos(rad) * r}
                y2={cy + Math.sin(rad) * r}
                className="riskdial__tick"
                data-lit={i < lit || undefined}
                strokeLinecap="round"
              />
            );
          })}
        </svg>
        <div className="riskdial__readout">
          {scored ? (
            <>
              <span className="riskdial__score mono">{Math.round(pct)}</span>
              <span className="riskdial__level">{level}</span>
            </>
          ) : (
            <span className="riskdial__unscored">Not scored</span>
          )}
        </div>
      </div>

      {caption && <p className="riskdial__caption">{caption}</p>}

      {typeof confidence === "number" && (
        <div className="riskdial__conf">
          <div className="riskdial__confhead">
            <span className="label">Confidence</span>
            <span className="mono">{Math.round(confidence * 100)}%</span>
          </div>
          <div className="riskdial__conftrack">
            <i style={{ width: `${Math.max(0, Math.min(1, confidence)) * 100}%` }} />
          </div>
        </div>
      )}
    </div>
  );
}
