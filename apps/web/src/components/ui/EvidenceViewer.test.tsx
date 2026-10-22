import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { EvidenceItem, ExtractedText } from "@/types/contract";
import { EvidenceViewer } from "./EvidenceViewer";

const shot: EvidenceItem = {
  id: "ev-1", kind: "SCREENSHOT", filename: "sms.png", declared_type: "image/jpeg", media_type: "image/png",
  size_bytes: 30768, sha256: "a".repeat(64), uri: "s3://x/ev-1.png", text: null, received_at: null,
};
const ocr: ExtractedText[] = [
  { source_ref: "ev-1", text: "Pay Rs 4999 <script>alert(1)</script> <b>now</b>", language: "en", confidence: 0.62, extractor: "ocr:tesseract" },
  { source_ref: "ev-2", text: "another item", language: null, confidence: 1, extractor: "verbatim" },
];

describe("EvidenceViewer", () => {
  it("shows the artefact beside what was read from it, with extractor and confidence", () => {
    render(<EvidenceViewer item={shot} src="blob:x" extracted={ocr} />);
    expect(screen.getByAltText("Submitted evidence: sms.png")).toHaveAttribute("src", "blob:x");
    expect(screen.getByText("ocr:tesseract")).toBeInTheDocument();
    expect(screen.getByText("62% confidence")).toBeInTheDocument();
    expect(screen.queryByText("another item")).not.toBeInTheDocument();
  });

  it("renders evidence text as text, never as markup", () => {
    const { container } = render(<EvidenceViewer item={shot} src="blob:x" extracted={ocr} />);
    expect(container.querySelector("script, b")).toBeNull();
    expect(screen.getByLabelText("Text read by ocr:tesseract")).toHaveTextContent("<script>alert(1)</script> <b>now</b>");
  });

  it("shows a declared-versus-detected type mismatch, because it is a finding", () => {
    render(<EvidenceViewer item={shot} src="blob:x" />);
    expect(screen.getByText(/but the bytes are/)).toHaveTextContent("Declared image/jpeg, but the bytes are image/png");
  });

  it("plays a recording with native controls, and scrolls text by keyboard", () => {
    const audio = { ...shot, kind: "AUDIO" as const, filename: "call.wav", media_type: "audio/wav", declared_type: "audio/wav" };
    const { container } = render(<EvidenceViewer item={audio} src="blob:a" extracted={ocr} />);
    expect(container.querySelector("audio[controls]")).not.toBeNull();
    expect(screen.getByLabelText("Text read by ocr:tesseract")).toHaveAttribute("tabindex", "0");
  });

  it("without bytes, shows metadata and says there is no preview", () => {
    render(<EvidenceViewer item={shot} />);
    expect(screen.getByText("No preview")).toBeInTheDocument();
    expect(screen.getByText("ev-1")).toBeInTheDocument();
  });

  it("has loading and error states", () => {
    const { rerender } = render(<EvidenceViewer item={shot} loading />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading the evidence");
    rerender(<EvidenceViewer item={shot} error="404" />);
    expect(screen.getByRole("alert")).toHaveTextContent("could not be loaded");
  });
});
