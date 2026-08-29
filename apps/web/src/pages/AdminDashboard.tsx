/**
 * Admin dashboard — the platform-operator view, gated to `admin`+ roles.
 *
 * Deliberately separate from the citizen surfaces: a citizen never sees model
 * internals, the user roster, or system health, and an analyst's console is
 * about a single call. This is the "is the whole platform healthy, who can use
 * it, and what is the fraud picture" view. Everything here is real data from
 * endpoints that already existed — health, the model card, Module 2 intel, the
 * user roster — assembled behind one role check rather than re-derived.
 */

import { useEffect, useState } from "react";
import {
  Activity,
  BrainCircuit,
  Database,
  MapPin,
  ShieldCheck,
  Users,
} from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { AuditLog, Organizations, Users as UserRoster } from "@/pages/admin/Tenancy";
import { formatInr } from "@/lib/format";
import * as api from "@/lib/api";
import type { Health, IntelStats, ModelCard, ScamPoint } from "@/lib/api";
import { ScamMap } from "@/components/map/ScamMap";
import { useAuth } from "@/context/AuthContext";

export function AdminDashboard() {
  const { user } = useAuth();
  const [health, setHealth] = useState<Health | null>(null);
  const [card, setCard] = useState<ModelCard | null>(null);
  const [stats, setStats] = useState<IntelStats | null>(null);
  const [points, setPoints] = useState<ScamPoint[]>([]);
  const [scamTypes, setScamTypes] = useState<{ id: string; name: string }[]>([]);

  // The user roster and its add-user form live in pages/admin/Tenancy, which
  // owns the only copy. This page used to fetch and render its own.

  useEffect(() => {
    void (async () => {
      const [h, c, s, p] = await Promise.all([
        api.getHealth(),
        api.getModelCard(),
        api.getIntelStats(),
        api.getPoints(),
      ]);
      if (h.ok) setHealth(h.data);
      if (c.ok) setCard(c.data);
      if (s.ok) setStats(s.data);
      if (p.ok) {
        setPoints(p.data.points);
        setScamTypes(p.data.scam_types);
      }
    })();
  }, []);

  const scores = card?.evaluation?.scores ?? {};
  const kpis = [
    { label: "Fraud cases", value: stats?.total_cases ?? "—", icon: Database },
    { label: "Active clusters", value: stats?.active_clusters ?? "—", icon: Activity },
    { label: "Linked entities", value: stats?.linked_entities ?? "—", icon: Users },
    {
      // Same formatter as the operations screen. These two pages used to
      // render the same field as "₹12Cr" and "₹12.16 cr", which reads as two
      // different measurements of two different things.
      label: "Loss tracked",
      value: stats ? formatInr(stats.total_loss_inr) : "—",
      icon: ShieldCheck,
    },
  ];

  return (
    <div className="page">
      <PageHeader
        title="Administration"
        lede="Platform health, fraud intelligence, and access control."
        actions={
          user?.role ? (
            <span className="chip chip--caps" data-tone="ok">{user.role}</span>
          ) : undefined
        }
      />

      <div className="stack" style={{ gap: "var(--s-6)" }}>
        {/* KPI row */}
        <div className="admin-kpis">
          {kpis.map((k) => (
            <div key={k.label} className="card admin-kpi">
              <k.icon size={18} className="admin-kpi__icon" />
              <strong className="admin-kpi__v">{k.value}</strong>
              <span className="small faint">{k.label}</span>
            </div>
          ))}
        </div>

        <div className="admin-grid">
          {/* System monitoring */}
          <div className="card">
            <h2 className="card__title">
              <Activity size={16} /> System monitoring
            </h2>
            {health ? (
              <ul className="admin-status">
                <StatusRow
                  label="Classifier"
                  value={health.classifier.backend}
                  ok={health.classifier.serving_best}
                  detail={health.classifier.reason}
                />
                <StatusRow
                  label="Retrieval (RAG)"
                  value={`${health.retrieval.backend} · ${health.retrieval.chunks} chunks`}
                  ok={health.retrieval.chunks > 0}
                />
                <StatusRow
                  label="Digital twin"
                  value={health.twin.fitted ? "fitted" : "unfitted"}
                  ok={health.twin.fitted}
                />
                <StatusRow
                  label="LLM explainer"
                  value={health.llm.configured ? `${health.llm.backend}` : "not configured"}
                  ok={health.llm.configured}
                />
                {health.database && (
                  <StatusRow
                    label="Database"
                    value={health.database.backend}
                    ok={health.database.persistent}
                    detail={health.database.persistent ? "persistent" : "in-memory"}
                  />
                )}
                <StatusRow
                  label="Degradations"
                  value={health.degraded.length ? health.degraded.join(", ") : "none"}
                  ok={health.degraded.length === 0}
                />
              </ul>
            ) : (
              <p className="small muted">Loading…</p>
            )}
          </div>

          {/* AI model stats */}
          <div className="card">
            <h2 className="card__title">
              <BrainCircuit size={16} /> AI model
            </h2>
            {card ? (
              <div className="stack" style={{ gap: 8 }}>
                <div className="row" style={{ justifyContent: "space-between" }}>
                  <span className="small muted">Serving</span>
                  <span className="chip" data-tone="ok">{card.active_backend}</span>
                </div>
                <div className="row" style={{ justifyContent: "space-between" }}>
                  <span className="small muted">Base model</span>
                  <span className="small mono">{card.base_model}</span>
                </div>
                {Object.keys(scores).length > 0 && (
                  <div className="admin-scores">
                    <span className="label">Held-out macro-F1</span>
                    {Object.entries(scores).map(([name, sc]) => (
                      <div key={name} className="admin-score">
                        <span className="small">{name}</span>
                        <span className="admin-score__bar" aria-hidden="true">
                          <i style={{ transform: `scaleX(${Math.min(1, sc.macro_f1)})` }} />
                        </span>
                        <span className="small mono">{sc.macro_f1.toFixed(3)}</span>
                      </div>
                    ))}
                  </div>
                )}
                {card.limitations?.length > 0 && (
                  <details className="admin-limits">
                    <summary className="small">Known limitations ({card.limitations.length})</summary>
                    <ul className="small muted" style={{ margin: "6px 0 0", paddingLeft: 18 }}>
                      {card.limitations.slice(0, 6).map((l, i) => (
                        <li key={i}>{l}</li>
                      ))}
                    </ul>
                  </details>
                )}
              </div>
            ) : (
              <p className="small muted">Loading…</p>
            )}
          </div>
        </div>

        {/* Hotspot monitoring */}
        <div className="card">
          <h2 className="card__title">
            <MapPin size={16} /> Fraud hotspot monitoring
          </h2>
          {points.length > 0 ? (
            <ScamMap
              points={points}
              scamTypes={scamTypes}
              height={440}
              enableFilters
              showUserLocation
            />
          ) : (
            <p className="small muted">Loading map…</p>
          )}
        </div>

        {/* Tenancy — organisations, users, audit trail. One implementation,
            shared with nothing else: `/reports` used to render a second user
            table with a second add-user form beside this one. */}
        <Organizations />
        <UserRoster />
        <AuditLog />
      </div>
    </div>
  );
}

function StatusRow({
  label,
  value,
  ok,
  detail,
}: {
  label: string;
  value: string;
  ok: boolean;
  detail?: string;
}) {
  return (
    <li className="admin-status__row">
      <span className={`admin-status__dot ${ok ? "is-ok" : "is-warn"}`} />
      <span className="small">{label}</span>
      <span className="admin-status__v small mono">{value}</span>
      {detail && <span className="admin-status__d small faint">{detail}</span>}
    </li>
  );
}
