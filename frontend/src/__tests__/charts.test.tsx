import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BarList, LineChart } from "../components/charts";

const rows = [
  { month: "2026-09", found: 3, lost: 1, returned: 0 },
  { month: "2026-10", found: 5, lost: 2, returned: 4 },
];
const series = [
  { key: "found", label: "Found", color: "var(--series-1)" },
  { key: "lost", label: "Lost", color: "var(--series-2)" },
  { key: "returned", label: "Returned", color: "var(--series-3)" },
];

describe("charts", () => {
  it("line chart has a legend, end labels and a table view with every value", async () => {
    render(<LineChart title="Items per month" rows={rows} xKey="month" series={series} />);
    expect(screen.getByRole("img", { name: /Items per month/ })).toBeInTheDocument();
    expect(screen.getByText("Returned 4")).toBeInTheDocument();          // direct end label
    await userEvent.click(screen.getByRole("button", { name: "Show table" }));
    const cells = screen.getAllByRole("cell").map((c) => c.textContent);
    expect(cells).toEqual(expect.arrayContaining(["3", "1", "0", "5", "2", "4"]));
  });

  it("bar list shows values and notes, and an empty message", () => {
    const { rerender } = render(<BarList title="By category" rows={[{ label: "Keys", value: 2, note: "1 recovered" }]} />);
    expect(screen.getByText("Keys")).toBeInTheDocument();
    expect(screen.getByTitle("Keys: 2 (1 recovered)")).toBeInTheDocument();
    rerender(<BarList title="By category" rows={[]} />);
    expect(screen.getByText("No items in this period.")).toBeInTheDocument();
  });
});
