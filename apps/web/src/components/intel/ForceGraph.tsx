/**
 * ForceGraph — a dependency-free force-directed graph for the fraud network.
 *
 * A small velocity-Verlet simulation (repulsion + edge springs + centering) that
 * settles in a few hundred ticks and then idles. Kept in-house rather than
 * pulling d3-force because the whole app is a pure renderer with a tight bundle,
 * and a scam-network graph of ~90 nodes does not need a physics library — it
 * needs to look alive, be readable, and never block the main thread, which a
 * capped, alpha-decaying loop does.
 *
 * Nodes are coloured by entity kind (cases carry the threat ramp; infrastructure
 * is neutral) and sized by reuse, so the visual weight of a node *is* its
 * centrality. Respects prefers-reduced-motion by settling instantly.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import type { GraphData, GraphNode } from "@/lib/api";

interface Sim {
  id: string;
  x: number;
  y: number;
  vx: number;
  vy: number;
  r: number;
  node: GraphNode;
}

const KIND_COLOR: Record<string, string> = {
  case: "var(--accent)",
  phone: "#e0a33c",
  upi: "#ec6a45",
  wallet: "#f2473f",
  email: "#8a7dff",
  bank: "#35c08b",
  domain: "#4bc0d9",
};

function radiusFor(node: GraphNode): number {
  if (node.kind === "case") return 6;
  const reuse = node.cases ?? 1;
  return Math.min(16, 5 + reuse * 0.9);
}

export function ForceGraph({
  data,
  height = 460,
  onSelect,
  selectedCluster,
}: {
  data: GraphData;
  height?: number;
  onSelect?: (node: GraphNode) => void;
  selectedCluster?: string | null;
}) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(720);
  const [, force] = useState(0);
  const rafRef = useRef<number>();
  const [hover, setHover] = useState<Sim | null>(null);

  // Measure the container so the sim centres correctly and scales responsively.
  useEffect(() => {
    if (!wrapRef.current) return;
    const ro = new ResizeObserver((entries) => {
      const w = entries[0].contentRect.width;
      if (w) setWidth(w);
    });
    ro.observe(wrapRef.current);
    return () => ro.disconnect();
  }, []);

  // Seed the simulation SYNCHRONOUSLY, keyed on the graph + size. Seeding in an
  // effect left the first paint reading an empty ref — the nodes never appeared
  // until an animation frame forced a re-render, which under some timings never
  // came. A useMemo gives every node a position on the very first render; the
  // effect below only *animates* this same array in place.
  const simRef = useRef<Sim[]>([]);
  const nodes = useMemo(() => {
    const cx = width / 2;
    const cy = height / 2;
    const seeded = data.nodes.map((node, i) => {
      const angle = (i / Math.max(1, data.nodes.length)) * Math.PI * 2;
      const rad = Math.min(width, height) * 0.32;
      return {
        id: node.id,
        x: cx + Math.cos(angle) * rad + (Math.random() - 0.5) * 40,
        y: cy + Math.sin(angle) * rad + (Math.random() - 0.5) * 40,
        vx: 0,
        vy: 0,
        r: radiusFor(node),
        node,
      };
    });
    simRef.current = seeded;
    return seeded;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, width, height]);

  const edges = useMemo(() => data.edges, [data]);
  const adjacency = useMemo(() => {
    const idx = new Map<string, number>();
    data.nodes.forEach((n, i) => idx.set(n.id, i));
    return edges
      .map((e) => [idx.get(e.source), idx.get(e.target)] as const)
      .filter(([a, b]) => a !== undefined && b !== undefined) as [number, number][];
  }, [data.nodes, edges]);

  // Animate the already-seeded array in place.
  useEffect(() => {
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let alpha = 1;
    const nodes = simRef.current;

    const tick = () => {
      const cxx = width / 2;
      const cyy = height / 2;
      // Repulsion (O(n²), fine for <200 nodes).
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const a = nodes[i];
          const b = nodes[j];
          let dx = a.x - b.x;
          let dy = a.y - b.y;
          let d2 = dx * dx + dy * dy || 0.01;
          const d = Math.sqrt(d2);
          const rep = (2400 * alpha) / d2;
          const fx = (dx / d) * rep;
          const fy = (dy / d) * rep;
          a.vx += fx;
          a.vy += fy;
          b.vx -= fx;
          b.vy -= fy;
        }
      }
      // Edge springs.
      for (const [ai, bi] of adjacency) {
        const a = nodes[ai];
        const b = nodes[bi];
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const d = Math.sqrt(dx * dx + dy * dy) || 0.01;
        const target = 54;
        const k = 0.02 * alpha * (d - target);
        const fx = (dx / d) * k;
        const fy = (dy / d) * k;
        a.vx += fx;
        a.vy += fy;
        b.vx -= fx;
        b.vy -= fy;
      }
      // Centering + integrate.
      for (const n of nodes) {
        n.vx += (cxx - n.x) * 0.006 * alpha;
        n.vy += (cyy - n.y) * 0.006 * alpha;
        n.vx *= 0.86;
        n.vy *= 0.86;
        n.x += n.vx;
        n.y += n.vy;
        n.x = Math.max(n.r + 4, Math.min(width - n.r - 4, n.x));
        n.y = Math.max(n.r + 4, Math.min(height - n.r - 4, n.y));
      }
      alpha *= 0.985;
      force((v) => v + 1);
      if (alpha > 0.02) rafRef.current = requestAnimationFrame(tick);
    };

    if (reduced) {
      for (let i = 0; i < 260; i++) {
        alpha = Math.max(0.02, alpha * 0.985);
      }
      // Run a synchronous settle for reduced-motion users.
      alpha = 1;
      for (let s = 0; s < 260; s++) tick();
    } else {
      rafRef.current = requestAnimationFrame(tick);
    }
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, width, height]);

  if (!data.nodes.length) {
    return (
      <div ref={wrapRef} className="fgraph fgraph--empty">
        <p className="muted small">No network to display.</p>
      </div>
    );
  }

  return (
    <div ref={wrapRef} className="fgraph">
      <svg width={width} height={height} role="img" aria-label="Fraud network graph">
        <g opacity={0.5}>
          {adjacency.map(([ai, bi], i) => {
            const a = nodes[ai];
            const b = nodes[bi];
            if (!a || !b) return null;
            return (
              <line
                key={i}
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                stroke="var(--line-strong)"
                strokeWidth={1}
              />
            );
          })}
        </g>
        {nodes.map((n) => {
          const color = KIND_COLOR[n.node.kind] ?? "var(--ink-faint)";
          const dim = selectedCluster && n.node.cluster && n.node.cluster !== selectedCluster;
          return (
            <g
              key={n.id}
              transform={`translate(${n.x},${n.y})`}
              className="fgraph__node"
              opacity={dim ? 0.25 : 1}
              onMouseEnter={() => setHover(n)}
              onMouseLeave={() => setHover((h) => (h?.id === n.id ? null : h))}
              onClick={() => onSelect?.(n.node)}
              style={{ cursor: onSelect ? "pointer" : "default" }}
            >
              <circle
                r={n.r}
                fill={color}
                fillOpacity={n.node.kind === "case" ? 0.9 : 0.22}
                stroke={color}
                strokeWidth={1.5}
              />
              {n.r >= 10 && (
                <text
                  y={-n.r - 4}
                  textAnchor="middle"
                  className="fgraph__label"
                  fill="var(--ink-muted)"
                >
                  {n.node.label}
                </text>
              )}
            </g>
          );
        })}
      </svg>
      {hover && (
        <div className="fgraph__tip" style={tipPos(hover, width)}>
          <span className="fgraph__tipkind" style={{ color: KIND_COLOR[hover.node.kind] }}>
            {hover.node.kind}
          </span>
          <strong>{hover.node.label}</strong>
          {hover.node.cases != null && hover.node.kind !== "case" && (
            <span className="muted small"> · reused in {hover.node.cases} cases</span>
          )}
          {hover.node.threat != null && (
            <span className="muted small"> · threat {Math.round(hover.node.threat)}</span>
          )}
        </div>
      )}
    </div>
  );
}

function tipPos(n: Sim, width: number): React.CSSProperties {
  const left = n.x > width - 200 ? n.x - 200 : n.x + 12;
  return { left, top: n.y + 12 };
}
