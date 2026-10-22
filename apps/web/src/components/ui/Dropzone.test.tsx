import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Dropzone } from "./Dropzone";

const png = (name = "sms.png", bytes = 2048) => new File([new Uint8Array(bytes)], name, { type: "image/png" });

function setup(extra: Partial<React.ComponentProps<typeof Dropzone>> = {}) {
  const onFiles = vi.fn();
  render(
    <Dropzone accept={["image/*", ".pdf"]} maxBytes={4096} maxFiles={2} onFiles={onFiles} hint="Images or a PDF, up to 4 KB." {...extra} />,
  );
  return onFiles;
}

describe("Dropzone", () => {
  it("is a real button that opens the native file input", () => {
    setup();
    const input = screen.getByTestId("dropzone-input") as HTMLInputElement;
    const click = vi.spyOn(input, "click");
    fireEvent.click(screen.getByRole("button", { name: /Drop a file here/ }));
    expect(click).toHaveBeenCalled();
    expect(input.accept).toBe("image/*,.pdf");
  });

  it("passes accepted files on, from a drop or from the picker", () => {
    const onFiles = setup();
    fireEvent.drop(screen.getByRole("button"), { dataTransfer: { files: [png()] } });
    expect(onFiles).toHaveBeenCalledWith([expect.objectContaining({ name: "sms.png" })]);
    fireEvent.change(screen.getByTestId("dropzone-input"), { target: { files: [png("b.png")] } });
    expect(onFiles).toHaveBeenLastCalledWith([expect.objectContaining({ name: "b.png" })]);
  });

  it("names each rejected file with its reason, and still passes the good ones", () => {
    const onFiles = setup();
    const exe = new File(["MZ"], "setup.exe", { type: "application/x-msdownload" });
    fireEvent.drop(screen.getByRole("button"), { dataTransfer: { files: [png("big.png", 9000), exe, png("ok.png")] } });
    expect(screen.getByText(/big\.png/).parentElement).toHaveTextContent("over the 4 KB limit");
    expect(screen.getByText(/setup\.exe/).parentElement).toHaveTextContent("this type is not accepted");
    expect(onFiles).toHaveBeenCalledWith([expect.objectContaining({ name: "ok.png" })]);
    expect(screen.getByRole("button")).toHaveAttribute("data-invalid", "true");
  });

  it("enforces the file count", () => {
    const onFiles = setup({ maxFiles: 1 });
    fireEvent.drop(screen.getByRole("button"), { dataTransfer: { files: [png("a.png"), png("b.png")] } });
    expect(onFiles).toHaveBeenCalledWith([expect.objectContaining({ name: "a.png" })]);
    expect(screen.getByText(/b\.png/).parentElement).toHaveTextContent("at most 1 file at a time");
  });

  it("does nothing while disabled", () => {
    const onFiles = setup({ disabled: true });
    expect(screen.getByRole("button")).toBeDisabled();
    fireEvent.drop(screen.getByRole("button"), { dataTransfer: { files: [png()] } });
    expect(onFiles).not.toHaveBeenCalled();
  });
});
