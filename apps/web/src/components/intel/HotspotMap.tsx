/**
 * HotspotMap — a geospatial command-centre view of fraud density across India.
 *
 * An equirectangular projection of the hotspot coordinates onto a simplified
 * India silhouette (the outline is projected with the very same transform as the
 * data, so bubbles land in the right state). Bubble area encodes case count and
 * colour encodes the risk band — the same threat ramp used everywhere else, so a
 * red bubble on the map means exactly what a red meter means on a call.
 *
 * No mapping library, no tiles, no network: a self-contained SVG that renders
 * offline like the rest of the product. Precise cartography is not the point —
 * placing "where is this happening, and how badly" at a glance is.
 */

import { useState } from "react";
import type { Hotspot } from "@/lib/api";

// Bounding box of the projection. India spans ~6.5–37.5°N, ~68–97.5°E.
const LON_MIN = 67;
const LON_MAX = 98;
const LAT_MIN = 6;
const LAT_MAX = 37.5;
const W = 440;
const H = 500;

function project(lon: number, lat: number): [number, number] {
  const x = ((lon - LON_MIN) / (LON_MAX - LON_MIN)) * W;
  const y = ((LAT_MAX - lat) / (LAT_MAX - LAT_MIN)) * H;
  return [x, y];
}

// A coarse but recognisable mainland outline, [lon, lat] going clockwise from
// the north-west. Approximate on purpose — the bubbles carry the real data.
const INDIA_OUTLINE: [number, number][] = [
  [74, 34], [76.5, 34.5], [78, 33], [79, 32], [81, 30], [83, 28.5], [85, 27.5],
  [88, 27], [88.7, 26.3], [90, 26.5], [92, 27.5], [94, 27.8], [95.5, 27], [95, 25.5],
  [93.5, 24], [92.5, 22.5], [91.5, 23.5], [89.5, 22], [88.2, 21.5], [87, 21], [86, 20],
  [84, 18.5], [82, 17], [80.3, 15.8], [80.2, 13.5], [79.8, 11.8], [79, 10.3], [78.2, 8.9],
  [77.5, 8.1], [76.5, 9], [75.8, 11], [74.5, 13.5], [73.5, 15.7], [73, 17.7], [72.7, 19.2],
  [72.6, 21], [70.5, 20.9], [69, 22.3], [68.3, 23.5], [69.7, 24], [71, 24.3], [70.2, 25.5],
  [70.8, 27.5], [73, 29.5], [74.5, 31], [74, 32.5], [74, 34],
];

const RISK_COLOR: Record<string, string> = {
  CRITICAL: "var(--critical)",
  HIGH: "var(--high)",
  MEDIUM: "var(--elevated)",
  LOW: "var(--calm)",
};

export function HotspotMap({
  hotspots,
  height = 500,
}: {
  hotspots: Hotspot[];
  height?: number;
}) {
  const [hover, setHover] = useState<Hotspot | null>(null);
  const outlinePath =
    "M" +
    INDIA_OUTLINE.map(([lon, lat]) => {
      const [x, y] = project(lon, lat);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(" L") +
    " Z";

  const maxCases = Math.max(1, ...hotspots.map((h) => h.cases));

  return (
    <div className="hmap">
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={height} role="img"
           aria-label="Fraud hotspot map of India">
        {/* graticule */}
        <g opacity={0.25}>
          {[10, 15, 20, 25, 30, 35].map((lat) => {
            const [, y] = project(LON_MIN, lat);
            return <line key={lat} x1={0} y1={y} x2={W} y2={y} stroke="var(--line)" strokeWidth={0.5} />;
          })}
          {[70, 75, 80, 85, 90, 95].map((lon) => {
            const [x] = project(lon, LAT_MAX);
            return <line key={lon} x1={x} y1={0} x2={x} y2={H} stroke="var(--line)" strokeWidth={0.5} />;
          })}
        </g>
        {/* landmass */}
        <path d={outlinePath} fill="var(--panel-hover)" stroke="var(--line-strong)" strokeWidth={1.2} />
        {/* hotspot bubbles */}
        {hotspots.map((h) => {
          const [x, y] = project(h.lon, h.lat);
          const r = 4 + Math.sqrt(h.cases / maxCases) * 22;
          const color = RISK_COLOR[h.risk] ?? "var(--ink-faint)";
          return (
            <g key={h.name} transform={`translate(${x},${y})`}
               onMouseEnter={() => setHover(h)} onMouseLeave={() => setHover(null)}>
              <circle r={r} fill={color} fillOpacity={0.16} stroke={color} strokeWidth={1.4}>
                {h.risk === "CRITICAL" && (
                  <animate attributeName="r" values={`${r};${r + 4};${r}`} dur="2.4s" repeatCount="indefinite" />
                )}
              </circle>
              <circle r={2.5} fill={color} />
            </g>
          );
        })}
      </svg>
      {hover && (
        <div className="hmap__tip">
          <strong>{hover.name}</strong>
          <span className="chip" data-risk={hover.risk} style={{ marginLeft: 6 }}>{hover.risk}</span>
          <p className="small muted" style={{ margin: "4px 0 0" }}>
            {hover.cases} cases · ₹{hover.total_loss_inr.toLocaleString("en-IN")} exposure
            {hover.top_scam ? ` · ${hover.top_scam.replace(/_/g, " ")}` : ""}
          </p>
        </div>
      )}
      <div className="hmap__legend">
        {(["CRITICAL", "HIGH", "MEDIUM", "LOW"] as const).map((r) => (
          <span key={r} className="hmap__legenditem">
            <span className="hmap__dot" style={{ background: RISK_COLOR[r] }} /> {r}
          </span>
        ))}
      </div>
    </div>
  );
}
