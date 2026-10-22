import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RiskBadge } from "./RiskBadge";

describe("RiskBadge", () => {
  it("shows the band's label and the number, and names both for a screen reader", () => {
    render(<RiskBadge level="CRITICAL" score={93.4} />);
    const badge = screen.getByLabelText("Risk 93 of 100, Critical");
    expect(badge).toHaveAttribute("data-risk", "CRITICAL");
    expect(badge).toHaveTextContent("Critical93");
  });

  it("uses the level it is given, never one derived from the number", () => {
    render(<RiskBadge level="WATCH" score={95} />);
    expect(screen.getByLabelText("Risk 95 of 100, Watch")).toHaveAttribute("data-risk", "WATCH");
  });

  it("says 'Not scored' rather than drawing a zero", () => {
    render(<RiskBadge level={null} score={null} />);
    expect(screen.getByText("Not scored")).toBeInTheDocument();
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });

  it("can drop the number for a table that shows it elsewhere", () => {
    render(<RiskBadge level="HIGH" score={71} hideScore />);
    expect(screen.getByLabelText("Risk 71 of 100, High")).toHaveTextContent(/^High$/);
  });
});
