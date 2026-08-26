/**
 * Investigate — the launcher for task 1.6's lifecycle API, and the first reader
 * the per-node event stream has ever had.
 *
 * Everything an investigation needs has existed on the server since 1.6, and
 * until now nothing in the product could start one: submission was a `curl`
 * command. This page is the `/investigate` half of task 1.9 — evidence in,
 * observed progress while the graph runs, and a hand-off to the report.
 *
 * Three things about it are load-bearing rather than decorative.
 *
 * **The progress bar is not a timer.** Its denominator is `plan`, which the
 * server sends on `accepted` before any node has run, and its numerator is
 * `nodes_done`, which the server sends when a node has actually finished. Both
 * are contract fields. Nothing here interpolates, estimates or animates towards
 * a number it has not been told — 1.9's acceptance criterion says progress must
 * reflect real node completion, and the contract was shaped in 1.1 and 1.6 to
 * make that the easy thing to build. A tier that takes nine seconds shows as
 * nine seconds of nothing followed by a real completion, which is the truth.
 *
 * **A degraded agent is shown degraded.** Every agent that reports anything
 * other than `ok` is rendered with its status and its own error text. Hiding
 * them would make the run look cleaner than it was, and the whole point of
 * `AgentResult.status` existing as a field is that the UI cannot quietly round
 * it up.
 *
 * **No threat maths lives here.** The page renders `risk_score`, `risk_level`
 * and the report's own `scored` flag verbatim. An investigation the judgement
 * tier has not scored says so — it is never drawn as a risk of zero, which is
 * the distinction `investigations/report.py` refuses to collapse.
 *
 * The declared type of a pasted artefact is sent as `declared_type` and is
 * recorded, never trusted: the graph's classifier node decides what something
 * actually is from its bytes. The chooser below is therefore an affordance for
 * the person, not a routing decision, and the copy says so.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  CheckCircle2,
  CircleDashed,
  FileUp,
  IndianRupee,
  Link2,
  Loader2,
  Mail,
  MessageSquare,
  Phone,
  ShieldQuestion,
  Trash2,
} from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState, ErrorState } from "@/components/ui/States";
import { RiskDial } from "@/components/ui/RiskDial";
import * as api from "@/lib/api";
import type { AcceptedInvestigation, StreamEnd } from "@/lib/api";
import type {
  AgentResult,
  InvestigationEvent,
  InvestigationState,
} from "@/types/contract";

/* ------------------------------------------------------------------ input */

/** The paste affordances. `declared` is recorded by the server next to what the
 *  magic bytes actually say — their disagreement is itself evidence — and is
 *  never what routes the artefact. */
const PASTE_KINDS = [
  {
    id: "message",
    label: "Message",
    icon: MessageSquare,
    declared: "text/plain",
    placeholder:
      "Paste the SMS, WhatsApp message or email body exactly as you received it — "
      + "including the sender line if you have it.",
  },
  {
    id: "url",
    label: "Link",
    icon: Link2,
    declared: "text/uri-list",
    placeholder: "https://…",
  },
  {
    id: "phone",
    label: "Phone number",
    icon: Phone,
    declared: "text/x-phone",
    placeholder: "+91 98765 43210",
  },
  {
    id: "upi",
    label: "UPI ID",
    icon: IndianRupee,
    declared: "text/x-upi",
    placeholder: "someone@okaxis",
  },
  {
    id: "email",
    label: "Email header",
    icon: Mail,
    declared: "message/rfc822",
    placeholder: "Paste the full message source, including Received: lines.",
  },
] as const;

type PasteKind = (typeof PASTE_KINDS)[number]["id"];

/** Mirrors the server's `MAX_ITEMS`. A client-side count is a courtesy — intake
 *  enforces it, and a 413 says so — but refusing the ninth file before the
 *  upload starts is kinder than refusing it after four megabytes. */
const MAX_FILES = 8;

/* ------------------------------------------------------------------- page */

type Phase = "compose" | "running" | "done";

interface Progress {
  plan: string[];
  nodesDone: number;
  /** Every agent result the stream has delivered, in arrival order. Appended
   *  rather than replaced: each event carries this node's delta, so appending
   *  reconstructs the state's own list and a mid-run reconnect cannot
   *  double-count an earlier tier. */
  agents: AgentResult[];
  degraded: string[];
  status: string;
  error: string | null;
  /** The node each event reported, so the plan can be rendered as done/pending
   *  from what the server said rather than from an index we kept ourselves. */
  completed: string[];
}

const EMPTY_PROGRESS: Progress = {
  plan: [],
  nodesDone: 0,
  agents: [],
  degraded: [],
  status: "QUEUED",
  error: null,
  completed: [],
};

export function Investigate() {
  const [phase, setPhase] = useState<Phase>("compose");
  const [kind, setKind] = useState<PasteKind>("message");
  const [text, setText] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [accepted, setAccepted] = useState<AcceptedInvestigation | null>(null);
  const [progress, setProgress] = useState<Progress>(EMPTY_PROGRESS);
  const [final, setFinal] = useState<InvestigationState | null>(null);
  const [streamNote, setStreamNote] = useState<string | null>(null);

  const stopRef = useRef<(() => void) | null>(null);

  // A page that navigates away must not leave a reader attached to a live
  // response. The abort also settles the stream's own promise chain, so the
  // retry loop inside it stops rather than continuing against a dead component.
  useEffect(() => () => stopRef.current?.(), []);

  const active = PASTE_KINDS.find((k) => k.id === kind) ?? PASTE_KINDS[0];
  const canSubmit = !busy && (text.trim().length > 0 || files.length > 0);

  const addFiles = useCallback((incoming: FileList | File[]) => {
    setError(null);
    setFiles((current) => {
      const next = [...current];
      for (const file of Array.from(incoming)) {
        if (next.length >= MAX_FILES) {
          setError(`At most ${MAX_FILES} files per investigation.`);
          break;
        }
        // Same name and size twice is a double-drop, not two artefacts.
        if (next.some((f) => f.name === file.name && f.size === file.size)) continue;
        next.push(file);
      }
      return next;
    });
  }, []);

  const onEvent = useCallback((event: InvestigationEvent) => {
    setProgress((current) => ({
      // `plan` arrives on `accepted` and is empty on later events; keeping the
      // first non-empty one is what stops the denominator flickering to zero.
      plan: event.plan.length > 0 ? event.plan : current.plan,
      nodesDone: Math.max(current.nodesDone, event.nodes_done),
      agents: [...current.agents, ...event.agent_results],
      degraded: [...current.degraded, ...event.degraded],
      status: event.status,
      error: event.error ?? current.error,
      completed: event.node ? [...current.completed, event.node] : current.completed,
    }));
  }, []);

  const settle = useCallback(async (caseId: string, reason: StreamEnd, message?: string) => {
    if (reason === "aborted") return;
    if (reason !== "terminal") {
      // The stream stopped without telling us how it ended. The durable record
      // is the answer in that case, and saying which happened beats a spinner
      // that never resolves.
      setStreamNote(
        message
          ?? "The progress stream ended early; this is the case as the server has it.",
      );
    }
    const result = await api.getInvestigation(caseId);
    if (result.ok) setFinal(result.data);
    else setError(result.error);
    setPhase("done");
  }, []);

  const submit = async () => {
    setBusy(true);
    setError(null);
    setStreamNote(null);
    setProgress(EMPTY_PROGRESS);
    setFinal(null);

    const result = files.length
      ? await api.uploadInvestigation(files, text)
      : await api.createInvestigation({
          items: [{ text: text.trim(), declared_type: active.declared }],
        });

    setBusy(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }

    setAccepted(result.data);
    setProgress({ ...EMPTY_PROGRESS, status: result.data.status });
    setPhase("running");
    stopRef.current = api.streamInvestigation(result.data.case_id, {
      onEvent,
      onEnd: (reason, detail) => void settle(result.data.case_id, reason, detail.message),
    });
  };

  const reset = () => {
    stopRef.current?.();
    stopRef.current = null;
    setPhase("compose");
    setAccepted(null);
    setFinal(null);
    setProgress(EMPTY_PROGRESS);
    setStreamNote(null);
    setError(null);
    setText("");
    setFiles([]);
  };

  return (
    <div className={phase === "compose" ? "page page--doc" : "page page--wide"}>
      <PageHeader
        title="Investigate"
        lede={
          phase === "compose"
            ? "Submit evidence and watch the agent graph work through it. Every step is reported by the server as it actually completes — nothing here is a progress animation."
            : "Every step below is reported by the server as it actually completes."
        }
        actions={
          phase !== "compose" ? (
            <button type="button" className="btn2 btn2--ghost" onClick={reset}>
              Investigate something else
            </button>
          ) : undefined
        }
      />

      {phase === "compose" && (
        <Compose
          kind={kind}
          setKind={setKind}
          active={active}
          text={text}
          setText={setText}
          files={files}
          setFiles={setFiles}
          addFiles={addFiles}
          busy={busy}
          canSubmit={canSubmit}
          submit={submit}
          error={error}
        />
      )}

      {/* Once a run is under way the page becomes a workspace: what was
          submitted on the left, what the graph is doing in the middle, what it
          concluded on the right. Stacked, the verdict landed two scrolls below
          the evidence it was about. */}
      {phase !== "compose" && accepted && (
        <div className="workspace">
          <div className="workspace__col">
            <EvidencePanel text={text} files={files} kind={kind} state={final} />
          </div>

          <div className="workspace__col">
            <ProgressPanel
              accepted={accepted}
              progress={progress}
              phase={phase}
              note={streamNote}
            />
          </div>

          <div className="workspace__col workspace__col--verdict">
            <Outcome
              state={final}
              caseId={accepted.case_id}
              error={error}
              onReset={reset}
              pending={phase !== "done"}
            />
          </div>
        </div>
      )}
    </div>
  );
}

/* --------------------------------------------------------------- evidence */

/** What was actually submitted, kept on screen for the whole run.
 *
 *  `input_types` is what the classifier decided the bytes are; the declared
 *  kind is what the person said they were. Both are shown, because their
 *  disagreement is the signal the submit copy promises to record. */
function EvidencePanel({
  text,
  files,
  kind,
  state,
}: {
  text: string;
  files: File[];
  kind: PasteKind;
  state: InvestigationState | null;
}) {
  const detected = state?.input_types ?? [];
  return (
    <section className="card" aria-labelledby="inv-evidence">
      <h2 className="card__title" id="inv-evidence">Evidence</h2>

      {text.trim() ? (
        <>
          <p className="label">Submitted as {kind}</p>
          <blockquote className="inv__quote">{text.trim()}</blockquote>
        </>
      ) : null}

      {files.length > 0 && (
        <>
          <p className="label" style={{ marginTop: "var(--s-4)" }}>Attachments</p>
          <ul className="inv__files">
            {files.map((file) => (
              <li key={`${file.name}:${file.size}`}>
                <span className="inv__filename">{file.name}</span>
                <span className="mono faint">{formatBytes(file.size)}</span>
              </li>
            ))}
          </ul>
        </>
      )}

      {!text.trim() && files.length === 0 && (
        <EmptyState inline title="No evidence recorded" body="This case was submitted empty." />
      )}

      {detected.length > 0 && (
        <>
          <p className="label" style={{ marginTop: "var(--s-4)" }}>Detected from the bytes</p>
          <div className="row" style={{ gap: 6 }}>
            {detected.map((t) => (
              <span className="chip" key={t}>{t}</span>
            ))}
          </div>
        </>
      )}
    </section>
  );
}

/* ---------------------------------------------------------------- compose */

interface ComposeProps {
  kind: PasteKind;
  setKind: (k: PasteKind) => void;
  active: (typeof PASTE_KINDS)[number];
  text: string;
  setText: (t: string) => void;
  files: File[];
  setFiles: (f: File[] | ((current: File[]) => File[])) => void;
  addFiles: (incoming: FileList | File[]) => void;
  busy: boolean;
  canSubmit: boolean;
  submit: () => void;
  error: string | null;
}

function Compose(props: ComposeProps) {
  const { kind, setKind, active, text, setText, files, setFiles, addFiles } = props;
  const [over, setOver] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);

  return (
    <>
      <section className="card" aria-labelledby="ev-kind">
        <h2 className="card__title" id="ev-kind">What are you submitting?</h2>
        <p className="inv__hint">
          This chooses how to ask you for it — it does not decide what the
          evidence is. The classifier reads the bytes and records what you
          declared next to what it found, because a disagreement between the two
          is itself a signal.
        </p>
        {/* A real radiogroup, with the keyboard behaviour a radiogroup owes:
            one tab stop for the set, arrows to move within it, Home/End to the
            ends. Declaring `role="radio"` without that is worse than not
            declaring it — a screen-reader user is told to use arrow keys and
            then finds they do nothing. */}
        <div className="inv__kinds" role="radiogroup" aria-label="Evidence type">
          {PASTE_KINDS.map((option, index) => {
            const Icon = option.icon;
            const selected = option.id === kind;
            return (
              <button
                key={option.id}
                type="button"
                role="radio"
                aria-checked={selected}
                // Roving tabindex: only the selected option is in the tab order,
                // so Tab moves past the whole group rather than through five
                // stops of the same decision.
                tabIndex={selected ? 0 : -1}
                className="inv__kind"
                data-selected={selected || undefined}
                onClick={() => setKind(option.id)}
                onKeyDown={(e) => onKindKey(e, index, setKind)}
              >
                <Icon size={16} aria-hidden="true" />
                {option.label}
              </button>
            );
          })}
        </div>

        <label className="inv__label" htmlFor="ev-text">
          Paste the {active.label.toLowerCase()}
        </label>
        <textarea
          id="ev-text"
          className="field inv__textarea"
          rows={kind === "message" || kind === "email" ? 7 : 2}
          placeholder={active.placeholder}
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
      </section>

      <section className="card" aria-labelledby="ev-files">
        <h2 className="card__title" id="ev-files">Or attach files</h2>
        <p className="inv__hint">
          Screenshots, PDFs, emails, audio, an APK — up to {MAX_FILES}. An
          uploaded APK is analysed statically and never run. You can attach
          files and paste text in the same submission.
        </p>
        {/* A real button, not a div with a click handler: the dropzone has to be
            reachable by keyboard, and the file input it opens is the native one
            every assistive technology already understands. */}
        <button
          type="button"
          className="dropzone inv__drop"
          data-over={over || undefined}
          onClick={() => inputRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setOver(true);
          }}
          onDragLeave={() => setOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setOver(false);
            if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files);
          }}
        >
          <FileUp size={22} aria-hidden="true" />
          <span>Drop files here, or press to choose</span>
        </button>
        <input
          ref={inputRef}
          type="file"
          multiple
          className="inv__file"
          onChange={(e) => {
            if (e.target.files?.length) addFiles(e.target.files);
            e.target.value = "";
          }}
        />

        {files.length > 0 && (
          <ul className="inv__files">
            {files.map((file) => (
              <li key={`${file.name}:${file.size}`}>
                <span className="inv__filename">{file.name}</span>
                <span className="mono faint">{formatBytes(file.size)}</span>
                <button
                  type="button"
                  className="iconbtn"
                  aria-label={`Remove ${file.name}`}
                  onClick={() => setFiles((current) => current.filter((f) => f !== file))}
                >
                  <Trash2 size={14} aria-hidden="true" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="card inv__consent" aria-labelledby="ev-consent">
        <h2 className="card__title" id="ev-consent">
          <ShieldQuestion size={16} aria-hidden="true" /> Before you submit
        </h2>
        <ul className="inv__consentlist">
          <li>
            What you submit is stored as case evidence for your organisation and
            is readable by its members. Nobody outside it can read this case —
            not even a platform owner.
          </li>
          <li>
            Text extracted from a screenshot or a message is treated as data, never
            as instructions. It is quoted into the models as untrusted input.
          </li>
          <li>
            You can erase the case at any time. Erasure removes the rows, the
            stored bytes of every artefact, and the progress journal; an audit
            entry recording that you erased it is kept.
          </li>
        </ul>
      </section>

      {props.error && (
        <div className="alert" data-tone="bad" role="alert">
          <AlertTriangle size={16} aria-hidden="true" />
          <span>{props.error}</span>
        </div>
      )}

      <div className="actions">
        <button
          type="button"
          className="btn2 btn2--primary"
          disabled={!props.canSubmit}
          onClick={props.submit}
        >
          {props.busy ? <Loader2 size={16} className="spin" aria-hidden="true" /> : null}
          {props.busy ? "Submitting…" : "Start investigation"}
        </button>
        <span className="faint">
          {files.length > 0
            ? `${files.length} file${files.length === 1 ? "" : "s"} attached`
            : "Paste something or attach a file"}
        </span>
      </div>
    </>
  );
}

/* --------------------------------------------------------------- progress */

interface ProgressPanelProps {
  accepted: AcceptedInvestigation;
  progress: Progress;
  phase: Phase;
  note: string | null;
}

function ProgressPanel({ accepted, progress, phase, note }: ProgressPanelProps) {
  // The live region owns its own focus. Moving focus here when the panel first
  // appears is what makes the transition legible to a screen reader: the button
  // that was pressed has gone, and without this the focus ring lands on <body>.
  const liveRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    liveRef.current?.focus();
  }, []);

  const total = progress.plan.length;
  const done = Math.min(progress.nodesDone, total || progress.nodesDone);
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;
  const running = phase === "running";

  return (
    <section className="card" aria-labelledby="inv-progress">
      <h2 className="card__title" id="inv-progress">
        Case <span className="mono">{accepted.case_id}</span>
      </h2>

      {accepted.degraded.length > 0 && (
        <p className="inv__note">
          {accepted.degraded.includes("queue:in_process")
            ? "Running in the API process — there is no worker available, so a server restart would lose this run. The case file itself is already durable."
            : `Reduced capability: ${accepted.degraded.join(", ")}`}
        </p>
      )}

      {/* `aria-live="polite"` and not "assertive": a node completing is worth
          announcing, and worth announcing *after* whatever the reader is
          currently saying. tabIndex -1 so submit can move focus here. */}
      <div ref={liveRef} tabIndex={-1} aria-live="polite" className="inv__live">
        <div className="inv__bar" role="img" aria-label={`${done} of ${total || "?"} steps complete`}>
          <i style={{ width: `${pct}%` }} />
        </div>
        <p className="inv__count mono">
          {total > 0 ? `${done} of ${total} steps` : "Queued"}
          {running ? " · running" : ` · ${progress.status}`}
        </p>
      </div>

      {total > 0 && (
        <ol className="inv__plan">
          {progress.plan.map((node, index) => {
            // Done is decided by the server's own count, not by matching names:
            // the plan is ordered and the graph reports completions in order, so
            // an index below `nodesDone` has finished. Matching on `node` would
            // break the first time two tiers share a name.
            const complete = index < done;
            const current = running && index === done;
            return (
              <li key={node} data-state={complete ? "done" : current ? "now" : "wait"}>
                {complete ? (
                  <CheckCircle2 size={15} aria-hidden="true" />
                ) : current ? (
                  <Loader2 size={15} className="spin" aria-hidden="true" />
                ) : (
                  <CircleDashed size={15} aria-hidden="true" />
                )}
                <span className="mono">{prettyNode(node)}</span>
              </li>
            );
          })}
        </ol>
      )}

      {progress.agents.length > 0 && (
        <>
          <h3 className="inv__subhead">Agents</h3>
          <ul className="inv__agents">
            {progress.agents.map((agent, i) => (
              <AgentRow key={`${agent.agent}:${i}`} agent={agent} />
            ))}
          </ul>
        </>
      )}

      {progress.degraded.length > 0 && (
        <p className="inv__note" role="status">
          Reduced during this run: <span className="mono">{progress.degraded.join(", ")}</span>
        </p>
      )}

      {progress.error && (
        <div className="alert" data-tone="bad" role="alert">
          <AlertTriangle size={16} aria-hidden="true" />
          <span>{progress.error}</span>
        </div>
      )}

      {note && <p className="inv__note">{note}</p>}
    </section>
  );
}

/** One agent, with its status shown rather than rounded up.
 *
 *  An agent that degraded, skipped or errored is rendered exactly as loudly as
 *  one that succeeded, and its own `error` string is printed. 1.9's acceptance
 *  criterion is "degraded agents shown as degraded, not hidden", and the reason
 *  it is a criterion is that the alternative makes a run look better than it
 *  was — which is the same failure `degraded` exists on the contract to prevent.
 */
function AgentRow({ agent }: { agent: AgentResult }) {
  return (
    <li className="inv__agent" data-status={agent.status}>
      <span className="inv__agentname mono">{agent.agent}</span>
      <span className="chip" data-tone={toneOf(agent.status)}>{agent.status}</span>
      <span className="mono faint">{agent.latency_ms} ms</span>
      {agent.findings.length > 0 && (
        <span className="faint">
          {agent.findings.length} finding{agent.findings.length === 1 ? "" : "s"}
        </span>
      )}
      {agent.error && <span className="inv__agenterror">{agent.error}</span>}
    </li>
  );
}

/* ---------------------------------------------------------------- outcome */

function Outcome({
  state,
  caseId,
  error,
  onReset,
  pending,
}: {
  state: InvestigationState | null;
  caseId: string;
  error: string | null;
  onReset: () => void;
  pending: boolean;
}) {
  const scored = state?.risk_score != null && state?.risk_level != null;

  // While the graph is still running there is no verdict to draw, and drawing
  // an empty dial that later fills in would imply the score was climbing.
  // It was not: it arrives once, at the end, from the judgement tier.
  if (pending) {
    return (
      <section className="card" aria-labelledby="inv-outcome">
        <h2 className="card__title" id="inv-outcome">Verdict</h2>
        <EmptyState
          inline
          title="Still investigating"
          body="The verdict appears here once every agent has reported. It arrives as one reading — it does not climb while you watch."
        />
      </section>
    );
  }

  return (
    <section className="card" aria-labelledby="inv-outcome">
      <h2 className="card__title" id="inv-outcome">Verdict</h2>

      {error && <ErrorState inline title="This run did not finish" detail={error} onRetry={onReset} retryLabel="Start over" />}

      {state && (
        <>
          <RiskDial
            score={state.risk_score ?? null}
            level={state.risk_level ?? null}
            caption={
              scored
                ? undefined
                : "The judgement tier has no agents yet (tasks 4.6 and 4.7). Everything below it ran, and its findings are on the report."
            }
          />
          <dl className="kv" style={{ marginTop: "var(--s-4)" }}>
            <dt>Status</dt><dd className="mono">{state.status}</dd>
            <dt>Agents</dt><dd className="mono">{state.agent_results.length}</dd>
            <dt>Evidence items</dt><dd className="mono">{state.inputs.length}</dd>
            {state.degraded.length > 0 && (
              <>
                <dt>Degraded</dt>
                <dd className="mono">{state.degraded.join(", ")}</dd>
              </>
            )}
          </dl>
        </>
      )}

      <div className="actions" style={{ marginTop: "var(--s-4)" }}>
        <a
          className="btn2 btn2--block"
          href={api.investigationReportPdfUrl(caseId)}
          target="_blank"
          rel="noreferrer"
        >
          Download report (PDF)
        </a>
        <Link className="btn2 btn2--block" to="/reports">Open in My Reports</Link>
      </div>
    </section>
  );
}

/** Arrow/Home/End within the evidence-type group.
 *
 *  Selection follows focus, which is the pattern for a radiogroup whose options
 *  are cheap to preview: moving to "Link" selects it, and nothing is submitted
 *  until the button at the bottom is pressed. `focus()` on the new element is
 *  what actually moves the tab stop, because the roving tabindex above only
 *  describes where it should be. */
function onKindKey(
  event: React.KeyboardEvent,
  index: number,
  setKind: (k: PasteKind) => void,
): void {
  const last = PASTE_KINDS.length - 1;
  let next: number | null = null;
  if (event.key === "ArrowRight" || event.key === "ArrowDown") next = index === last ? 0 : index + 1;
  else if (event.key === "ArrowLeft" || event.key === "ArrowUp") next = index === 0 ? last : index - 1;
  else if (event.key === "Home") next = 0;
  else if (event.key === "End") next = last;
  if (next === null) return;

  event.preventDefault();
  setKind(PASTE_KINDS[next].id);
  const group = event.currentTarget.parentElement;
  const target = group?.children[next];
  if (target instanceof HTMLElement) target.focus();
}

/* ----------------------------------------------------------------- detail */

/** `investigate_stage` reads as machinery; "Investigate" reads as a step. The
 *  node names are the contract's, so they are transformed for display only and
 *  never re-derived into anything the server would disagree with. */
function prettyNode(node: string): string {
  const base = node.replace(/_stage$/, "").replace(/_/g, " ");
  return base.charAt(0).toUpperCase() + base.slice(1);
}

/** `skipped` deliberately returns nothing: the base chip is already muted, and
 *  an agent that was not eligible for this evidence is not a problem. `error`
 *  and `degraded` are distinct tones because they are distinct facts — one
 *  produced no answer, the other produced a worse one. */
function toneOf(status: string): string | undefined {
  if (status === "ok") return "ok";
  if (status === "degraded") return "warn";
  if (status === "error") return "bad";
  return undefined;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
