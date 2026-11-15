import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Modal } from "../components/Modal";

describe("Modal", () => {
  it("is a labelled dialog that closes on Escape and the close button", async () => {
    const onClose = vi.fn();
    render(<Modal open title="Report an item" onClose={onClose}><input aria-label="Name" /></Modal>);
    expect(screen.getByRole("dialog", { name: "Report an item" })).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    await userEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it("renders nothing when closed", () => {
    render(<Modal open={false} title="Hidden" onClose={() => {}}>x</Modal>);
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
