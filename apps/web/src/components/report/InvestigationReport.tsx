/**
 * InvestigationReport — the one report both journeys end in.
 *
 * Whether the evidence was pasted/uploaded (Analyze) or captured from a live
 * call (Live Protection), the outcome is the identical seven-section story:
 * Are you in danger? → Why? → How confident? → Has this happened before? →
 * Where? → What to do → Take action. The three research modules are fused into
 * one `VerifyResult` upstream; this component only tells the story.
 *
 * Extracted verbatim from the original Shield page so there is exactly one
 * implementation of the report — a second copy would drift.
 */

import {
  AlertTriangle,
  CheckCircle2,
  Circle,
  Download,
  FileText,
  Info,
  MapPin,
  Network,
  Phone,
  Save,
  Search,
  Share2,
  ShieldCheck,
} from "lucide-react";
import * as api from "@/lib/api";
import type { AnalysisResult, VerifyResult } from "@/lib/api";
import { ScamMap } from "@/components/map/ScamMap";
import { pretty, stageColor } from "@/lib/stages";

export const VERDICT_COPY: Record<string, string> = {
  LIKELY_SCAM: "This is very likely a scam",
  SUSPICIOUS: "This looks suspicious",
  LIKELY_LEGITIMATE: "No scam patterns detected",
  INSUFFICIENT: "Not enough to judge yet",
};

type ConfidenceSignal = { label: string; met: boolean };

function computeConfidence(result: VerifyResult): { pct: number; signals: ConfidenceSignal[] } {
  const signals: ConfidenceSignal[] = [
    { label: "Conversation", met: result.analysis.lines.length > 0 || result.analysis.findings.length > 0 },
    { label: "Known scam script", met: result.analysis.drivers.some((d) => d.label === "Script match") },
    { label: "Caller information", met: result.analysis.drivers.some((d) => d.label === "Number spoofing") },
    { label: "Previous reports", met: result.intel.clusters.length > 0 },
    { label: "Fraud database", met: result.intel.matched_entities.length > 0 || result.nearby_hotspots.length > 0 },
  ];
  const metCount = signals.filter((s) => s.met).length;
  return { pct: Math.round((metCount / signals.length) * 100), signals };
}

export function InvestigationReport({
  result,
  onPreserve,
  saving,
  token,
  note,
}: {
  result: VerifyResult;
  onPreserve: () => void;
  saving: boolean;
  token: string | null;
  /** Optional lead-in, e.g. "Generated from your live call." */
  note?: string;
}) {
  const em = result.emergency;
  const confidence = computeConfidence(result);
  const primaryHelpline = em.helplines.find((h) => h.value === "1930") ?? em.helplines.find((h) => h.priority === "primary");
  const shareText = `KAVACH check: ${VERDICT_COPY[result.verdict] ?? result.verdict} (${Math.round(result.score)}/100). ${result.summary}`;

  const share = async () => {
    if (navigator.share) {
      try {
        await navigator.share({ title: "KAVACH fraud check", text: shareText });
        return;
      } catch {
        // user cancelled the native share sheet — fall through to nothing
        return;
      }
    }
    window.open(`https://wa.me/?text=${encodeURIComponent(shareText)}`, "_blank", "noreferrer");
  };

  return (
    <div className="shield-narrative">
      {/* 1. Are you in danger? */}
      <section id="verdict" data-reveal>
        {note && (
          <p className="small faint" style={{ margin: "0 0 var(--s-3)" }}>
            {note}
          </p>
        )}
        {em.show_panic_banner && (
          <div className="panicbanner" style={{ marginBottom: "var(--s-4)" }}>
            <div className="panicbanner__head">
              <AlertTriangle size={18} /> {em.title}
            </div>
            <div className="panicbanner__helplines">
              {em.helplines
                .filter((h) => h.priority === "primary")
                .map((h) => (
                  <a
                    key={h.value}
                    className="helpbtn"
                    href={h.action}
                    target={h.action.startsWith("http") ? "_blank" : undefined}
                    rel="noreferrer"
                  >
                    <Phone size={14} /> {h.value}
                  </a>
                ))}
            </div>
          </div>
        )}
        <div className="verdict" data-v={result.verdict}>
          <div className="verdict__head">
            <span className="verdict__label">
              <AlertTriangle size={16} style={{ marginRight: 6, verticalAlign: -2 }} />
              {VERDICT_COPY[result.verdict] ?? result.verdict}
            </span>
            <span className="verdict__score">{Math.round(result.score)}</span>
          </div>
          <p className="verdict__summary">{result.summary}</p>
          <div className="row" style={{ gap: 6, marginTop: "var(--s-3)" }}>
            <span className="chip" data-risk={result.level}>
              {result.level}
            </span>
            {result.stage !== "BENIGN" && <span className="chip">Stage: {result.stage.replace(/_/g, " ").toLowerCase()}</span>}
            {result.intel.known_infrastructure && (
              <span className="chip" data-tone="bad">
                ⚠ Known fraud infrastructure
              </span>
            )}
          </div>
        </div>
      </section>

      {/* What KAVACH pulled out on its own — so the citizen sees it never had
          to be typed in. */}
      <DetectedEntities entities={result.extracted_entities} />

      {/* 2. Why do we think so? */}
      <section id="why" data-reveal>
        <div className="card">
          <h2 className="card__title">
            <Search size={16} /> Why do we think so?
          </h2>
          {result.analysis.drivers.length === 0 && result.analysis.findings.length === 0 ? (
            <p className="small muted" style={{ margin: 0 }}>
              Not enough signal in what you gave us to explain a verdict either way.
            </p>
          ) : (
            <>
              {result.analysis.drivers.length > 0 && (
                <ul className="findings">
                  {result.analysis.drivers.map((driver) => (
                    <li className="finding" data-v="UNKNOWN" key={driver.label}>
                      <div className="finding__label">
                        {driver.label} <span className="mono faint small">+{(driver.contribution * 100).toFixed(0)}</span>
                      </div>
                      <p className="finding__detail">{driver.detail}</p>
                    </li>
                  ))}
                </ul>
              )}
              {result.analysis.findings.length > 0 && (
                <ul className="findings" style={{ marginTop: result.analysis.drivers.length ? "var(--s-3)" : 0 }}>
                  {result.analysis.findings.map((finding, i) => (
                    <li className="finding" data-v={finding.verdict} key={`${finding.label}-${i}`}>
                      <div className="finding__label">{finding.label}</div>
                      <p className="finding__detail">{finding.detail}</p>
                      {finding.source && <div className="finding__src">↳ {finding.source}</div>}
                    </li>
                  ))}
                </ul>
              )}
              <TechnicalDetails analysis={result.analysis} />
            </>
          )}
        </div>
      </section>

      {/* 3. How confident are we? */}
      <section id="confidence" data-reveal>
        <div className="card confidence-card">
          <h2 className="card__title">
            <CheckCircle2 size={16} /> How confident are we?
          </h2>
          <div className="confidence-card__pct mono">{confidence.pct}%</div>
          <p className="small muted" style={{ marginTop: 0 }}>
            {confidence.signals.filter((s) => s.met).length} of {confidence.signals.length} independent signals agree —
            this reflects how many separate checks corroborate each other, separate from the verdict score above.
          </p>
          <ul className="confidence-signals">
            {confidence.signals.map((s) => (
              <li key={s.label} data-met={s.met || undefined}>
                {s.met ? <CheckCircle2 size={14} /> : <Circle size={14} />}
                <span>{s.label}</span>
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* 4. Has this happened before? */}
      <section id="network" data-reveal>
        <div className="card">
          <h2 className="card__title">
            <Network size={16} /> Has this happened before?
          </h2>
          {result.intel.matched_entities.length === 0 && result.intel.clusters.length === 0 ? (
            <p className="small muted" style={{ margin: 0 }}>
              Nothing matched — that's good news. This number, UPI ID, or message doesn't appear in any known fraud
              network yet.
            </p>
          ) : (
            <>
              {result.intel.matched_entities.length > 0 && (
                <div className="row" style={{ gap: 6, marginBottom: result.intel.clusters.length ? "var(--s-3)" : 0 }}>
                  {result.intel.matched_entities.map((e) => (
                    <span key={`${e.kind}-${e.value}`} className="chip" data-tone="bad">
                      {e.kind}: {e.value} · {e.case_count} case{e.case_count === 1 ? "" : "s"}
                    </span>
                  ))}
                </div>
              )}
              {result.intel.clusters.map((c) => (
                <div key={c.cluster_id} className="linkedcluster">
                  <span className="mono small">{c.cluster_id}</span>
                  <span className="small">{c.primary_scam}</span>
                  <span className="chip" data-risk={c.risk} style={{ marginLeft: "auto" }}>
                    {c.risk}
                  </span>
                  <p className="small faint" style={{ width: "100%", margin: "4px 0 0" }}>
                    This identifier appears in a {c.size}-case network across {c.states.join(", ")}.
                  </p>
                </div>
              ))}
            </>
          )}
        </div>
      </section>

      {/* 5. Where is this happening? */}
      <section id="hotspots" data-reveal>
        <div className="card">
          <h2 className="card__title">
            <MapPin size={16} /> Where is this happening?
          </h2>
          {result.nearby_hotspots.length === 0 ? (
            <p className="small muted" style={{ margin: 0 }}>
              No fraud hotspots reported near you yet — that's good news.
            </p>
          ) : (
            <>
              <ScamMap
                hotspots={result.nearby_hotspots}
                height={320}
                enableFilters
                showUserLocation
              />
              <div className="stack" style={{ gap: 6, marginTop: "var(--s-3)" }}>
                {result.nearby_hotspots.map((h) => (
                  <div key={h.name} className="row" style={{ justifyContent: "space-between" }}>
                    <span className="small">{h.name}</span>
                    <span className="chip" data-risk={h.risk}>
                      {h.cases} cases · {h.risk}
                    </span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </section>

      {/* 6. What should you do now? */}
      <section id="protect" data-reveal>
        <div className="card guidance-card">
          <h2 className="card__title">
            <ShieldCheck size={16} /> {result.guidance.headline}
          </h2>
          <ul className="actions">
            {result.guidance.actions.map((a, i) => (
              <li key={i}>{a}</li>
            ))}
          </ul>
          {result.guidance.coach_line && (
            <div className="coachline">
              <span className="label">Say this, out loud</span>
              <p className="coachline__quote">"{result.guidance.coach_line}"</p>
              {result.guidance.coach_why && <p className="small faint">{result.guidance.coach_why}</p>}
            </div>
          )}
        </div>
        <div className="card" style={{ marginTop: "var(--s-4)" }}>
          <h3 className="card__title" style={{ fontSize: "var(--t-base)" }}>
            {em.severity === "urgent" ? "Do this now" : "Immediate checklist"}
          </h3>
          <ul className="checklist">
            {em.checklist.map((c, i) => (
              <li key={i}>{c}</li>
            ))}
          </ul>
          <div className="row" style={{ gap: "var(--s-2)", marginTop: "var(--s-3)" }}>
            {em.helplines.map((h) => (
              <a
                key={h.value}
                className="btn2"
                href={h.action}
                target={h.action.startsWith("http") ? "_blank" : undefined}
                rel="noreferrer"
              >
                <Phone size={13} /> {h.name} · {h.value}
              </a>
            ))}
          </div>
        </div>
      </section>

      {/* 7. Take Action */}
      <section id="action" data-reveal>
        <div className="card">
          <h2 className="card__title">
            <FileText size={16} /> Take Action
          </h2>
          <div className="takeaction-grid">
            {primaryHelpline && (
              <a className="btn2 btn2--primary" href={primaryHelpline.action}>
                <Phone size={14} /> Call {primaryHelpline.value}
              </a>
            )}
            <button className="btn2" onClick={share}>
              <Share2 size={14} /> Share with family
            </button>
            {!token ? (
              <button className="btn2" onClick={onPreserve} disabled={saving}>
                <Save size={14} /> {saving ? "Saving…" : "Save evidence"}
              </button>
            ) : (
              <a className="btn2" href={api.complaintPdfUrl(token)} target="_blank" rel="noreferrer">
                <Download size={14} /> Download complaint (PDF)
              </a>
            )}
          </div>
          {token && (
            <div className="banner" style={{ marginTop: "var(--s-3)" }}>
              <div className="small">
                Evidence preserved. Keep this reference to reopen it: <span className="mono">{token.slice(0, 12)}…</span>
              </div>
            </div>
          )}
          <details className="blocknumber-tip" style={{ marginTop: "var(--s-4)" }}>
            <summary>
              <Info size={14} /> How do I block this number?
            </summary>
            <p className="small muted">
              KAVACH runs in your browser and can't block calls on your phone directly. On Android, open the Phone
              app, find this number in Recents, and choose "Block/report spam." On iPhone, open the number's contact
              card and choose "Block this Caller." Reporting it on 1930 also helps flag it for other citizens.
            </p>
          </details>
        </div>
      </section>
    </div>
  );
}

const ENTITY_GROUPS: { key: keyof NonNullable<VerifyResult["extracted_entities"]>; label: string }[] = [
  { key: "phones", label: "Phone" },
  { key: "upi_ids", label: "UPI" },
  { key: "emails", label: "Email" },
  { key: "websites", label: "Website" },
  { key: "bank_accounts", label: "Account" },
  { key: "banks", label: "Bank" },
  { key: "authorities", label: "Claimed" },
  { key: "locations", label: "Place" },
  { key: "scam_keywords", label: "Signal" },
  { key: "amounts", label: "Amount" },
];

function DetectedEntities({ entities }: { entities?: VerifyResult["extracted_entities"] }) {
  if (!entities) return null;
  const chips = ENTITY_GROUPS.flatMap((g) =>
    (entities[g.key] ?? []).map((v) => ({ label: g.label, value: v })),
  );
  if (chips.length === 0) return null;
  return (
    <section id="detected" data-reveal>
      <div className="card">
        <h2 className="card__title">
          <Search size={16} /> What we found in your evidence
        </h2>
        <p className="small muted" style={{ marginTop: 0 }}>
          KAVACH pulled these out automatically — you didn't have to type them.
        </p>
        <div className="row" style={{ gap: 6 }}>
          {chips.map((c, i) => (
            <span key={`${c.label}-${c.value}-${i}`} className="chip detected-chip">
              <span className="detected-chip__k">{c.label}</span> {c.value}
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}

function TechnicalDetails({ analysis }: { analysis: AnalysisResult }) {
  const hasPassport = analysis.trust_passport && analysis.trust_passport.checks.length > 0;
  const hasLines = analysis.lines.length > 1;
  if (!hasPassport && !hasLines) return null;
  return (
    <details className="technical-details" style={{ marginTop: "var(--s-3)" }}>
      <summary>See the technical details</summary>
      {hasPassport && analysis.trust_passport && (
        <div style={{ marginTop: "var(--s-3)" }}>
          <h3 className="card__title" style={{ fontSize: "var(--t-sm) " }}>
            Trust passport <span className="mono faint small">{analysis.trust_passport.final_trust_pct.toFixed(0)}%</span>
          </h3>
          {analysis.trust_passport.claimed_identity && (
            <p className="small muted" style={{ marginTop: 0 }}>
              Claims to be {analysis.trust_passport.claimed_identity}.
            </p>
          )}
          <ul className="findings">
            {analysis.trust_passport.checks.map((check) => (
              <li className="finding" data-v={check.verdict} key={check.name}>
                <div className="finding__label">
                  {check.name} <span className="mono faint small">{check.verdict}</span>
                </div>
                <p className="finding__detail">{check.detail}</p>
                {check.source && <div className="finding__src">↳ {check.source}</div>}
              </li>
            ))}
          </ul>
        </div>
      )}
      {hasLines && (
        <div style={{ marginTop: "var(--s-3)" }}>
          <h3 className="card__title" style={{ fontSize: "var(--t-sm)" }}>
            Line by line
          </h3>
          <div className="lines">
            {analysis.lines.map((line) => (
              <div className="linerow" key={line.index}>
                <span className="linerow__who">{line.speaker}</span>
                <span className="linerow__text">{line.text}</span>
                <span
                  className="linerow__stage"
                  style={{ ["--stage-color" as string]: stageColor(line.stage) }}
                  title={line.confidence ? `${(line.confidence * 100).toFixed(0)}% confident` : undefined}
                >
                  {line.stage === "—" ? "—" : pretty(line.stage)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </details>
  );
}
