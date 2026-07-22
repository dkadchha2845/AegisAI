/**
 * Intel — the FIGAE investigator dashboard (KAVACH Module 2).
 *
 * Correlates individual Module 1 detections into organised-crime intelligence:
 * live stats, an interactive fraud-network graph, an India hotspot map, campaign
 * clusters ranked by risk, entity search, the most-reused infrastructure, hidden
 * link predictions, and an AI investigation report per cluster.
 *
 * Pure renderer, like every other screen — every number here is a field the API
 * computed. React draws the graph and the map; it does not decide what is a
 * cluster or what is CRITICAL.
 */

import { useCallback, useEffect, useState } from "react";
import {
  AlertOctagon,
  GitBranch,
  MapPin,
  Network,
  Search,
  TrendingUp,
} from "lucide-react";
import * as api from "@/lib/api";
import type {
  CentralityEntity,
  Cluster,
  GraphData,
  Hotspot,
  IntelStats,
  InvestigationReport,
  LinkPrediction,
} from "@/lib/api";
import { ForceGraph } from "@/components/intel/ForceGraph";
import { HotspotMap } from "@/components/intel/HotspotMap";

const inr = (n: number) => "₹" + Math.round(n).toLocaleString("en-IN");

/** Compact Indian-system figure for stat tiles — "₹12.16 cr", "₹4.5 L".
 *  The full paise-exact figure belongs in reports; a stat card that clips
 *  its own number reads as broken. */
const inrCompact = (n: number) => {
  if (n >= 1e7) return "₹" + (n / 1e7).toFixed(2).replace(/\.?0+$/, "") + " cr";
  if (n >= 1e5) return "₹" + (n / 1e5).toFixed(1).replace(/\.0$/, "") + " L";
  return inr(n);
};

export function Intel() {
  const [stats, setStats] = useState<IntelStats | null>(null);
  const [clusters, setClusters] = useState<Cluster[]>([]);
  const [geo, setGeo] = useState<Hotspot[]>([]);
  const [centrality, setCentrality] = useState<CentralityEntity[]>([]);
  const [links, setLinks] = useState<LinkPrediction[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<
    { cluster: Cluster; graph: GraphData; report: InvestigationReport } | null
  >(null);
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    void (async () => {
      const [s, c, g, ce, l] = await Promise.all([
        api.getIntelStats(),
        api.getClusters(),
        api.getGeo(),
        api.getCentrality(),
        api.getLinkPredictions(),
      ]);
      if (s.ok) setStats(s.data);
      else setOffline(true);
      if (c.ok) {
        setClusters(c.data.clusters);
        if (c.data.clusters[0]) setSelected(c.data.clusters[0].cluster_id);
      }
      if (g.ok) setGeo(g.data.states);
      if (ce.ok) setCentrality(ce.data.entities);
      if (l.ok) setLinks(l.data.predictions);
    })();
  }, []);

  useEffect(() => {
    if (!selected) return;
    void (async () => {
      const res = await api.getClusterDetail(selected);
      if (res.ok) setDetail(res.data);
    })();
  }, [selected]);

  if (offline) {
    return (
      <div className="page">
        <h1 className="page__title">Fraud intel</h1>
        <div className="banner banner--bad">
          <div>
            <strong>The intelligence service is not reachable.</strong>
            <p className="small" style={{ margin: "6px 0 0" }}>
              Start the API on port 8000 to load the fraud graph.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="page">
      <header className="page__head">
        <p className="eyebrow">Analyst tool</p>
        <h1 className="page__title">Fraud intelligence graph</h1>
        <p className="page__lede">
          Every detection becomes a node in a continuously-evolving fraud graph.
          Community detection connects related cases into campaigns, geospatial
          analysis surfaces hotspots, and each cluster gets a dynamic risk score
          and an AI investigation report — turning single scam calls into
          organised-crime intelligence.
        </p>
      </header>

      {/* live statistics */}
      {stats && (
        <div className="statband" style={{ marginBottom: "var(--s-6)" }}>
          <Stat n={stats.active_clusters} label="Active fraud clusters" />
          <Stat n={stats.campaigns} label="Coordinated campaigns" tone="warn" />
          <Stat n={stats.total_cases} label="Total scam cases" />
          <Stat n={stats.linked_entities} label="Linked entities" />
          <Stat n={inrCompact(stats.total_loss_inr)} label="Reported exposure" tone="bad" />
        </div>
      )}

      <EntitySearch onCluster={setSelected} />

      {/* clusters + detail */}
      <div className="intel-split">
        <aside className="intel-clusters">
          <p className="label" style={{ marginBottom: "var(--s-2)" }}>
            Fraud clusters · worst first
          </p>
          <div className="stack" style={{ gap: "var(--s-2)" }}>
            {clusters.map((c) => (
              <button
                key={c.cluster_id}
                className={`clustercard ${selected === c.cluster_id ? "clustercard--active" : ""}`}
                data-risk={c.risk}
                onClick={() => setSelected(c.cluster_id)}
              >
                <div className="clustercard__top">
                  <span className="mono">{c.cluster_id}</span>
                  <span className="chip" data-risk={c.risk}>{c.risk}</span>
                </div>
                <strong className="clustercard__scam">{c.primary_scam_name}</strong>
                <div className="clustercard__meta small muted">
                  {c.size} cases · {c.states.length} states · {inr(c.total_loss_inr)}
                </div>
                <div className="riskbar">
                  <span style={{ width: `${c.risk_score}%` }} data-risk={c.risk} />
                </div>
              </button>
            ))}
          </div>
        </aside>

        <section className="intel-detail">
          {detail ? (
            <ClusterDetail detail={detail} selected={selected} />
          ) : (
            <div className="card"><p className="muted small">Select a cluster.</p></div>
          )}
        </section>
      </div>

      {/* geospatial + analytics */}
      <div className="intel-geo-grid">
        <div className="card">
          <h2 className="card__title"><MapPin size={16} /> Geospatial hotspots</h2>
          <HotspotMap hotspots={geo} />
        </div>

        <div className="stack">
          <div className="card">
            <h2 className="card__title"><TrendingUp size={16} /> Most-reused infrastructure</h2>
            <p className="small muted" style={{ marginTop: 0 }}>
              Centrality: the phones and payment IDs recurring across the most
              cases — freeze these first.
            </p>
            <div className="stack" style={{ gap: 6 }}>
              {centrality.slice(0, 7).map((e) => (
                <div key={e.id} className="centralrow">
                  <span className="chip">{e.kind}</span>
                  <span className="mono small centralrow__val">{e.value}</span>
                  <span className="small muted">{e.cases} cases</span>
                  {e.cluster && <span className="mono small faint">{e.cluster}</span>}
                </div>
              ))}
            </div>
          </div>

          <div className="card">
            <h2 className="card__title"><GitBranch size={16} /> Predicted hidden links</h2>
            <p className="small muted" style={{ marginTop: 0 }}>
              Different numbers joined through a shared payment account — likely
              the same operation.
            </p>
            <div className="stack" style={{ gap: 8 }}>
              {links.slice(0, 5).map((p, i) => (
                <div key={i} className="linkrow">
                  <span className="mono small">{p.source}</span>
                  <span className="linkrow__arrow">⇄</span>
                  <span className="mono small">{p.target}</span>
                  <span className="chip" data-tone="warn" style={{ marginLeft: "auto" }}>
                    {Math.round(p.confidence * 100)}%
                  </span>
                  <p className="linkrow__via small faint">via {p.via.join(", ")}</p>
                </div>
              ))}
              {!links.length && <p className="small muted">No hidden links predicted.</p>}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------- cluster detail */

function ClusterDetail({
  detail,
  selected,
}: {
  detail: { cluster: Cluster; graph: GraphData; report: InvestigationReport };
  selected: string | null;
}) {
  const { cluster, graph, report } = detail;
  return (
    <>
      <div className="card">
        <div className="row" style={{ justifyContent: "space-between" }}>
          <h2 className="card__title" style={{ margin: 0 }}>
            <Network size={16} /> {cluster.cluster_id} network
          </h2>
          <span className="chip" data-risk={cluster.risk}>
            {cluster.risk} · {cluster.risk_score.toFixed(0)}/100
          </span>
        </div>
        <ForceGraph data={graph} selectedCluster={selected} />
        <p className="small faint" style={{ marginTop: "var(--s-2)" }}>
          Cases in accent; phones, UPI IDs and wallets sized by reuse. Hover a node
          for detail.
        </p>
      </div>

      <div className="card">
        <h2 className="card__title"><AlertOctagon size={16} /> AI investigation report</h2>
        <div className="statband" style={{ marginBottom: "var(--s-4)" }}>
          <MiniStat n={report.summary.linked_cases} label="Linked cases" />
          <MiniStat n={report.summary.shared_phone_numbers} label="Shared numbers" />
          <MiniStat n={report.summary.shared_upi_ids} label="Shared UPI IDs" />
          <MiniStat n={report.summary.affected_states.length} label="States" />
        </div>

        <p className="intel-narrative">{report.narrative_llm || report.narrative}</p>

        <p className="label" style={{ marginTop: "var(--s-4)" }}>Risk factors</p>
        <div className="stack" style={{ gap: 6 }}>
          {report.risk_factors.slice(0, 4).map((f) => (
            <div key={f.factor} className="factorrow">
              <span className="small">{f.factor}</span>
              <div className="riskbar riskbar--sm">
                <span style={{ width: `${Math.min(100, f.contribution * 300)}%` }} data-risk={cluster.risk} />
              </div>
              <span className="small faint">{f.detail}</span>
            </div>
          ))}
        </div>

        <p className="label" style={{ marginTop: "var(--s-4)" }}>Suggested actions</p>
        <ul className="actions">
          {report.suggested_actions.map((a, i) => <li key={i}>{a}</li>)}
        </ul>

        {report.summary.affected_states.length > 0 && (
          <p className="small muted" style={{ marginTop: "var(--s-3)" }}>
            Affected states: {report.summary.affected_states.join(", ")}
          </p>
        )}
      </div>
    </>
  );
}

/* -------------------------------------------------------------- entity search */

function EntitySearch({ onCluster }: { onCluster: (id: string) => void }) {
  const [q, setQ] = useState("");
  const [result, setResult] = useState<Awaited<ReturnType<typeof api.searchIntel>> | null>(null);
  const [busy, setBusy] = useState(false);

  const run = useCallback(async () => {
    if (q.trim().length < 2) return;
    setBusy(true);
    const res = await api.searchIntel(q.trim());
    setBusy(false);
    setResult(res);
  }, [q]);

  return (
    <div className="card" style={{ marginBottom: "var(--s-5)" }}>
      <h2 className="card__title"><Search size={16} /> Entity search</h2>
      <div className="row" style={{ gap: "var(--s-2)" }}>
        <input
          className="field"
          placeholder="Phone, UPI ID, wallet, email, or case ID (e.g. 7042118830, customs.duty@okaxis)"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && run()}
          style={{ flex: 1 }}
        />
        <button className="btn2 btn2--primary" onClick={run} disabled={busy}>
          {busy ? "Searching…" : "Search"}
        </button>
      </div>
      {result?.ok && result.data.matches.length > 0 && (
        <div className="stack" style={{ gap: 6, marginTop: "var(--s-3)" }}>
          {result.data.matches.map((m, i) => (
            <div key={i} className="searchrow">
              <span className="chip">{m.kind}</span>
              <span className="mono small">{m.value}</span>
              <span className="small muted">{m.case_count} cases</span>
              <div className="row" style={{ gap: 4, marginLeft: "auto" }}>
                {m.clusters.map((c) => (
                  <button key={c} className="chip chip--link" data-tone="warn" onClick={() => onCluster(c)}>
                    {c}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
      {result?.ok && result.data.matches.length === 0 && (
        <p className="small muted" style={{ marginTop: "var(--s-3)" }}>
          Nothing in the fraud graph matches that identifier. That is not proof
          it is safe — only that it has not been reported into this network yet.
        </p>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------- helpers */

function Stat({ n, label, tone }: { n: number | string; label: string; tone?: string }) {
  return (
    <div className="stat">
      <div className="stat__n" data-tone={tone}>{n}</div>
      <p className="stat__l">{label}</p>
    </div>
  );
}

function MiniStat({ n, label }: { n: number; label: string }) {
  return (
    <div className="stat" style={{ padding: "var(--s-3)" }}>
      <div className="stat__n" style={{ fontSize: "var(--t-lg)" }}>{n}</div>
      <p className="stat__l">{label}</p>
    </div>
  );
}
