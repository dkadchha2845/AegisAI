import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DEFAULT_DURATION, ToastProvider, useToast } from "./Toast";

function Trigger({ tone }: { tone?: "info" | "ok" | "bad" }) {
  const { show } = useToast();
  return (
    <button type="button" onClick={() => show({ title: "Report saved", body: "In My Reports.", tone })}>
      Save
    </button>
  );
}

function setup(tone?: "info" | "ok" | "bad") {
  render(
    <ToastProvider>
      <Trigger tone={tone} />
    </ToastProvider>,
  );
  const trigger = screen.getByText("Save");
  trigger.focus();
  fireEvent.click(trigger);
}

describe("Toast", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("is announced in a polite live region, without taking focus", () => {
    setup();
    expect(screen.getByRole("region", { name: "Notifications" })).toHaveAttribute("aria-live", "polite");
    expect(screen.getByRole("status")).toHaveTextContent("Report saved");
    expect(document.activeElement).toBe(screen.getByText("Save"));
  });

  it("dismisses itself, but not while it is hovered", () => {
    setup();
    const toast = screen.getByRole("status");
    fireEvent.mouseEnter(toast);
    act(() => vi.advanceTimersByTime(DEFAULT_DURATION * 2));
    expect(screen.getByRole("status")).toBeInTheDocument();
    fireEvent.mouseLeave(toast);
    act(() => vi.advanceTimersByTime(DEFAULT_DURATION + 10));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("closes from its button and from Escape", () => {
    setup();
    fireEvent.click(screen.getByRole("button", { name: "Dismiss notification" }));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("Save"));
    fireEvent.keyDown(screen.getByRole("status"), { key: "Escape" });
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("raises an error as an alert", () => {
    setup("bad");
    expect(screen.getByRole("alert")).toHaveTextContent("Report saved");
  });
});
