import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ItemCard } from "../components/ItemCard";
import type { Item } from "../lib/types";

const base: Item = {
  id: 7, ref: "F-00007", kind: "found", name: "Blue bottle", category: "Bottles", location: "Library", description: "Dented lid",
  occurred_on: "2026-11-01", reported_at: "2026-11-02T10:00:00Z", status: "Available", photos: ["/media/item-image/1"],
  is_mine: false, campus: null, collection_point: null, can_claim: true, can_report_found: false,
};

describe("ItemCard", () => {
  it("shows name, category, place, date and status, and opens details", async () => {
    const onOpen = vi.fn();
    render(<ItemCard item={base} onOpen={onOpen} />);
    expect(screen.getByText("Bottles")).toBeInTheDocument();
    expect(screen.getByText("Library")).toBeInTheDocument();
    expect(screen.getByText(/Found .*2026/)).toBeInTheDocument();
    expect(screen.getByText("Available")).toBeInTheDocument();
    expect(screen.getByText("View details")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Blue bottle" }));
    expect(onOpen).toHaveBeenCalledWith(base);
  });

  it("labels each status in plain words", () => {
    const { rerender } = render(<ItemCard item={{ ...base, status: "Pending" }} onOpen={() => {}} />);
    expect(screen.getByText("Claim under review")).toBeInTheDocument();
    rerender(<ItemCard item={{ ...base, status: "Claimed" }} onOpen={() => {}} />);
    expect(screen.getByText("Awaiting pickup")).toBeInTheDocument();
    rerender(<ItemCard item={{ ...base, kind: "lost", status: "Available", photos: [] }} onOpen={() => {}} />);
    expect(screen.getByText("Lost")).toBeInTheDocument();
    expect(screen.getByLabelText("No photo")).toBeInTheDocument();
  });

  it("never renders private fields even if present", () => {
    render(<ItemCard item={{ ...base, secret_detail: "TOPSECRET", reported_by: "finder@x.edu" }} onOpen={() => {}} />);
    expect(screen.queryByText(/TOPSECRET/)).toBeNull();
    expect(screen.queryByText(/finder@x\.edu/)).toBeNull();
  });
});
