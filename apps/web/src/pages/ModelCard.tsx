/**
 * Model card — what the model is, what it was trained on, and where it fails.
 *
 * Served from the API rather than written into the frontend so it cannot
 * drift from the thing actually loaded. The limitations render as prominently
 * as the capabilities on purpose: a model card that only lists strengths is
 * marketing, and the honest version is what survives a judge asking how it
 * works.
 */

import { AlertTriangle, Cpu, GitBranch } from "lucide-react";
import { useEffect, useState } from "react";
import { PageHeader } from "@/components/ui/PageHeader";
import * as api from "@/lib/api";
import type { ModelCard as Card } from "@/lib/api";
import { useHealth } from "@/hooks/useHealth";
import { STAGE_BLURB, STAGE_ORDER, pretty, stageColor } from "@/lib/stages";

export function ModelCard() {
  const [card, setCard] = useState<Card | null>(null);
  const [error, setError] = useState<string | null>(null);
  const health = useHealth();

  useEffect(() => {
    api.getModelCard().then((res) => {
      if (res.ok) setCard(res.data);
      else setError(res.error);
    });
  }, []);

  return (
    <div className="page">
      <PageHeader
        title="Model card"
        lede="Read live from the running service, so this describes the model that is actually loaded rather than the one that was intended."
      />

      {error && (
        <div className="banner banner--bad">
          <AlertTriangle size={18} />
          <div className="small">{error}</div>
        </div>
      )}

      {card && (
        <>
          <section className="card">
            <h2 className="card__title row" style={{ gap: 8 }}>
              <Cpu size={17} /> {card.name}
            </h2>
            <dl className="kv">
              <dt>task</dt>
              <dd>{card.task}</dd>
              <dt>base model</dt>
              <dd>{card.base_model}</dd>
              <dt>serving</dt>
              <dd>
                <span
                  className="chip"
                  data-tone={card.active_backend === "muril" ? "ok" : "warn"}
                >
                  {card.active_backend}
                </span>
                {card.active_backend !== "muril" && (
                  <span className="small faint" style={{ marginLeft: 8 }}>
                    {/* The reason comes from the service. Hardcoding "run
                        ml/train.py" here told users to retrain a model that
                        had already been trained and deliberately not
                        promoted. */}
                    {card.evaluation?.selection ??
                      "no fine-tuned checkpoint exported yet"}
                  </span>
                )}
              </dd>
            </dl>
          </section>

          {card.evaluation?.scores && Object.keys(card.evaluation.scores).length > 0 && (
            <section className="card">
              <h2 className="card__title">Measured, not assumed</h2>
              <p className="muted small" style={{ marginTop: 0 }}>
                {card.evaluation.protocol}
              </p>
              <div className="statband" style={{ marginTop: "var(--s-4)" }}>
                {Object.entries(card.evaluation.scores).map(([backend, score]) => {
                  const best =
                    score.macro_f1 ===
                    Math.max(
                      ...Object.values(card.evaluation!.scores).map((s) => s.macro_f1),
                    );
                  return (
                    <div className="stat" key={backend}>
                      <div
                        className="stat__n"
                        style={{ color: best ? "var(--calm)" : "var(--ink-muted)" }}
                      >
                        {score.macro_f1.toFixed(3)}
                      </div>
                      <p className="stat__l">
                        <strong>{backend}</strong> macro-F1
                        {best ? " — currently serving" : ""}
                      </p>
                    </div>
                  );
                })}
              </div>
              <p className="small faint" style={{ marginTop: "var(--s-4)" }}>
                Selection: {card.evaluation.selection}. A checkpoint is promoted
                on measured evidence, not on the files existing — loading a model
                that loses to its own baseline would quietly make every verdict
                in the product worse.
              </p>
            </section>
          )}

          <section className="card">
            <h2 className="card__title">Training data</h2>
            <dl className="kv">
              {Object.entries(card.training_data).map(([k, v]) => (
                <div key={k} style={{ display: "contents" }}>
                  <dt>{k.replace(/_/g, " ")}</dt>
                  <dd style={{ fontFamily: "var(--font-body)", fontSize: "var(--t-sm)" }}>
                    {v}
                  </dd>
                </div>
              ))}
            </dl>
          </section>

          <section className="card">
            <h2 className="card__title row" style={{ gap: 8 }}>
              <AlertTriangle size={17} /> Limitations
            </h2>
            <ul className="small muted" style={{ paddingLeft: "1.1rem", lineHeight: 1.7 }}>
              {card.limitations.map((limit) => (
                <li key={limit}>{limit}</li>
              ))}
            </ul>
          </section>

          <section className="card">
            <h2 className="card__title row" style={{ gap: 8 }}>
              <GitBranch size={17} /> Digital Twin
            </h2>
            <dl className="kv">
              {Object.entries(card.twin).map(([k, v]) => (
                <div key={k} style={{ display: "contents" }}>
                  <dt>{k.replace(/_/g, " ")}</dt>
                  <dd style={{ fontFamily: "var(--font-body)", fontSize: "var(--t-sm)" }}>
                    {String(v)}
                  </dd>
                </div>
              ))}
            </dl>
            {health.data && (
              <p className="small faint" style={{ marginTop: "var(--s-4)" }}>
                Fitted sample counts per stage:{" "}
                {Object.entries(health.data.twin.support)
                  .sort((a, b) => b[1] - a[1])
                  .map(([k, v]) => `${k} n=${v}`)
                  .join(" · ") || "none"}
                . Stages below 20 samples are dropped rather than quoted.
              </p>
            )}
          </section>
        </>
      )}

      <section className="card">
        <h2 className="card__title">The label space</h2>
        <p className="muted small" style={{ marginTop: 0 }}>
          Eight labels, not more. Stages are speech acts, not topics — a single
          utterance gets exactly one label, chosen by what the speaker is trying
          to make happen. Every extra class costs recall on the two that matter.
        </p>
        <div className="stack" style={{ marginTop: "var(--s-4)" }}>
          {STAGE_ORDER.map((stage) => (
            <div
              className="arcstep"
              key={stage}
              style={{ ["--stage-color" as string]: stageColor(stage) }}
            >
              <span className="arcstep__n mono">
                {stage === "BENIGN" ? "—" : STAGE_ORDER.indexOf(stage) + 1}
              </span>
              <div>
                <span className="arcstep__label">{pretty(stage)}</span>
                <p className="arcstep__body">{STAGE_BLURB[stage]}</p>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
