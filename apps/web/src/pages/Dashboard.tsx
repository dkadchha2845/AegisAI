/**
 * Operations — what the platform is seeing, and the honest state of each part
 * of the machine that is seeing it.
 *
 * Two things changed here in the UI audit.
 *
 * **The bottom half is gone.** It was a grid of seven cards linking to the
 * seven sidebar destinations, with the same labels and the same icons. It
 * existed because the analyst tools were not in the sidebar at the time; now
 * that `navGroups` puts them there, a card grid restating the navigation is
 * furniture that pushes the actual content below the fold.
 *
 * **Measurements come first.** A dashboard opens with what is happening, not
 * with a configuration readout. The system-state panel is still here and
 * still above the fold — which classifier is serving changes how much weight
 * every other screen's output deserves, and a user who does not know the
 * fallback is active will read its results as if they came from the good
 * model — but it is no longer the *only* thing on the page.
 *
 * Every figure below is a contract field. There is no arithmetic in this file.
 */

import { useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/States";
import { count, formatInr } from "@/lib/format";
import { useHealth } from "@/hooks/useHealth";
import * as api from "@/lib/api";

/** Plain-language readings of the machine-readable `degraded` tags. The tags
 *  are for logs; this is for people. */
const DEGRADED_COPY: Record<string, string> = {
  "clf:lexical_fallback":
    "No fine-tuned checkpoint is present on this machine, so stage labels come "
    + "from the lexical model. (When the checkpoint *is* present it is measured "
    + "against the baseline and only promoted if it wins — so this tag means "
    + "‘not exported here’, not ‘the good model failed’.)",
  "rag:lexical":
    "Retrieval is using BM25 rather than dense embeddings. Citations are still "
    + "exact; ranking on paraphrased queries is weaker.",
  "rag:unavailable":
    "The knowledge base did not load. Verdicts will have no citations.",
  "twin:prior_only":
    "The Digital Twin has no fitted transition matrix and is using the canonical "
    + "stage order as a prior. Run ml/build_dataset.py.",
  "coercion:text_only":
    "No live audio, so prosodic stress features are absent. The coercion index is "
    + "capped lower to reflect that.",
  "llm:unavailable":
    "The LLM explainer was requested but could not be reached. Templated "
    + "explanations are being used instead.",
  "db:ephemeral":
    "No DATABASE_URL is configured, so saved cases, users, and the audit log "
    + "live in a temporary store that resets with the process. Point "
    + "DATABASE_URL at a file or Postgres to persist them.",
  "ocr:unavailable":
    "No OCR engine is installed, so screenshot analysis is disabled. Install "
    + "Tesseract (brew install tesseract) to enable it.",
  "asr:local_fallback":
    "Live audio transcription is not configured; transcripts come from text "
    + "input only.",
  "queue:no_workers":
    "No Celery worker is attached, so investigations run in-process. Results are "
    + "identical; throughput is one at a time.",
};

export function Dashboard() {
  const { data, loading, error } = useHealth();
  const [stats, setStats] = useState<api.IntelStats | null>(null);
  const [statsFailed, setStatsFailed] = useState(false);

  useEffect(() => {
    let live = true;
    void (async () => {
      const r = await api.getIntelStats();
      if (!live) return;
      if (r.ok) setStats(r.data);
      else setStatsFailed(true);
    })();
    return () => {
      live = false;
    };
  }, []);

  return (
    <div className="page">
      <PageHeader
        title="Operations"
        lede="What the platform is seeing right now, and the honest state of each part of it."
      />

      {/* --- What the platform is seeing ---------------------------------- */}
      <section className="statband" aria-label="Platform metrics">
        {stats ? (
          <>
            <Metric value={count(stats.total_cases)} label="fraud cases in the intelligence graph" />
            <Metric value={count(stats.active_clusters)} label="active clusters, each risk-scored" />
            <Metric value={count(stats.high_risk_clusters)} label="clusters scored high risk or worse" />
            <Metric value={count(stats.linked_entities)} label="linked entities — numbers, UPI IDs, wallets" />
            <Metric value={formatInr(stats.total_loss_inr)} label="reported exposure across those cases" />
          </>
        ) : statsFailed ? (
          <div className="stat" style={{ gridColumn: "1 / -1" }}>
            <p className="small muted" style={{ margin: 0 }}>
              Platform metrics are unavailable while the analysis service is unreachable.
            </p>
          </div>
        ) : (
          Array.from({ length: 5 }, (_, i) => (
            <div className="stat" key={i}>
              <Skeleton lines={2} label="Loading metrics" />
            </div>
          ))
        )}
      </section>

      {/* --- What the machine is running ---------------------------------- */}
      <section className="card" style={{ marginTop: "var(--s-6)" }}>
        <h2 className="card__title">System state</h2>

        {loading && <Skeleton lines={4} label="Checking the analysis service" />}

        {error && (
          <ErrorState
            inline
            title="The analysis service is not reachable"
            body={
              <>
                Every screen still renders and the console falls back to the recorded
                stream, but nothing here is live.
              </>
            }
            detail=".venv/bin/uvicorn services.api.main:app --reload --port 8000"
          />
        )}

        {data && (
          <>
            <div className="grid2">
              <div>
                <p className="label">Stage classifier</p>
                <dl className="kv">
                  <dt>backend</dt>
                  <dd>
                    <span className="chip" data-tone={data.classifier.serving_best ? "ok" : "warn"}>
                      {data.classifier.backend}
                      {data.classifier.serving_best && data.classifier.backend !== "muril"
                        ? " · best"
                        : ""}
                    </span>
                  </dd>
                  <dt>why</dt>
                  <dd className="faint">{data.classifier.reason}</dd>
                </dl>
              </div>

              <div>
                <p className="label">Retrieval</p>
                <dl className="kv">
                  <dt>backend</dt>
                  <dd>
                    <span className="chip" data-tone={data.retrieval.backend === "dense" ? "ok" : "warn"}>
                      {data.retrieval.backend}
                    </span>
                  </dd>
                  <dt>indexed</dt>
                  <dd>{data.retrieval.chunks} sections</dd>
                  <dt>documents</dt>
                  <dd className="faint">{data.retrieval.documents.join(", ")}</dd>
                </dl>
              </div>

              <div>
                <p className="label">Digital Twin</p>
                <dl className="kv">
                  <dt>fitted</dt>
                  <dd>
                    <span className="chip" data-tone={data.twin.fitted ? "ok" : "warn"}>
                      {data.twin.fitted ? "yes" : "prior only"}
                    </span>
                  </dd>
                  <dt>stages</dt>
                  <dd>{data.twin.stages.length}</dd>
                  <dt>best support</dt>
                  <dd>
                    {Object.entries(data.twin.support)
                      .sort((a, b) => b[1] - a[1])
                      .slice(0, 2)
                      .map(([k, v]) => `${k} n=${v}`)
                      .join(", ") || "—"}
                  </dd>
                </dl>
              </div>

              <div>
                <p className="label">Coach &amp; explanation</p>
                <dl className="kv">
                  <dt>coach lines</dt>
                  <dd>{data.coach.lines} curated</dd>
                  <dt>LLM</dt>
                  <dd>
                    <span className="chip" data-tone={data.llm.configured ? "ok" : undefined}>
                      {data.llm.configured ? data.llm.backend : "not configured"}
                    </span>
                  </dd>
                  <dt>contract</dt>
                  <dd>v{data.contract_version}</dd>
                </dl>
              </div>
            </div>

            {data.degraded.length > 0 ? (
              <div className="alert" data-tone="warn" style={{ marginTop: "var(--s-5)", display: "block" }}>
                <strong className="row alert__title" style={{ gap: 8 }}>
                  <RefreshCw size={15} aria-hidden="true" /> {data.degraded.length} component
                  {data.degraded.length > 1 ? "s are" : " is"} running degraded
                </strong>
                <ul style={{ margin: "var(--s-3) 0 0", paddingLeft: "1.1rem" }}>
                  {data.degraded.map((tag) => (
                    <li key={tag} className="small" style={{ marginBottom: 6 }}>
                      <span className="mono faint">{tag}</span> — {DEGRADED_COPY[tag] ?? "no description"}
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <div className="alert" data-tone="ok" style={{ marginTop: "var(--s-5)" }}>
                <span className="alert__title">Nothing is degraded.</span> Every component is
                serving its primary path.
              </div>
            )}
          </>
        )}

        {!loading && !error && !data && (
          <EmptyState
            inline
            title="No health reading yet"
            body="The analysis service answered, but with nothing to report."
          />
        )}
      </section>
    </div>
  );
}

function Metric({ value, label }: { value: string; label: string }) {
  return (
    <div className="stat">
      <div className="stat__n mono">{value}</div>
      <p className="stat__l">{label}</p>
    </div>
  );
}
