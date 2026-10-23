import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import * as api from "@/lib/api";
import { AuditLog, Organizations } from "./Tenancy";

// A failed load used to leave the skeleton up for good: an organisation admin
// opening the dashboard got 403 from /api/orgs and a card that never finished
// loading. A failure is a state of its own, with the server's reason and a retry.

const forbidden = { ok: false as const, error: "You do not have permission to do that.", status: 403 };

describe("Tenancy panels", () => {
  it("shows why the organisations could not be loaded, instead of loading forever", async () => {
    vi.spyOn(api, "listOrgs").mockResolvedValue(forbidden);
    render(<Organizations />);
    expect(await screen.findByText("Organisations could not be loaded")).toBeInTheDocument();
    expect(screen.getByText(forbidden.error)).toBeInTheDocument();
  });

  it("retries, and shows the table once the server answers", async () => {
    const list = vi.spyOn(api, "listOrgs").mockResolvedValueOnce(forbidden).mockResolvedValueOnce({
      ok: true,
      data: { organizations: [{ id: 1, slug: "aegis", name: "AegisAI (default)", created_at: null, members: 3, cases: 1 }] },
    });
    render(<Organizations />);
    fireEvent.click(await screen.findByRole("button", { name: /try again/i }));
    expect(await screen.findByText("AegisAI (default)")).toBeInTheDocument();
    expect(screen.queryByText("Organisations could not be loaded")).not.toBeInTheDocument();
    expect(list).toHaveBeenCalledTimes(2);
  });

  it("does the same for the activity log", async () => {
    vi.spyOn(api, "getAudit").mockResolvedValue({ ok: false, error: "GET /api/audit → 503", status: 503 });
    render(<AuditLog />);
    await waitFor(() => expect(screen.getByText("The activity log could not be loaded")).toBeInTheDocument());
  });
});
