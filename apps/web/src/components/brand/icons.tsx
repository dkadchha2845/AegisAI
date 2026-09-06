/**
 * The AegisAI icon set — the navigation and dashboard glyphs, drawn here.
 *
 * **Why not keep using the icon library.** Lucide is a good library and the
 * rest of the app still uses it for incidental controls. But its glyphs are the
 * house style of every scaffolded dashboard on the internet, and at the two
 * places a person looks most — the rail they navigate by, and the tiles that
 * carry the platform's headline numbers — the interface was wearing someone
 * else's face. Three pairs of destinations also collided: Analyze and
 * Investigate shared `ScanSearch`, Learn and Model card shared `BookOpen`, and
 * Profile and Administration shared `UserCircle`. A rail where two rows are the
 * same picture is a rail you have to read the words of, which is the one job
 * the icon was there to save you.
 *
 * **The grammar.** Every glyph is drawn on the same 24×24 grid as
 * `Logo.tsx`, at the mark's own 1.6 stroke with round joins, and keeps its
 * content inside a 3–21 box so nothing clips at 16px. Three shapes recur and
 * mean the same thing everywhere they appear:
 *
 *   * **the reading line** — the logo's rising polyline, for anything that is
 *     a measurement over time (Dashboard, Investigate, exposure);
 *   * **the point** — a filled dot at the end of a line, for the latest or
 *     dominant value;
 *   * **the shield** — the logo's silhouette, only for protection itself
 *     (Guardian), never as decoration.
 *
 * Colour is always `currentColor`, so a glyph takes the ink of the row it sits
 * in and the accent when that row is active. Nothing here carries the threat
 * ramp: an icon is not a readout, and spending the ramp on chrome is what
 * makes a real CRITICAL stop registering.
 *
 * **Limitations.** This covers navigation, the user menu, and the dashboard
 * surfaces. Deeper instruments (the live console, form affordances, table
 * controls) are still lucide, and mixing two sets on one screen is a real cost
 * — worth paying only where the custom set is finished. Extend it here rather
 * than reaching back for a library glyph on a nav-level surface.
 */

import type { ReactNode } from "react";

export interface IconProps {
  /** Rendered box in px. The drawing is a 24-unit grid scaled to it. */
  size?: number;
  className?: string;
  /** Only for oversized display uses, where 1.6 at 40px reads as spidery. */
  strokeWidth?: number;
}

/** The component shape every glyph here satisfies. Structurally compatible
 *  with `LucideIcon` at the call sites that take either. */
export type AegisIcon = (props: IconProps) => ReactNode;

function Glyph({
  size = 18,
  className,
  strokeWidth = 1.6,
  children,
}: IconProps & { children: ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  );
}

/** A measured point. `stroke="none"` so it stays a dot rather than growing a
 *  1.6 halo and closing up at 16px. */
function Point({ cx, cy, r = 1.5 }: { cx: number; cy: number; r?: number }) {
  return <circle cx={cx} cy={cy} r={r} fill="currentColor" stroke="none" />;
}

/* --- Protection ----------------------------------------------------------- */

/** Dashboard — a reading against an axis, with its latest point marked. */
export const IconDashboard: AegisIcon = (p) => (
  <Glyph {...p}>
    <path d="M4 3.8v14.6a1.4 1.4 0 0 0 1.4 1.4H20" />
    <path d="M7.6 15.4 11 11.3l2.6 2.4 3.8-5" />
    <Point cx={17.4} cy={8.7} />
  </Glyph>
);

/** Home — a flat-pitched house with eaves. The one glyph in the set that is
 *  deliberately conventional: "start here" has to be read, not decoded. */
export const IconHome: AegisIcon = (p) => (
  <Glyph {...p}>
    <path d="M3.4 10.7 12 4.2l8.6 6.5" />
    <path d="M5.7 9.7v9.1a1.2 1.2 0 0 0 1.2 1.2h10.2a1.2 1.2 0 0 0 1.2-1.2V9.7" />
    <path d="M9.9 20v-5.1h4.2V20" />
  </Glyph>
);

/** Analyze — a viewfinder with a scan line across it. Four corners rather than
 *  a magnifier, so it does not collide with Investigate. */
export const IconAnalyze: AegisIcon = (p) => (
  <Glyph {...p}>
    <path d="M4 8.4V5.6A1.6 1.6 0 0 1 5.6 4h2.8" />
    <path d="M15.6 4h2.8A1.6 1.6 0 0 1 20 5.6v2.8" />
    <path d="M20 15.6v2.8a1.6 1.6 0 0 1-1.6 1.6h-2.8" />
    <path d="M8.4 20H5.6A1.6 1.6 0 0 1 4 18.4v-2.8" />
    <path d="M7.6 12h8.8" />
  </Glyph>
);

/** Live Protection — a live trace. One continuous stroke, because a call in
 *  progress is one continuous thing. */
export const IconLive: AegisIcon = (p) => (
  <Glyph {...p}>
    <path d="M2.8 12h3l1.9-5.4 3 11 2.3-7.8 1.6 4.3 1.3-2.1h4.1" />
  </Glyph>
);

/** My Reports — a filed document: fold, and the two lines of a record. */
export const IconReports: AegisIcon = (p) => (
  <Glyph {...p}>
    <path d="M7.4 3.4h6.1l4.7 4.6v10.6a1.4 1.4 0 0 1-1.4 1.4H7.4A1.4 1.4 0 0 1 6 18.6V4.8a1.4 1.4 0 0 1 1.4-1.4Z" />
    <path d="M13.3 3.6v3.7a1 1 0 0 0 1 1h3.8" />
    <path d="M9.2 13.4h5.6M9.2 16.4h3.2" />
  </Glyph>
);

/** Learn — an open book, spine centred. */
export const IconLearn: AegisIcon = (p) => (
  <Glyph {...p}>
    <path d="M12 7.1v12.7" />
    <path d="M12 7.1C10.4 5.7 8.4 5 5.7 5A1.2 1.2 0 0 0 4.5 6.2v10.6A1.2 1.2 0 0 0 5.7 18c2.7 0 4.7.7 6.3 2" />
    <path d="M12 7.1c1.6-1.4 3.6-2.1 6.3-2.1a1.2 1.2 0 0 1 1.2 1.2v10.6a1.2 1.2 0 0 1-1.2 1.2c-2.7 0-4.7.7-6.3 2" />
  </Glyph>
);

/** Emergency — a hazard triangle. The most conventional shape available on
 *  purpose: this is the row someone looks for while panicking. */
export const IconEmergency: AegisIcon = (p) => (
  <Glyph {...p}>
    <path d="M12 4.2 20.4 18.9a1 1 0 0 1-.87 1.5H4.47a1 1 0 0 1-.87-1.5L12 4.2Z" />
    <path d="M12 10.2v4.1" />
    <Point cx={12} cy={17.3} r={1.2} />
  </Glyph>
);

/** Profile — a person. */
export const IconProfile: AegisIcon = (p) => (
  <Glyph {...p}>
    <circle cx="12" cy="8.5" r="3.6" />
    <path d="M4.9 20.1a7.5 7.5 0 0 1 14.2 0" />
  </Glyph>
);

/* --- Investigator tools --------------------------------------------------- */

/** Investigate — the logo's reading line seen through a lens. Submitting
 *  evidence is looking closely at a reading, which is exactly the pairing. */
export const IconInvestigate: AegisIcon = (p) => (
  <Glyph {...p}>
    <circle cx="10.6" cy="10.6" r="6.2" />
    <path d="M15.1 15.1 20.3 20.3" />
    <path d="M8 11.8 10 9.3l1.7 1.9 2.2-2.9" />
  </Glyph>
);

/** Live console — a signal broadcasting from a point. Deliberately different
 *  from Live Protection: the citizen's screen shows the trace, the analyst's
 *  console is the receiver. */
export const IconConsole: AegisIcon = (p) => (
  <Glyph {...p}>
    <Point cx={12} cy={12} r={1.9} />
    <path d="M8.2 15.8a5.4 5.4 0 0 1 0-7.6" />
    <path d="M15.8 8.2a5.4 5.4 0 0 1 0 7.6" />
    <path d="M5.4 18.6a9.3 9.3 0 0 1 0-13.2" />
    <path d="M18.6 5.4a9.3 9.3 0 0 1 0 13.2" />
  </Glyph>
);

/** Fraud intelligence — three nodes and the edges between them. */
export const IconGraph: AegisIcon = (p) => (
  <Glyph {...p}>
    <circle cx="12" cy="5.1" r="2.3" />
    <circle cx="5.1" cy="17.3" r="2.3" />
    <circle cx="18.9" cy="17.3" r="2.3" />
    <path d="M10.8 7.1 6.3 15.3M13.2 7.1l4.5 8.2M7.4 17.3h9.2" />
  </Glyph>
);

/** Guardian — the logo's shield holding. The interior is a pause, because that
 *  is literally what the circuit breaker does to a payment. A single horizontal
 *  bar was tried first and read as a prohibition sign, which is a different
 *  claim: this console holds a transaction, it does not forbid one. */
export const IconGuardian: AegisIcon = (p) => (
  <Glyph {...p}>
    <path d="M12 3.2 19.6 5.9v5.9c0 4.3-2.9 7.8-7.6 9.2-4.7-1.4-7.6-4.9-7.6-9.2V5.9L12 3.2Z" />
    <path d="M10.3 9.9v4.6M13.7 9.9v4.6" />
  </Glyph>
);

/** Analyzer — driver weights as bars, the dominant one marked. */
export const IconAnalyzer: AegisIcon = (p) => (
  <Glyph {...p}>
    <path d="M3.8 20.2h16.4" />
    <path d="M7 20.2v-9.6M11.6 20.2V7.6M16.2 20.2v-6.4" />
    <Point cx={11.6} cy={5.6} r={1.4} />
  </Glyph>
);

/** Model card — a processor with its leads. Replaces the brain-in-a-circuit,
 *  which is the single most over-used glyph in AI product design and says
 *  nothing about a checkpoint's architecture or its limits. */
export const IconModel: AegisIcon = (p) => (
  <Glyph {...p}>
    <rect x="4.8" y="4.8" width="14.4" height="14.4" rx="2.4" />
    <rect x="9.4" y="9.4" width="5.2" height="5.2" rx="1" />
    <path d="M9.4 3v1.8M14.6 3v1.8M9.4 19.2V21M14.6 19.2V21M3 9.4h1.8M3 14.6h1.8M19.2 9.4H21M19.2 14.6H21" />
  </Glyph>
);

/* --- Oversight ------------------------------------------------------------ */

/** Research — a flask with a fill line. */
export const IconResearch: AegisIcon = (p) => (
  <Glyph {...p}>
    <path d="M8.4 3.4h7.2" />
    <path d="M9.6 3.4v6.1l-4.4 8a1.5 1.5 0 0 0 1.3 2.3h11a1.5 1.5 0 0 0 1.3-2.3l-4.4-8V3.4" />
    <path d="M7 14.4h10" />
    <Point cx={10.4} cy={17.2} r={1} />
  </Glyph>
);

/** Administration — a keyhole. The console is about who may open what, which
 *  is a lock, not a person: `UserCircle` here was the same glyph as Profile. */
export const IconAdmin: AegisIcon = (p) => (
  <Glyph {...p}>
    <rect x="3.8" y="3.8" width="16.4" height="16.4" rx="4" />
    <circle cx="12" cy="10.3" r="2.4" />
    <path d="M12 12.8v3.6" />
  </Glyph>
);

/* --- Dashboard surfaces --------------------------------------------------- */

/** Cases held — a body of records, seen edge-on. */
export const IconCases: AegisIcon = (p) => (
  <Glyph {...p}>
    <path d="M4.4 7.4 12 3.6l7.6 3.8L12 11.2 4.4 7.4Z" />
    <path d="M4.4 12 12 15.8 19.6 12" />
    <path d="M4.4 16.6 12 20.4l7.6-3.8" />
  </Glyph>
);

/** Clusters — satellites resolved around a centre, which is what community
 *  detection actually produces. */
export const IconCluster: AegisIcon = (p) => (
  <Glyph {...p}>
    <circle cx="12" cy="12.5" r="2.7" />
    <circle cx="5.3" cy="6.6" r="2.1" />
    <circle cx="19" cy="7.7" r="2.1" />
    <circle cx="7.9" cy="19" r="2.1" />
    <path d="M6.9 8.2 10.1 10.9M17.4 9.2 14.1 11.1M9 17.2l1.7-2.5" />
  </Glyph>
);

/** Reported exposure — the reading line falling. The deliberate mirror of
 *  `IconDashboard`: same grammar, opposite direction, so the pair reads as one
 *  measurement going two ways. */
export const IconExposure: AegisIcon = (p) => (
  <Glyph {...p}>
    <path d="M4 4.6v13.8a1.4 1.4 0 0 0 1.4 1.4H20" />
    <path d="M7.4 9 10.8 12.8l2.6-2.2 3.8 4.4" />
    <Point cx={17.2} cy={15} />
  </Glyph>
);

/** System monitoring — a live trace inside a frame. The instrument, not the
 *  signal: `IconLive` is the signal. */
export const IconMonitor: AegisIcon = (p) => (
  <Glyph {...p}>
    <rect x="3.4" y="5" width="17.2" height="14" rx="2.2" />
    <path d="M6.6 12.2h2.2l1.5-3.4 2.2 6.6 1.5-3.2h2.6" />
  </Glyph>
);

/** Hotspots — a located point on the map. */
export const IconMap: AegisIcon = (p) => (
  <Glyph {...p}>
    <path d="M12 20.8c4.1-4.6 6.2-8 6.2-10.4a6.2 6.2 0 1 0-12.4 0c0 2.4 2.1 5.8 6.2 10.4Z" />
    <circle cx="12" cy="10.3" r="2.3" />
  </Glyph>
);

/** The user roster — people, plural. A single-person glyph here is the same
 *  drawing as Profile, which is the collision this set exists to avoid. */
export const IconRoster: AegisIcon = (p) => (
  <Glyph {...p}>
    <circle cx="10" cy="8.6" r="3.5" />
    <path d="M4 20a6 6 0 0 1 12 0" />
    <circle cx="17.6" cy="8" r="2.3" />
    <path d="M17 14.2a4.6 4.6 0 0 1 3 4.4" />
  </Glyph>
);

/** Trends — the direction of travel, over a baseline. Deliberately an arrow
 *  rather than a plotted reading: `IconDashboard` is the reading, and two
 *  glyphs of a line in an axis on one screen would be one glyph too many. */
export const IconTrend: AegisIcon = (p) => (
  <Glyph {...p}>
    <path d="M3.6 20.4h16.8" />
    <path d="M4.2 15.8 9.6 10l3.4 3.2 6.8-7" />
    <path d="M15 6.2h5v5" />
  </Glyph>
);

/** What a surface will not show you — a closed lock. The one place the product
 *  states a limit on itself, so it gets the most literal drawing in the set. */
export const IconPrivacy: AegisIcon = (p) => (
  <Glyph {...p}>
    <rect x="4.6" y="10.4" width="14.8" height="9.6" rx="2.2" />
    <path d="M8.4 10.4V7.9a3.6 3.6 0 0 1 7.2 0v2.5" />
    <Point cx={12} cy={15.2} r={1.3} />
  </Glyph>
);

