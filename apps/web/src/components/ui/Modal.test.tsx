import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { Modal } from "./Modal";

function Harness({ dismissable = true }: { dismissable?: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>Open</button>
      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="Delete this report?"
        dismissable={dismissable}
        footer={
          <>
            <button type="button" onClick={() => setOpen(false)}>Cancel</button>
            <button type="button">Delete</button>
          </>
        }
      >
        <p>It cannot be recovered.</p>
      </Modal>
    </>
  );
}

function open() {
  const opener = screen.getByText("Open");
  opener.focus();
  fireEvent.click(opener);
  return opener;
}

describe("Modal", () => {
  it("is a named, modal dialog that takes focus", () => {
    render(<Harness />);
    open();
    const dialog = screen.getByRole("dialog", { name: "Delete this report?" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toContainElement(document.activeElement as HTMLElement);
  });

  it("traps Tab and Shift+Tab inside", () => {
    render(<Harness />);
    open();
    const dialog = screen.getByRole("dialog");
    const close = screen.getByRole("button", { name: "Close" });
    const last = screen.getByText("Delete");
    last.focus();
    fireEvent.keyDown(dialog, { key: "Tab" });
    expect(document.activeElement).toBe(close);
    fireEvent.keyDown(dialog, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(last);
  });

  it("closes on Escape and returns focus to what opened it", () => {
    render(<Harness />);
    const opener = open();
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(document.activeElement).toBe(opener);
  });

  it("closes on a backdrop click, but not on a click inside", () => {
    render(<Harness />);
    open();
    fireEvent.mouseDown(screen.getByText("It cannot be recovered."));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    fireEvent.mouseDown(document.querySelector(".modal__backdrop") as Element);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("a step that must be answered ignores Escape and has no close button", () => {
    render(<Harness dismissable={false} />);
    open();
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Close" })).not.toBeInTheDocument();
  });
});
