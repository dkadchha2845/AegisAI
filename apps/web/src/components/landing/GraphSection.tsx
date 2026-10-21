/**
 * What the graph knows that no single check can.
 *
 * One campaign from the intelligence store, drawn the way the store holds it:
 * the phone numbers and UPI handles it shares on an inner ring, the cases they
 * appear in on an outer one, and a line for every appearance. A number on its
 * own is a nuisance. The same four numbers and three handles turning up across
 * twenty-six cases in three states is an organisation — a different fact that
 * needs a different response.
 *
 * **The data is the store's, and it is synthetic.** The section loads campaign
 * FC-001 from `/api/intel/clusters/FC-001` — the same endpoint the
 * intelligence console reads. When that fails (the API is asleep, or it
 * enforces sign-in, as it does in production for an anonymous visitor), it
 * shows a snapshot of the same response from `landing/cluster.ts`. Either
 * way, the cases come from `seed_cases()`, which the store itself calls
 * "deterministic, clearly-synthetic", and the section says so on screen.
 *
 * **It is visibly interactive.** Until the reader touches it, the graph tours
 * itself: every few seconds another identifier lights up, its lines brighten,
 * the rest recede, and the panel reads it out. A pulsing ring marks the
 * current node, and nodes lift under the pointer. The moment the reader
 * hovers, focuses or taps a node, the tour stops and the graph is theirs.
 *
 * **The layout is computed from the data.** Identifiers are spaced evenly on
 * the inner ring; each case sits on the outer ring at the average angle of the
 * identifiers it used, so lines run outward rather than across the picture.
 * DOM nodes sit in slots that own their centring and never animate, so GSAP's
 * entrance cannot knock a node off the end of its lines.
 *
 * On a phone the drawing is replaced by its readout: the identifiers become a
 * row of chips that select, and the panel answers.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { Hash, IndianRupee } from "lucide-react";
import {
  gsap,
  split,
  fontsReady,
  DUR,
  EASE,
  reduced,
  refreshSoon,
} from "@/lib/landing-motion";
import * as api from "@/lib/api";
import {
  FC001_CAPTURED,
  FC001_CLUSTER,
  FC001_EDGES,
  FC001_FACTORS,
  FC001_NODES,
} from "@/components/landing/cluster";

const W = 900;
const H = 560;
const CX = W / 2;
const CY = H / 2;
const RING_IN = { rx: 214, ry: 136 };
const RING_OUT = { rx: 400, ry: 238 };
const TOUR_MS = 2800;

interface Campaign {
  cluster: api.Cluster;
  nodes: api.GraphNode[];
  edges: [string, string][];
  factors: api.RiskFactor[];
  source: "live" | "snapshot";
}

const SNAPSHOT: Campaign = {
  cluster: FC001_CLUSTER,
  nodes: FC001_NODES,
  edges: FC001_EDGES,
  factors: FC001_FACTORS,
  source: "snapshot",
};

interface Placed extends api.GraphNode {
  x: number;
  y: number;
}

const rad = (deg: number) => (deg * Math.PI) / 180;
const onRing = (deg: number, r: { rx: number; ry: number }) => ({
  x: CX + Math.cos(rad(deg)) * r.rx,
  y: CY + Math.sin(rad(deg)) * r.ry,
});

/** Identifiers evenly on the inner ring, phones and handles alternating;
 *  each case on the outer ring at the circular mean of its identifiers'
 *  angles, then spread evenly in that order. */
function layout(c: Campaign) {
  const ids = c.nodes.filter((n) => n.kind !== "case");
  const phones = ids.filter((n) => n.kind === "phone");
  const handles = ids.filter((n) => n.kind !== "phone");
  const ordered: api.GraphNode[] = [];
  for (let i = 0; i < Math.max(phones.length, handles.length); i++) {
    if (phones[i]) ordered.push(phones[i]);
    if (handles[i]) ordered.push(handles[i]);
  }
  const angle = new Map<string, number>();
  const placed = new Map<string, Placed>();
  ordered.forEach((n, i) => {
    const deg = -90 + (360 / ordered.length) * i;
    angle.set(n.id, deg);
    placed.set(n.id, { ...n, ...onRing(deg, RING_IN) });
  });

  const cases = c.nodes.filter((n) => n.kind === "case");
  const mean = (id: string) => {
    let sx = 0;
    let sy = 0;
    c.edges.forEach(([a, b]) => {
      const other = a === id ? b : b === id ? a : null;
      const deg = other ? angle.get(other) : undefined;
      if (deg !== undefined) {
        sx += Math.cos(rad(deg));
        sy += Math.sin(rad(deg));
      }
    });
    return (Math.atan2(sy, sx) * 180) / Math.PI;
  };
  const byAngle = cases
    .map((n) => ({ n, a: mean(n.id) }))
    .sort((p, q) => p.a - q.a);
  // Spread evenly, rotated so the slots sit as close as they can to the
  // angles the cases want.
  const step = 360 / Math.max(1, byAngle.length);
  const offset =
    byAngle.reduce((acc, p, i) => acc + (((p.a - (i * step - 180)) % 360) + 540) % 360 - 180, 0) /
    Math.max(1, byAngle.length);
  byAngle.forEach((p, i) => {
    const deg = i * step - 180 + offset;
    placed.set(p.n.id, { ...p.n, ...onRing(deg, RING_OUT) });
  });
  return { identifiers: ordered.map((n) => placed.get(n.id)!), cases: byAngle.map((p) => placed.get(p.n.id)!), placed };
}

const KIND: Record<string, string> = { phone: "Phone number", upi: "UPI handle", case: "Case" };
const crore = (inr: number) => `₹${(inr / 1e7).toFixed(2)} cr`;

export function GraphSection() {
  const root = useRef<HTMLElement>(null);
  const [data, setData] = useState<Campaign>(SNAPSHOT);
  const [active, setActive] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);

  /* --- the data: live first, snapshot if the store will not answer ---- */
  useEffect(() => {
    let alive = true;
    void api.getClusterDetail("FC-001").then((r) => {
      if (!alive || !r.ok) return;
      const { cluster, graph, report } = r.data;
      setData({
        cluster,
        nodes: graph.nodes,
        edges: graph.edges.map((e) => [e.source, e.target] as [string, string]),
        factors: report.risk_factors,
        source: "live",
      });
    });
    return () => {
      alive = false;
    };
  }, []);

  const { identifiers, cases, placed } = useMemo(() => layout(data), [data]);
  const neighbours = useMemo(() => {
    const m = new Map<string, Set<string>>();
    data.edges.forEach(([a, b]) => {
      if (!m.has(a)) m.set(a, new Set());
      if (!m.has(b)) m.set(b, new Set());
      m.get(a)!.add(b);
      m.get(b)!.add(a);
    });
    return m;
  }, [data]);

  const current = active ?? identifiers[0]?.id ?? null;
  const node = current ? placed.get(current) : undefined;
  const linked = current ? neighbours.get(current) ?? new Set<string>() : new Set<string>();

  /* --- the tour: until the reader takes over --------------------------- */
  useEffect(() => {
    const el = root.current;
    if (!el || touched || reduced() || !identifiers.length) return;
    let i = 0;
    let visible = false;
    const io = new IntersectionObserver(([e]) => {
      visible = e.isIntersecting;
    }, { threshold: 0.35 });
    const stage = el.querySelector("[data-g-stage]");
    if (stage) io.observe(stage);
    const timer = window.setInterval(() => {
      if (!visible) return;
      i = (i + 1) % identifiers.length;
      setActive(identifiers[i].id);
    }, TOUR_MS);
    return () => {
      window.clearInterval(timer);
      io.disconnect();
    };
  }, [touched, identifiers]);

  const choose = (id: string) => {
    setTouched(true);
    setActive(id);
  };

  /* --- the entrance ---------------------------------------------------- */
  useEffect(() => {
    const el = root.current;
    if (!el || reduced()) return;
    let cancelled = false;
    const teardown: (() => void)[] = [];

    void fontsReady().then(() => {
      if (cancelled) return;
      const ctx = gsap.context(() => {
        const h = split(el.querySelector("[data-g-h2]"), "lines");
        gsap.from(h.lines, {
          yPercent: 116,
          opacity: 0,
          filter: "blur(12px)",
          duration: DUR.slow,
          ease: EASE.out,
          stagger: 0.09,
          scrollTrigger: { trigger: el, start: "top 72%", once: true },
          onComplete: () => h.revert(),
        });
        gsap.from("[data-g-lede], [data-g-sum]", {
          opacity: 0,
          y: 22,
          filter: "blur(8px)",
          duration: DUR.reveal,
          ease: EASE.out,
          stagger: 0.1,
          scrollTrigger: { trigger: "[data-g-lede]", start: "top 88%", once: true },
        });

        /* Scrubbed against the stage's own arrival, and finished while the
           whole stage is still on screen: identifiers drift in from where
           they would be if nothing connected them, the cases surface on the
           outer ring, and only then do the lines between them draw. */
        const stage = el.querySelector<HTMLElement>("[data-g-stage]");
        const tl = gsap.timeline({
          scrollTrigger: { trigger: "[data-g-stage]", start: "top 86%", end: "top 30%", scrub: 0.8 },
        });
        gsap.utils.toArray<HTMLElement>("[data-g-id]").forEach((n, i) => {
          const a = (i * 137.5 * Math.PI) / 180;
          tl.from(
            n,
            {
              x: () => Math.cos(a) * (stage?.clientWidth ?? 600) * 0.16,
              y: () => Math.sin(a) * (stage?.clientHeight ?? 400) * 0.22,
              opacity: 0,
              scale: 0.75,
              duration: 0.8,
              ease: EASE.out,
            },
            i * 0.05,
          );
        });
        tl.from("[data-g-case]", { scale: 0, opacity: 0, duration: 0.4, stagger: 0.015, ease: "back.out(2)" }, 0.35)
          .from("[data-g-edge]", { drawSVG: "0% 0%", duration: 0.6, stagger: 0.006, ease: "power2.inOut" }, 0.55);

        gsap.from("[data-g-panel]", {
          opacity: 0,
          x: 26,
          filter: "blur(8px)",
          duration: DUR.reveal,
          ease: EASE.out,
          scrollTrigger: { trigger: "[data-g-panel]", start: "top 88%", once: true },
        });
      }, el);
      teardown.push(() => ctx.revert());
      refreshSoon();
    });

    return () => {
      cancelled = true;
      teardown.forEach((fn) => fn());
    };
  }, []);

  /* --- the readout ----------------------------------------------------- */
  const c = data.cluster;
  const caseCount = cases.length;
  const sharedWith = (id: string) => {
    const mine = neighbours.get(id) ?? new Set<string>();
    return identifiers
      .filter((o) => o.id !== id)
      .map((o) => {
        const theirs = neighbours.get(o.id) ?? new Set<string>();
        let n = 0;
        mine.forEach((x) => {
          if (theirs.has(x)) n++;
        });
        return { node: o, n };
      })
      .filter((s) => s.n > 0)
      .sort((p, q) => q.n - p.n);
  };
  const meanThreat = (id: string) => {
    const ts = [...(neighbours.get(id) ?? [])]
      .map((x) => placed.get(x)?.threat)
      .filter((t): t is number => typeof t === "number");
    return ts.length ? ts.reduce((a, b) => a + b, 0) / ts.length : null;
  };
  const topFactors = [...data.factors].sort((a, b) => b.contribution - a.contribution).slice(0, 3);
  const maxFactor = topFactors[0]?.contribution || 1;

  return (
    <section className="lp-section" id="graph" ref={root}>
      <div className="lp-shell">
        <p className="lp-eyebrow">
          <span className="lp-eyebrow__n">06</span> Intelligence
        </p>
        <h2 className="lp-h2" data-g-h2>
          Connections reveal what <em>isolated signals hide.</em>
        </h2>
        <p className="lp-lede" data-g-lede>
          Every case leaves identifiers behind. When the same phone numbers and UPI
          handles keep turning up across cases, the store collapses them into one
          campaign — with a risk score, a footprint across states, and a report an
          investigator can file. This is one of them.
        </p>

        {/* The campaign, in one line, before the drawing. */}
        <dl className="lp-graph__sum" data-g-sum>
          <div className="lp-graph__sumhead">
            <dt className="lp-mono">{c.cluster_id}</dt>
            <dd>{c.primary_scam_name}</dd>
          </div>
          <div>
            <dt>Risk</dt>
            <dd className="lp-mono">
              {c.risk} · {c.risk_score.toFixed(1)}
            </dd>
          </div>
          <div>
            <dt>Cases</dt>
            <dd className="lp-mono">{c.size}</dd>
          </div>
          <div>
            <dt>Shared identifiers</dt>
            <dd className="lp-mono">{identifiers.length}</dd>
          </div>
          <div>
            <dt>States</dt>
            <dd className="lp-mono">{c.states.length}</dd>
          </div>
          <div>
            <dt>Reported loss</dt>
            <dd className="lp-mono">{crore(c.total_loss_inr)}</dd>
          </div>
        </dl>

        <div className="lp-graph">
          <div
            className="lp-graph__stage"
            data-g-stage
            data-focus={current ? "" : undefined}
          >
            <svg className="lp-graph__svg" viewBox={`0 0 ${W} ${H}`} fill="none" aria-hidden="true">
              <ellipse className="lp-graph__ring" cx={CX} cy={CY} rx={RING_IN.rx} ry={RING_IN.ry} />
              <ellipse className="lp-graph__ring" cx={CX} cy={CY} rx={RING_OUT.rx} ry={RING_OUT.ry} />
              {data.edges.map(([a, b]) => {
                const na = placed.get(a);
                const nb = placed.get(b);
                if (!na || !nb) return null;
                const on = a === current || b === current;
                return (
                  <line
                    key={`${a}-${b}`}
                    className="lp-graph__edge"
                    data-g-edge
                    data-on={on || undefined}
                    x1={na.x}
                    y1={na.y}
                    x2={nb.x}
                    y2={nb.y}
                  />
                );
              })}
            </svg>

            <div className="lp-graph__layer">
              {cases.map((n) => {
                const on = n.id === current || linked.has(n.id);
                return (
                  <div
                    key={n.id}
                    className="lp-graph__slot"
                    data-on={on || undefined}
                    style={{ left: `${(n.x / W) * 100}%`, top: `${(n.y / H) * 100}%` }}
                  >
                    <button
                      type="button"
                      className="lp-graph__case"
                      data-g-case
                      aria-pressed={n.id === current}
                      aria-label={`Case ${n.label}${n.threat != null ? `, threat ${n.threat.toFixed(0)}` : ""}`}
                      onPointerEnter={() => choose(n.id)}
                      onFocus={() => choose(n.id)}
                      onClick={() => choose(n.id)}
                    >
                      <span />
                    </button>
                  </div>
                );
              })}

              {identifiers.map((n) => {
                const on = n.id === current || linked.has(n.id);
                const Icon = n.kind === "phone" ? Hash : IndianRupee;
                return (
                  <div
                    key={n.id}
                    className="lp-graph__slot"
                    data-on={on || undefined}
                    style={{ left: `${(n.x / W) * 100}%`, top: `${(n.y / H) * 100}%` }}
                  >
                    <button
                      type="button"
                      className="lp-graph__id"
                      data-g-id
                      data-kind={n.kind}
                      aria-pressed={n.id === current}
                      onPointerEnter={() => choose(n.id)}
                      onFocus={() => choose(n.id)}
                      onClick={() => choose(n.id)}
                    >
                      <span className="lp-graph__pulse" aria-hidden="true" />
                      <Icon size={13} strokeWidth={1.8} aria-hidden="true" />
                      <span className="lp-mono">{n.label}</span>
                      <em className="lp-mono">{n.cases}</em>
                    </button>
                  </div>
                );
              })}
            </div>

            <ul className="lp-graph__legend" aria-hidden="true">
              <li data-kind="phone">Phone number</li>
              <li data-kind="upi">UPI handle</li>
              <li data-kind="case">Case</li>
              <li data-kind="count">cases it appears in</li>
            </ul>
          </div>

          {/* On a phone the drawing goes; these chips select instead. */}
          <div className="lp-graph__chips" role="group" aria-label="Shared identifiers">
            {identifiers.map((n) => (
              <button
                key={n.id}
                type="button"
                className="lp-graph__chip lp-mono"
                data-kind={n.kind}
                aria-pressed={n.id === current}
                onClick={() => choose(n.id)}
              >
                {n.label}
              </button>
            ))}
          </div>

          {/* The readout. `aria-live` because the panel is the answer to the
              interaction, and a keyboard user needs it announced. */}
          <aside className="lp-graph__panel lp-card" data-g-panel aria-live="polite">
            {node && node.kind !== "case" && (
              <>
                <p className="lp-label">{KIND[node.kind] ?? node.kind}</p>
                <p className="lp-graph__pname lp-mono">{node.label}</p>
                <div className="lp-graph__stat">
                  <span>
                    In <b className="lp-mono">{linked.size}</b> of {caseCount} cases
                  </span>
                  <i style={{ ["--w" as string]: `${(linked.size / Math.max(1, caseCount)) * 100}%` }} />
                </div>
                {meanThreat(node.id) != null && (
                  <p className="lp-graph__line">
                    Mean threat across those cases{" "}
                    <b className="lp-mono">{meanThreat(node.id)!.toFixed(1)}</b>
                  </p>
                )}
                <p className="lp-label lp-graph__psub">Shares cases with</p>
                <ul className="lp-graph__links">
                  {sharedWith(node.id).map((s) => (
                    <li key={s.node.id}>
                      <button type="button" onClick={() => choose(s.node.id)}>
                        <span className="lp-mono">{s.node.label}</span>
                        <em>{s.n} shared</em>
                      </button>
                    </li>
                  ))}
                </ul>
              </>
            )}
            {node && node.kind === "case" && (
              <>
                <p className="lp-label">Case</p>
                <p className="lp-graph__pname lp-mono">{node.label}</p>
                {node.threat != null && (
                  <div className="lp-graph__stat">
                    <span>
                      Threat <b className="lp-mono">{node.threat.toFixed(1)}</b> / 100
                    </span>
                    <i style={{ ["--w" as string]: `${node.threat}%` }} />
                  </div>
                )}
                <p className="lp-label lp-graph__psub">Identifiers used</p>
                <ul className="lp-graph__links">
                  {[...linked].map((id) => {
                    const o = placed.get(id);
                    if (!o) return null;
                    return (
                      <li key={id}>
                        <button type="button" onClick={() => choose(id)}>
                          <span className="lp-mono">{o.label}</span>
                          <em>{KIND[o.kind] ?? o.kind}</em>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </>
            )}

            <p className="lp-label lp-graph__psub">Why {c.risk.toLowerCase()}</p>
            <ul className="lp-graph__factors">
              {topFactors.map((f) => (
                <li key={f.factor}>
                  <span>{f.factor}</span>
                  <em>{f.detail}</em>
                  <i style={{ ["--w" as string]: `${(f.contribution / maxFactor) * 100}%` }} />
                </li>
              ))}
            </ul>

            <p className="lp-graph__src">
              <span data-live={data.source === "live" || undefined} aria-hidden="true" />
              Synthetic demo dataset ·{" "}
              {data.source === "live"
                ? "loaded live from the intelligence store"
                : `snapshot of the intelligence store, ${FC001_CAPTURED}`}
            </p>
          </aside>
        </div>
      </div>
    </section>
  );
}
