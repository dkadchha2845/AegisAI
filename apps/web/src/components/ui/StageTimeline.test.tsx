import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { StageTimeline } from "./StageTimeline";

const visits = [
  { stage: "GREETING" as const, at: 2, confidence: 0.81 },
  { stage: "AUTHORITY_CLAIM" as const, at: 14, confidence: 0.92 },
  { stage: "ISOLATION" as const, at: 61, confidence: 0.77 },
];

describe("StageTimeline", () => {
  it("draws the seven arc stages, marking reached, current and ahead", () => {
    render(<StageTimeline visits={visits} current="ISOLATION" />);
    const steps = screen.getAllByRole("listitem");
    expect(steps).toHaveLength(7);
    expect(steps[1]).toHaveAttribute("data-state", "reached");
    expect(steps[1]).toHaveTextContent("Authority claim14 s · 92%");
    expect(steps[3]).toHaveAttribute("aria-current", "step");
    expect(steps[5]).toHaveAttribute("data-state", "ahead");
    expect(screen.queryByText(/Benign/)).not.toBeInTheDocument();
  });

  it("makes reached stages buttons when asked, and only those", () => {
    const onSelect = vi.fn();
    render(<StageTimeline visits={visits} onSelect={onSelect} />);
    const buttons = screen.getAllByRole("button");
    expect(buttons).toHaveLength(3);
    fireEvent.click(screen.getByRole("button", { name: /Authority claim/ }));
    expect(onSelect).toHaveBeenCalledWith("AUTHORITY_CLAIM");
  });

  it("says no scam stage was reached rather than drawing an empty ladder", () => {
    render(<StageTimeline visits={[{ stage: "BENIGN" }]} />);
    expect(screen.getByText("No scam stage reached")).toBeInTheDocument();
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
  });

  it("has loading and error states", () => {
    const { rerender } = render(<StageTimeline visits={[]} loading />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading the stage timeline");
    const onRetry = vi.fn();
    rerender(<StageTimeline visits={[]} error="503" onRetry={onRetry} />);
    expect(screen.getByRole("alert")).toHaveTextContent("could not be loaded");
    fireEvent.click(screen.getByRole("button", { name: /Try again/ }));
    expect(onRetry).toHaveBeenCalled();
  });
});
