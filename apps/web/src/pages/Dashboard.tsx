/**
 * Dashboard — the hub. What is loaded, what is degraded, where to go next.
 *
 * The system-state panel is first, above the navigation cards, on purpose.
 * Which classifier is serving and whether retrieval is dense or lexical
 * changes how much weight every other screen's output deserves, and a user who
 * does not know the fallback is active will read its results as if they came
 * from the good model.
 */

import { Link } from "react-router-dom";
import { ArrowRight, RefreshCw } from "lucide-react";
import { NAV } from "@/components/layout/nav";
import { useHealth } from "@/hooks/useHealth";

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
};

export function Dashboard() {
  const { data, loading, error } = useHealth();

  return (
    <div className="page">
      <header className="page__head">
        <p className="label">Overview</p>
        <h1 className="page__title">Dashboard</h1>
        <p className="page__lede">
          Everything this build can do, and the honest state of each part of it.
          Press <kbd>⌘K</kbd> from anywhere to jump between screens.
        </p>
      </header>

      <section className="card" style={{ marginBottom: "var(--s-6)" }}>
        <h2 className="card__title">System state</h2>

        {loading && (
          <p className="row muted small">
            <span className="spinner" /> Checking the analysis service…
          </p>
        )}

        {error && (
          <div className="banner banner--bad">
            <div>
              <strong>The analysis service is not reachable.</strong>
              <p className="small" style={{ margin: "6px 0 0" }}>
                Every screen still renders, and the console falls back to the
                recorded demo stream — but nothing here is live. Start it with:
              </p>
              <p className="mono small" style={{ margin: "8px 0 0" }}>
                .venv/bin/uvicorn services.api.main:app --reload --port 8000
              </p>
            </div>
          </div>
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
                <p className="label">Coach & explanation</p>
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

            {data.degraded.length > 0 && (
              <div className="banner" style={{ marginTop: "var(--s-5)", display: "block" }}>
                <strong className="row" style={{ gap: 8 }}>
                  <RefreshCw size={15} /> {data.degraded.length} component
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
            )}
          </>
        )}
      </section>

      <section style={{ marginBottom: "var(--s-6)" }}>
        <p className="label" style={{ marginBottom: "var(--s-3)" }}>
          Go to
        </p>
        <div className="grid2">
          {NAV.map((item) => (
            <Link key={item.to} to={item.to} className="featurecard">
              <span className="featurecard__icon">
                <item.icon size={17} />
              </span>
              <span className="featurecard__label">{item.label}</span>
              <p className="featurecard__detail">{item.detail}</p>
              <span className="featurecard__go">
                Open <ArrowRight size={13} />
              </span>
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}
