/**
 * The dial renders contract fields and decides nothing (invariant 2) — and an
 * unscored case is never drawn as a risk of zero.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RiskDial } from "./RiskDial";

function litTicks(container: HTMLElement): number {
  return container.querySelectorAll("line[data-lit]").length;
}

describe("RiskDial", () => {
  it("shows the score and level it was given, verbatim", () => {
    const { container } = render(<RiskDial score={93} level="CRITICAL" />);
    expect(screen.getByRole("img")).toHaveAccessibleName("Risk 93 out of 100, level CRITICAL");
    expect(screen.getByText("93")).toBeInTheDocument();
    expect(screen.getByText("CRITICAL")).toBeInTheDocument();
    expect(litTicks(container)).toBe(19);
  });

  it("draws an unscored case as 'Not scored', never as zero", () => {
    const { container } = render(<RiskDial score={null} level={null} />);
    expect(screen.getByRole("img")).toHaveAccessibleName("Not scored");
    expect(screen.getByText("Not scored")).toBeInTheDocument();
    expect(screen.queryByText("0")).not.toBeInTheDocument();
    expect(litTicks(container)).toBe(0);
  });

  it("keeps confidence separate from the score", () => {
    render(<RiskDial score={40} level="WATCH" confidence={0.25} caption="Provisional, uncalibrated score." />);
    expect(screen.getByText("40")).toBeInTheDocument();
    expect(screen.getByText("25%")).toBeInTheDocument();
    expect(screen.getByText("Provisional, uncalibrated score.")).toBeInTheDocument();
  });
});
