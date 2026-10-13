import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import type { TagRow } from "../bulk-tags";
import { BulkTagPicker } from "../ui/bulk-tag-picker";

const ROWS: TagRow[] = [
  { tag: "good", count: 3, presence: "all", check: "checked" },
  { tag: "retry", count: 1, presence: "some", check: "mixed" },
  { tag: "blurry", count: 2, presence: "some", check: "unchecked" },
  { tag: "reviewed", count: 0, presence: "none", check: "checked" },
];

/** Renders the picker with the draft held in state, as the dialog does. */
function renderPicker(rows: TagRow[] = ROWS) {
  const onToggle = vi.fn();
  const onAdd = vi.fn();
  function Harness() {
    const [draft, setDraft] = useState("");
    return (
      <BulkTagPicker rows={rows} total={3} draft={draft} onDraftChange={setDraft} onToggle={onToggle} onAdd={onAdd} />
    );
  }
  render(<Harness />);
  return { onToggle, onAdd };
}

describe("BulkTagPicker", () => {
  it("renders one tri-state checkbox per row with its count", () => {
    renderPicker();

    expect(screen.getByRole("checkbox", { name: "good" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("checkbox", { name: "retry" })).toHaveAttribute("aria-checked", "mixed");
    expect(screen.getByRole("checkbox", { name: "blurry" })).toHaveAttribute("aria-checked", "false");
    expect(screen.getByText("1/3")).toBeInTheDocument();
  });

  it("labels the rows that saving will change", () => {
    renderPicker();

    expect(screen.getAllByText("→ add to all")).toHaveLength(1);
    expect(screen.getAllByText("→ remove from all")).toHaveLength(1);
  });

  it("reports a toggle when the checkbox or its label is clicked", () => {
    const { onToggle } = renderPicker();

    fireEvent.click(screen.getByRole("checkbox", { name: "retry" }));
    fireEvent.click(screen.getByText("good"));

    expect(onToggle.mock.calls).toEqual([["retry"], ["good"]]);
  });

  it("adds the trimmed draft on Enter and clears the input", () => {
    const { onAdd } = renderPicker();
    const input = screen.getByLabelText<HTMLInputElement>("Add a tag");

    fireEvent.change(input, { target: { value: "  night-shift " } });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(onAdd).toHaveBeenCalledWith("night-shift");
    expect(input.value).toBe("");
  });

  it("also commits on comma and on blur, but ignores an empty draft", () => {
    const { onAdd } = renderPicker();
    const input = screen.getByLabelText<HTMLInputElement>("Add a tag");

    fireEvent.keyDown(input, { key: "Enter" });
    fireEvent.keyDown(input, { key: "Tab" });
    expect(onAdd).not.toHaveBeenCalled();

    fireEvent.change(input, { target: { value: "a" } });
    fireEvent.keyDown(input, { key: "," });
    fireEvent.change(input, { target: { value: "b" } });
    fireEvent.blur(input);

    expect(onAdd.mock.calls).toEqual([["a"], ["b"]]);
  });

  it("explains an empty list", () => {
    renderPicker([]);

    expect(screen.getByText("No tags on the selected recordings yet.")).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });
});
