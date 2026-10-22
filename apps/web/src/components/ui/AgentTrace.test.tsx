import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { AgentResult } from "@/types/contract";
import { AgentTrace } from "./AgentTrace";

const results: AgentResult[] = [
  {
    agent: "trust_passport", version: "1.0.0", status: "ok", confidence: 0.5, latency_ms: 20,
    provenance: ["trust_passport"], error: null, features: { trust_pct: 0, passport_fails: 2 },
    findings: [
      { label: "passport_fail", value: "Secrecy demand", confidence: 1, source: "kb", detail: "required secrecy",
        verification: { verdict: "DOWNGRADED", reason: "single agent", challenger: "deterministic:uncorroborated",
          confidence_before: 1, confidence_after: 0.6, weight: 0.6 } },
    ],
  },
  {
    agent: "number_spoofing", version: "1.0.0", status: "error", confidence: 0, latency_ms: 8000,
    provenance: [], error: "TimeoutError: lookup", features: {}, findings: [],
  },
  {
    agent: "coercion_tracker", version: "1.0.0", status: "skipped", confidence: 0, latency_ms: 0,
    provenance: [], error: null, features: {}, findings: [],
  },
];

describe("AgentTrace", () => {
  it("shows every agent, a failure as loudly as a success", () => {
    render(<AgentTrace results={results} />);
    const rows = screen.getAllByRole("button");
    expect(rows).toHaveLength(3);
    expect(rows[1]).toHaveTextContent("number_spoofing");
    expect(rows[1]).toHaveTextContent("error");
    expect(rows[2]).toHaveTextContent("skipped");
  });

  it("opens a row by keyboard-operable button to what the agent found", () => {
    render(<AgentTrace results={results} />);
    const head = screen.getByRole("button", { name: /trust_passport/ });
    expect(head).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByText("Secrecy demand")).not.toBeVisible();
    fireEvent.click(head);
    expect(head).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Secrecy demand")).toBeVisible();
    expect(screen.getByText("trust_pct")).toBeVisible();
    expect(screen.getByText(/A7 downgraded this \(100% → 60%\): single agent/)).toBeVisible();
  });

  it("shows why an agent failed", () => {
    render(<AgentTrace results={results} />);
    fireEvent.click(screen.getByRole("button", { name: /number_spoofing/ }));
    expect(screen.getByText("TimeoutError: lookup")).toBeVisible();
  });

  it("has loading, empty and error states", () => {
    const { rerender } = render(<AgentTrace results={[]} loading />);
    expect(screen.getByRole("status", { busy: true })).toBeInTheDocument();
    rerender(<AgentTrace results={[]} />);
    expect(screen.getByText("No agent has reported yet")).toBeInTheDocument();
    rerender(<AgentTrace results={[]} error="502" />);
    expect(screen.getByRole("alert")).toHaveTextContent("could not be loaded");
  });
});
