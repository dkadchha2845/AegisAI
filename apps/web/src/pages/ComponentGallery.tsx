/**
 * The component gallery — every design-system component in one place, in
 * both themes and at any width (T-16, DESIGN_SYSTEM.md §6 and §9).
 *
 * A review surface, not a product page: no data is fetched and nothing is
 * submitted. Investigation-shaped examples come from the contract fixture
 * (`mock/investigation.json`, generated from `schema/mock_investigation.py`),
 * so the trace and the evidence viewer are rendered from the real contract
 * shape rather than from hand-written props. The sample screenshot is an
 * inline SVG drawn here and labelled as a sample. Use the theme toggle in the
 * header to see the other theme.
 */

import { useId, useState, type ReactNode } from "react";
import fixture from "@/mock/investigation.json";
import { AgentTrace } from "@/components/ui/AgentTrace";
import { Dropzone } from "@/components/ui/Dropzone";
import { EvidenceViewer } from "@/components/ui/EvidenceViewer";
import { Modal } from "@/components/ui/Modal";
import { PageHeader } from "@/components/ui/PageHeader";
import { RiskBadge } from "@/components/ui/RiskBadge";
import { RiskDial } from "@/components/ui/RiskDial";
import { StageTimeline } from "@/components/ui/StageTimeline";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/States";
import { ToastProvider, useToast } from "@/components/ui/Toast";
import type { InvestigationState } from "@/types/contract";

const SAMPLE = fixture as unknown as InvestigationState;

/** A drawn stand-in for a screenshot — labelled, so it is never mistaken for evidence. */
const SAMPLE_IMAGE =
  "data:image/svg+xml;utf8," +
  encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="480" height="200"><rect width="480" height="200" rx="14" fill="#1c2128"/>` +
      `<text x="24" y="44" fill="#9198a3" font-family="sans-serif" font-size="14">SAMPLE · VM-SBIKYC</text>` +
      `<text x="24" y="84" fill="#e8eaed" font-family="sans-serif" font-size="17">Your KYC has expired. Your account</text>` +
      `<text x="24" y="112" fill="#e8eaed" font-family="sans-serif" font-size="17">will be blocked in 24 hours. Verify at</text>` +
      `<text x="24" y="140" fill="#4d8dff" font-family="sans-serif" font-size="17">sbi-kyc-verify.top</text></svg>`,
  );

function Specimen({ id, title, note, children }: { id: string; title: string; note: string; children: ReactNode }) {
  return (
    <section className="card gallery__specimen" aria-labelledby={`g-${id}`}>
      <h2 className="card__title" id={`g-${id}`}>{title}</h2>
      <p className="small muted gallery__note">{note}</p>
      <div className="gallery__stage">{children}</div>
    </section>
  );
}

function ToastDemo() {
  const { show } = useToast();
  return (
    <div className="gallery__row">
      <button type="button" className="btn2" onClick={() => show({ title: "Report saved", body: "It is in My Reports.", tone: "ok" })}>
        Show a confirmation
      </button>
      <button type="button" className="btn2" onClick={() => show({ title: "Could not save the report", body: "The server did not answer. Try again.", tone: "bad" })}>
        Show an error
      </button>
    </div>
  );
}

function ModalDemo() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" className="btn2" onClick={() => setOpen(true)}>
        Open a dialog
      </button>
      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="Delete this saved report?"
        footer={
          <>
            <button type="button" className="btn2" onClick={() => setOpen(false)}>Cancel</button>
            <button type="button" className="btn2 btn2--danger" onClick={() => setOpen(false)}>Delete</button>
          </>
        }
      >
        <p>The report and its evidence package are removed for good. The case itself stays in the audit log.</p>
      </Modal>
    </>
  );
}

function DropzoneDemo() {
  const [taken, setTaken] = useState<string[]>([]);
  return (
    <div className="stack">
      <Dropzone
        accept={["image/*", ".pdf"]}
        maxBytes={4 * 1024 * 1024}
        maxFiles={3}
        onFiles={(files) => setTaken(files.map((f) => f.name))}
        hint="Screenshots or a PDF, up to 3 files of 4 MB. Try a larger file or a .zip to see a rejection."
      />
      {taken.length > 0 && <p className="small">Accepted: <span className="mono">{taken.join(", ")}</span></p>}
    </div>
  );
}

function InvalidFieldDemo() {
  const id = useId();
  return (
    <div>
      <label className="fieldlabel" htmlFor={id}>UPI ID</label>
      <input id={id} className="field" defaultValue="refund@" aria-invalid="true" aria-describedby={`${id}-msg`} />
      <p className="fieldmsg fieldmsg--bad" id={`${id}-msg`}>A UPI ID looks like name@bank — this one has no bank.</p>
    </div>
  );
}

export function ComponentGallery() {
  return (
    <ToastProvider>
      <div className="page">
        <PageHeader
          title="Components"
          lede="Every design-system component, rendered from contract-shaped data. Toggle the theme in the header; resize to phone width."
        />
        <div className="gallery">
          <Specimen id="riskbadge" title="Risk badge" note="Colour, label and number from one level and score. Unscored is never zero.">
            <div className="gallery__row">
              {(["CALM", "WATCH", "ELEVATED", "HIGH", "CRITICAL"] as const).map((level, i) => (
                <RiskBadge key={level} level={level} score={[8, 31, 55, 77, 93][i]} />
              ))}
              <RiskBadge level={null} score={null} />
            </div>
          </Specimen>

          <Specimen id="riskdial" title="Risk gauge" note="RiskDial. The live ThreatMeter is a second gauge for the same idea — gap G-09, a decision for the owner.">
            <div className="gallery__row">
              <RiskDial score={93} level="CRITICAL" />
              <RiskDial score={null} level={null} caption="Not scored is its own state." />
            </div>
          </Specimen>

          <Specimen id="timeline" title="Stage timeline" note="The seven arc stages: reached, current, ahead. Reached stages are buttons when the page can jump to their turn.">
            <StageTimeline
              current="ISOLATION"
              onSelect={() => undefined}
              visits={[
                { stage: "GREETING", at: 2, confidence: 0.81 },
                { stage: "AUTHORITY_CLAIM", at: 14, confidence: 0.92 },
                { stage: "FEAR_INDUCTION", at: 33, confidence: 0.74 },
                { stage: "ISOLATION", at: 61, confidence: 0.77 },
              ]}
            />
          </Specimen>

          <Specimen id="trace" title="Agent trace" note="From the contract fixture. A degraded, skipped or failed agent is shown as loudly as a successful one; rows open to findings, features and A7's verdict.">
            <AgentTrace results={SAMPLE.agent_results} />
          </Specimen>

          <Specimen id="evidence" title="Evidence viewer" note="The artefact beside what was read from it. The image is a drawn sample; the item and its OCR come from the fixture.">
            <div className="stack">
              <EvidenceViewer item={SAMPLE.inputs[0]} src={SAMPLE_IMAGE} extracted={SAMPLE.extracted_text} />
              <EvidenceViewer item={SAMPLE.inputs[1]} extracted={SAMPLE.extracted_text} />
            </div>
          </Specimen>

          <Specimen id="dropzone" title="Dropzone and invalid input" note="A real button that opens the native picker. Rejected files are named with their reason. Fields share one invalid pattern.">
            <div className="gallery__grid">
              <DropzoneDemo />
              <InvalidFieldDemo />
            </div>
          </Specimen>

          <Specimen id="overlays" title="Toast and modal" note="Toasts are announced, never focused, and pause while hovered. The dialog traps focus, closes on Escape, and returns focus.">
            <div className="gallery__row">
              <ToastDemo />
              <ModalDemo />
            </div>
          </Specimen>

          <Specimen id="states" title="Empty, loading and error states" note="The three states every async component above reuses.">
            <div className="gallery__grid">
              <EmptyState inline title="No saved reports yet." body="Reports you save from an analysis appear here." />
              <Skeleton lines={3} label="Loading reports" />
              <ErrorState inline title="Reports could not be loaded" detail="GET /api/reports → 503" onRetry={() => undefined} />
            </div>
          </Specimen>
        </div>
      </div>
    </ToastProvider>
  );
}
