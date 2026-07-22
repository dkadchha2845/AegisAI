/**
 * ScamMap — the one interactive geospatial surface for the whole product.
 *
 * OpenStreetMap tiles via Leaflet, so there is no API key to leak and no
 * per-load billing — a real consideration for a citizen tool that must keep
 * working after the demo. CARTO's light/dark raster themes are used so the map
 * reads as part of the app in either theme rather than a bright rectangle
 * dropped into a dark console.
 *
 * Deliberately provider-agnostic at the seam: every Leaflet import is contained
 * in this file, and the public props (`hotspots` / `points` / `height` /
 * filters / geolocation) describe *what to show*, not *how*. Swapping to Google
 * Maps later means rewriting this component against the same props — nothing
 * upstream (Analyze, Home, Admin) changes. That is the modularity the brief
 * asked for, without the ceremony of a premature abstraction layer.
 *
 * Two data shapes, one map:
 *   • `hotspots` — aggregated city/district/state density (from /api/intel/geo).
 *   • `points`   — individual dated cases (from /api/intel/points), which is
 *                  what makes clustering and the date filter *real* rather than
 *                  decorative. A date filter over pre-aggregated buckets would
 *                  be a control that does nothing; we only show it when the data
 *                  underneath it actually carries dates.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { MapContainer, TileLayer, Marker, Popup, Circle, useMap } from "react-leaflet";
import MarkerClusterGroup from "react-leaflet-cluster";
import L from "leaflet";
import { Crosshair, Filter } from "lucide-react";
import { useTheme } from "@/context/ThemeContext";
import type { Hotspot, ScamPoint } from "@/lib/api";
import "leaflet/dist/leaflet.css";
import "./scam-map.css";

interface ScamMapProps {
  /** Aggregated density buckets. */
  hotspots?: Hotspot[];
  /** Per-case dated points — enables clustering + the date filter. */
  points?: ScamPoint[];
  /** Scam-type options for the filter (from getPoints); derived if omitted. */
  scamTypes?: { id: string; name: string }[];
  height?: number;
  /** Cluster markers. Defaults on for points, off for the few hotspot buckets. */
  cluster?: boolean;
  /** Show the "near me" geolocation control. */
  showUserLocation?: boolean;
  /** Show the scam-type / risk / date filter toolbar. */
  enableFilters?: boolean;
  className?: string;
}

/** Normalised marker the renderer works from, regardless of source shape. */
interface MapMarker {
  id: string;
  lat: number;
  lon: number;
  title: string;
  risk: string;
  scamType: string | null;
  scamName: string | null;
  cases: number | null;
  amountInr: number | null;
  reportedAt: string | null;
}

const RISK_COLOR: Record<string, string> = {
  CRITICAL: "var(--critical)",
  HIGH: "var(--high)",
  ELEVATED: "var(--elevated)",
  WATCH: "var(--watch)",
  MEDIUM: "var(--elevated)",
  CALM: "var(--calm)",
  LOW: "var(--calm)",
};
const riskColor = (r: string) => RISK_COLOR[r] ?? "var(--ink-faint)";

const INR = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
});

function hotspotToMarker(h: Hotspot): MapMarker {
  return {
    id: `hs-${h.name}-${h.lat}-${h.lon}`,
    lat: h.lat,
    lon: h.lon,
    title: h.name,
    risk: h.risk,
    scamType: h.top_scam,
    scamName: h.top_scam,
    cases: h.cases,
    amountInr: h.total_loss_inr,
    reportedAt: null,
  };
}

function pointToMarker(p: ScamPoint): MapMarker {
  return {
    id: p.id,
    lat: p.lat,
    lon: p.lon,
    title: p.city ?? p.state ?? "Reported case",
    risk: p.risk,
    scamType: p.scam_type,
    scamName: p.scam_name,
    cases: null,
    amountInr: p.amount_inr,
    reportedAt: p.reported_at,
  };
}

/** Leaflet div-icon coloured by risk; hotspot markers scale with case volume. */
function pinIcon(marker: MapMarker, maxCases: number): L.DivIcon {
  const base = 14;
  const size =
    marker.cases != null && maxCases > 0
      ? base + Math.round(Math.sqrt(marker.cases / maxCases) * 16)
      : base;
  const color = riskColor(marker.risk);
  return L.divIcon({
    className: "scam-pin",
    html: `<span style="--pin:${color};width:${size}px;height:${size}px"></span>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

/** Cluster bubble sized/coloured by how many reports it folds together. */
function clusterIcon(cluster: { getChildCount: () => number }): L.DivIcon {
  const n = cluster.getChildCount();
  const tier = n >= 25 ? "high" : n >= 10 ? "mid" : "low";
  return L.divIcon({
    className: "scam-cluster",
    html: `<div class="scam-cluster__b" data-tier="${tier}"><span>${n}</span></div>`,
    iconSize: [40, 40],
  });
}

function haversineKm(a: [number, number], b: [number, number]): number {
  const R = 6371;
  const dLat = ((b[0] - a[0]) * Math.PI) / 180;
  const dLon = ((b[1] - a[1]) * Math.PI) / 180;
  const lat1 = (a[0] * Math.PI) / 180;
  const lat2 = (b[0] * Math.PI) / 180;
  const h =
    Math.sin(dLat / 2) ** 2 + Math.sin(dLon / 2) ** 2 * Math.cos(lat1) * Math.cos(lat2);
  return 2 * R * Math.asin(Math.sqrt(h));
}

/** Imperatively flies the map when the user's location resolves. Lives inside
 *  MapContainer so it can use the map instance. */
function FlyToUser({ pos }: { pos: [number, number] | null }) {
  const map = useMap();
  useEffect(() => {
    if (pos) map.flyTo(pos, 9, { duration: 1.1 });
  }, [pos, map]);
  return null;
}

/** Keeps Leaflet's cached size correct after the container animates/resizes in
 *  (reveal animations leave the map thinking it's 0px tall otherwise). */
function InvalidateOnMount() {
  const map = useMap();
  useEffect(() => {
    const t = setTimeout(() => map.invalidateSize(), 200);
    return () => clearTimeout(t);
  }, [map]);
  return null;
}

const DATE_WINDOWS = [
  { id: "all", label: "All time", days: 0 },
  { id: "90", label: "90 days", days: 90 },
  { id: "30", label: "30 days", days: 30 },
  { id: "7", label: "7 days", days: 7 },
] as const;

export function ScamMap({
  hotspots,
  points,
  scamTypes,
  height = 360,
  cluster,
  showUserLocation = false,
  enableFilters = false,
  className,
}: ScamMapProps) {
  const { theme } = useTheme();
  const [scamFilter, setScamFilter] = useState<string>("all");
  const [riskFilter, setRiskFilter] = useState<string>("all");
  const [dateWindow, setDateWindow] = useState<string>("all");
  const [userPos, setUserPos] = useState<[number, number] | null>(null);
  const [geoError, setGeoError] = useState<string | null>(null);
  const [geoBusy, setGeoBusy] = useState(false);
  const mapKey = useRef(`map-${Math.random().toString(36).slice(2)}`).current;

  const allMarkers = useMemo<MapMarker[]>(() => {
    if (points && points.length) return points.map(pointToMarker);
    if (hotspots && hotspots.length) return hotspots.map(hotspotToMarker);
    return [];
  }, [points, hotspots]);

  const hasDates = allMarkers.some((m) => m.reportedAt);
  // Date windows are relative to the newest report in the data, not to "now",
  // so the control always reveals something on a fixed demo corpus.
  const latestDate = useMemo(() => {
    const ds = allMarkers.map((m) => m.reportedAt).filter(Boolean) as string[];
    return ds.length ? ds.reduce((a, b) => (a > b ? a : b)) : null;
  }, [allMarkers]);

  const scamOptions = useMemo(() => {
    if (scamTypes && scamTypes.length) return scamTypes;
    const seen = new Map<string, string>();
    allMarkers.forEach((m) => {
      if (m.scamType) seen.set(m.scamType, m.scamName ?? m.scamType);
    });
    return [...seen.entries()].map(([id, name]) => ({ id, name })).sort((a, b) =>
      a.name.localeCompare(b.name),
    );
  }, [scamTypes, allMarkers]);

  const markers = useMemo(() => {
    let list = allMarkers;
    if (scamFilter !== "all") list = list.filter((m) => m.scamType === scamFilter);
    if (riskFilter !== "all") list = list.filter((m) => m.risk === riskFilter);
    if (dateWindow !== "all" && latestDate) {
      const win = DATE_WINDOWS.find((w) => w.id === dateWindow);
      if (win && win.days) {
        const cutoff = new Date(latestDate);
        cutoff.setDate(cutoff.getDate() - win.days);
        const cutoffStr = cutoff.toISOString().slice(0, 10);
        list = list.filter((m) => m.reportedAt && m.reportedAt >= cutoffStr);
      }
    }
    return list;
  }, [allMarkers, scamFilter, riskFilter, dateWindow, latestDate]);

  const maxCases = useMemo(
    () => Math.max(1, ...markers.map((m) => m.cases ?? 0)),
    [markers],
  );

  const nearest = useMemo(() => {
    if (!userPos) return null;
    const ranked = markers
      .map((m) => ({ m, km: haversineKm(userPos, [m.lat, m.lon]) }))
      .sort((a, b) => a.km - b.km);
    return ranked[0] ?? null;
  }, [userPos, markers]);

  const locate = () => {
    if (!("geolocation" in navigator)) {
      setGeoError("Location isn't available in this browser.");
      return;
    }
    setGeoBusy(true);
    setGeoError(null);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setUserPos([pos.coords.latitude, pos.coords.longitude]);
        setGeoBusy(false);
      },
      () => {
        setGeoError("Couldn't get your location — showing all of India.");
        setGeoBusy(false);
      },
      { enableHighAccuracy: false, timeout: 8000, maximumAge: 300000 },
    );
  };

  const doCluster = cluster ?? Boolean(points && points.length);

  const tileUrl =
    theme === "light"
      ? "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
      : "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png";

  const markerNodes = markers.map((m) => (
    <Marker 
      key={m.id} 
      position={[m.lat, m.lon]} 
      icon={pinIcon(m, maxCases)}
      title={`${m.title} - ${m.risk} risk`}
      alt={`Map marker for ${m.title}`}
      keyboard={true}
    >
      <Popup>
        <div className="scam-popup">
          <strong className="scam-popup__title">{m.title}</strong>
          <span className="scam-popup__risk" style={{ color: riskColor(m.risk) }}>
            {m.risk}
          </span>
          {m.scamName && <div className="scam-popup__row">{m.scamName}</div>}
          {m.cases != null && (
            <div className="scam-popup__row">
              {m.cases} report{m.cases === 1 ? "" : "s"}
            </div>
          )}
          {m.amountInr != null && m.amountInr > 0 && (
            <div className="scam-popup__row">{INR.format(m.amountInr)} at risk</div>
          )}
          {m.reportedAt && <div className="scam-popup__row muted">Reported {m.reportedAt}</div>}
        </div>
      </Popup>
    </Marker>
  ));

  return (
    <div className={`scam-map ${className ?? ""}`}>
      {(enableFilters || showUserLocation) && (
        <div className="scam-map__bar">
          {enableFilters && (
            <>
              <span className="scam-map__filtericon">
                <Filter size={13} />
              </span>
              <select
                className="scam-map__select"
                value={scamFilter}
                onChange={(e) => setScamFilter(e.target.value)}
                aria-label="Filter by scam type"
              >
                <option value="all">All scam types</option>
                {scamOptions.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
              <select
                className="scam-map__select"
                value={riskFilter}
                onChange={(e) => setRiskFilter(e.target.value)}
                aria-label="Filter by risk level"
              >
                <option value="all">Any risk</option>
                {["CRITICAL", "HIGH", "ELEVATED", "WATCH", "CALM"].map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </select>
              {hasDates && (
                <div className="scam-map__seg" role="group" aria-label="Filter by date">
                  {DATE_WINDOWS.map((w) => (
                    <button
                      key={w.id}
                      type="button"
                      className="scam-map__segbtn"
                      data-on={dateWindow === w.id || undefined}
                      onClick={() => setDateWindow(w.id)}
                    >
                      {w.label}
                    </button>
                  ))}
                </div>
              )}
            </>
          )}
          {showUserLocation && (
            <button
              type="button"
              className="scam-map__locate"
              onClick={locate}
              disabled={geoBusy}
            >
              <Crosshair size={13} /> {geoBusy ? "Locating…" : "Scams near me"}
            </button>
          )}
        </div>
      )}

      <div className="scam-map__canvas" style={{ height }}>
        <MapContainer
          key={mapKey}
          center={[22.6, 79]}
          zoom={5}
          minZoom={4}
          scrollWheelZoom={false}
          worldCopyJump
          className="scam-map__leaflet"
        >
          <TileLayer
            url={tileUrl}
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>'
          />
          <InvalidateOnMount />
          <FlyToUser pos={userPos} />

          {doCluster ? (
            <MarkerClusterGroup
              chunkedLoading
              maxClusterRadius={50}
              showCoverageOnHover={false}
              iconCreateFunction={clusterIcon}
            >
              {markerNodes}
            </MarkerClusterGroup>
          ) : (
            markerNodes
          )}

          {userPos && (
            <>
              <Circle
                center={userPos}
                radius={30000}
                pathOptions={{ color: "var(--accent)", fillColor: "var(--accent)", fillOpacity: 0.08, weight: 1 }}
              />
              <Marker
                position={userPos}
                icon={L.divIcon({ className: "scam-you", html: "<span></span>", iconSize: [16, 16], iconAnchor: [8, 8] })}
              >
                <Popup>You are here</Popup>
              </Marker>
            </>
          )}
        </MapContainer>
      </div>

      <div className="scam-map__foot">
        <span className="scam-map__count">
          {markers.length} {points ? "report" : "hotspot"}
          {markers.length === 1 ? "" : "s"} shown
        </span>
        {geoError && <span className="scam-map__geoerr">{geoError}</span>}
        {nearest && !geoError && (
          <span className="scam-map__near">
            Nearest: <strong>{nearest.m.title}</strong> ({Math.round(nearest.km)} km
            {nearest.m.scamName ? ` · ${nearest.m.scamName}` : ""})
          </span>
        )}
      </div>
    </div>
  );
}
