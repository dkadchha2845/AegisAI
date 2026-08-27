/**
 * The researcher's dashboard — §27.
 *
 * Dataset statistics, measured model performance, and aggregated fraud trends.
 * Every figure is one field of `GET /api/research/overview`, which is the only
 * endpoint a researcher can reach and which never returns a case identifier, a
 * phone number, a UPI ID, an email address or any submitted text.
 *
 * **The page states what has not been measured.** If the promotion gate has not
 * been run on this machine there are no macro-F1 scores, and this renders that
 * as "not measured on this deployment" rather than as an empty chart or a zero.
 * A research surface that presents an unmeasured model as scoring 0.00 is worse
 * than one that says nothing — invariant 7, on a page whose whole audience is
 * people who will quote the number.
 *
 * **The privacy threshold is shown, not hidden.** How many clusters were
 * withheld for being too small is a property of the dataset a researcher needs
 * in order to reason about it, so it is on the page rather than in a docstring.
 */

import { useEffect, useState } from "react";
import { BrainCircuit, Database, FlaskConical, Lock, TrendingUp } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { ErrorState, Skeleton } from "@/components/ui/States";
import { formatInr } from "@/lib/format";
import * as api from "@/lib/api";
import type { ResearchOverview } from "@/lib/api";

export function ResearchDashboard() {
  const [data, setData] = useState<ResearchOverview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      const res = await api.getResearchOverview();
      if (res.ok) setData(res.data);
      else setError(res.error);
    })();
  }, []);

  if (error) {
    return (
      <div className="page page--doc">
        <PageHeader title="Research" lede="Datasets, model evaluation, and fraud trends." />
        <ErrorState title="Couldn't load the research overview" detail={error} />
      </div>
    );
  }

  const scores = Object.entries(data?.evaluation.scores ?? {});

  return (
    <div className="page">
      <PageHeader
        title="Research"
        lede="Aggregated fraud statistics and measured model performance. No case-level data, and no personally identifying information."
      />

      {/* --- Dataset ------------------------------------------------------ */}
      <div className="admin-kpis">
        {[
          { label: "Cases in the graph", value: data?.dataset.cases },
          { label: "Clusters", value: data?.dataset.clusters },
          { label: "Campaigns", value: data?.dataset.campaigns },
          { label: "Linked entities", value: data?.dataset.linked_entities },
        ].map((k) => (
          <div key={k.label} className="card admin-kpi">
            <Database size={18} className="admin-kpi__icon" aria-hidden="true" />
            <strong className="admin-kpi__v">
              {data ? k.value : "—"}
            </strong>
            <span className="small faint">{k.label}</span>
          </div>
        ))}
      </div>

      <div className="admin-grid">
        {/* --- Model ------------------------------------------------------ */}
        <section className="card">
          <h2 className="card__title">
            <BrainCircuit size={16} aria-hidden="true" /> Model
          </h2>
          {!data ? (
            <Skeleton lines={4} />
          ) : (
            <dl className="kv">
              <dt>Task</dt>
              <dd>{data.model.task}</dd>
              <dt>Base model</dt>
              <dd className="mono small">{data.model.base_model}</dd>
              <dt>Serving</dt>
              <dd>
                <span className="chip" data-tone={data.model.serving_best ? "ok" : "warn"}>
                  {data.model.serving}
                </span>
              </dd>
              <dt>Why this one</dt>
              <dd className="small muted">{data.model.selection_reason}</dd>
              <dt>Checkpoint loaded</dt>
              <dd>{data.model.checkpoint_backed ? "yes" : "no"}</dd>
            </dl>
          )}
        </section>

        {/* --- Evaluation ------------------------------------------------- */}
        <section className="card">
          <h2 className="card__title">
            <FlaskConical size={16} aria-hidden="true" /> Evaluation
          </h2>
          {!data ? (
            <Skeleton lines={3} />
          ) : !data.evaluation.measured ? (
            <>
              <p className="small muted" style={{ marginTop: 0 }}>
                <strong>Not measured on this deployment.</strong> The promotion
                gate has not been run here, so there are no held-out scores to
                report — and an unmeasured model must not be shown as one that
                scored zero.
              </p>
              <p className="small faint">
                Run <span className="mono">make eval</span> on a machine that has
                the checkpoint to produce them.
              </p>
            </>
          ) : (
            <>
              <p className="small muted" style={{ marginTop: 0 }}>
                {data.evaluation.protocol}
              </p>
              <div className="admin-scores">
                <span className="label">Held-out macro-F1</span>
                {scores.map(([name, sc]) => (
                  <div key={name} className="admin-score">
                    <span className="small">{name}</span>
                    <span className="admin-score__bar" aria-hidden="true">
                      <i style={{ transform: `scaleX(${Math.min(1, sc.macro_f1)})` }} />
                    </span>
                    <span className="small mono">{sc.macro_f1.toFixed(3)}</span>
                  </div>
                ))}
              </div>
            </>
          )}

          {data && (
            <dl className="kv" style={{ marginTop: "var(--s-4)" }}>
              <dt>Digital twin</dt>
              <dd>
                {data.twin.fitted ? (
                  <>
                    {data.twin.kind}, fitted over {data.twin.stages.length} stages
                    {" from "}
                    {Object.values(data.twin.support)
                      .reduce((a, b) => a + b, 0)
                      .toLocaleString()}{" "}
                    observed transitions.
                  </>
                ) : (
                  "Not fitted — using the canonical stage order as a prior."
                )}
              </dd>
            </dl>
          )}
        </section>
      </div>

      {/* --- Trends ------------------------------------------------------- */}
      <section className="card">
        <h2 className="card__title">
          <TrendingUp size={16} aria-hidden="true" /> Fraud trends
        </h2>
        {!data ? (
          <Skeleton lines={4} />
        ) : data.trends.length === 0 ? (
          <p className="small faint">
            No cluster is large enough to publish under the privacy threshold below.
          </p>
        ) : (
          <div className="cb-tablewrap">
            <table className="cb-table">
              <thead>
                <tr>
                  <th>Scam type</th>
                  <th>Clusters</th>
                  <th>Cases</th>
                  <th>Mean threat</th>
                  <th>Reported loss</th>
                </tr>
              </thead>
              <tbody>
                {data.trends.map((t) => (
                  <tr key={t.scam_type}>
                    <td>
                      <strong>{t.scam_name}</strong>
                      <br />
                      <span className="mono small faint">{t.scam_type}</span>
                    </td>
                    <td>{t.clusters}</td>
                    <td>{t.cases}</td>
                    <td className="mono">{t.mean_threat.toFixed(1)}</td>
                    <td>{formatInr(t.loss_inr)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* --- Privacy ------------------------------------------------------ */}
      {data && (
        <section className="card">
          <h2 className="card__title">
            <Lock size={16} aria-hidden="true" /> What this surface will not show you
          </h2>
          <p className="small muted" style={{ marginTop: 0 }}>{data.privacy.note}</p>
          <ul className="factlist">
            <li>
              <strong>{data.privacy.clusters_withheld} cluster(s) withheld</strong> for
              being smaller than {data.privacy.min_cluster_size} cases. A cluster of
              one is one person's case, and publishing its scam type and state is
              publishing that case.
            </li>
            <li>
              <strong>This is aggregation, not differential privacy.</strong> The
              threshold is a threshold; it is not a formal guarantee, and this
              project does not claim one.
            </li>
          </ul>
        </section>
      )}
    </div>
  );
}
