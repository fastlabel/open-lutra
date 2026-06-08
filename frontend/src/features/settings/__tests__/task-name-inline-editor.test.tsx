import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TooltipProvider } from "@/components/ui/tooltip";
import { useSettingsStore } from "../store";
import { TaskNameInlineEditor } from "../ui/task-name-inline-editor";

// Mock the API hook directly: this component test should not depend on
// network or query-client timing. `vi.hoisted` ensures the mock function is
// defined before the hoisted `vi.mock` factory closure captures it.
const { taskNamesMock } = vi.hoisted(() => ({
  taskNamesMock: vi.fn<() => string[]>(() => []),
}));

vi.mock("@/hooks/use-api", () => ({
  useTaskNames: () => taskNamesMock(),
}));

function renderEditor() {
  const wrapper = ({ children }: { children: ReactNode }) => <TooltipProvider>{children}</TooltipProvider>;
  return render(<TaskNameInlineEditor />, { wrapper });
}

/** Click the pencil and return the input element. */
function openEditor(): HTMLElement {
  fireEvent.click(screen.getByRole("button", { name: "Edit task name" }));
  return screen.getByRole("combobox", { name: "Task name" });
}

beforeEach(() => {
  useSettingsStore.setState({ taskName: "pick" });
  taskNamesMock.mockReturnValue([]);
});

afterEach(() => {
  useSettingsStore.getState().reset();
  taskNamesMock.mockReset();
});

describe("TaskNameInlineEditor autocomplete", () => {
  it("shows 'Set task name' placeholder when name is empty", () => {
    useSettingsStore.setState({ taskName: "" });
    renderEditor();
    expect(screen.getByText("Set task name")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit task name" })).toBeInTheDocument();
  });

  it("opens the editor from the empty placeholder state", () => {
    useSettingsStore.setState({ taskName: "" });
    renderEditor();
    openEditor();
    expect(screen.getByRole("combobox", { name: "Task name" })).toBeInTheDocument();
  });

  it("shows past task-name suggestions in edit mode", () => {
    taskNamesMock.mockReturnValue(["pick", "place", "fold_clothes"]);
    renderEditor();
    openEditor();

    expect(screen.getByRole("listbox", { name: "Task name suggestions" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "place" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "fold_clothes" })).toBeInTheDocument();
    // The current draft ("pick") is excluded from suggestions.
    expect(screen.queryByRole("option", { name: "pick" })).not.toBeInTheDocument();
  });

  it("narrows suggestions by input (case-insensitive)", () => {
    taskNamesMock.mockReturnValue(["Pick_blue_cube", "place_block", "fold_clothes"]);
    renderEditor();
    const input = openEditor();

    fireEvent.change(input, { target: { value: "PLACE" } });

    expect(screen.getByRole("option", { name: "place_block" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "Pick_blue_cube" })).not.toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "fold_clothes" })).not.toBeInTheDocument();
  });

  it("clicking a suggestion commits that value and exits edit mode", () => {
    taskNamesMock.mockReturnValue(["pick", "place"]);
    renderEditor();
    openEditor();

    fireEvent.mouseDown(screen.getByRole("option", { name: "place" }));

    expect(useSettingsStore.getState().taskName).toBe("place");
    expect(screen.queryByRole("combobox", { name: "Task name" })).not.toBeInTheDocument();
  });

  it("highlights with ArrowDown and selects with Enter", () => {
    taskNamesMock.mockReturnValue(["pick", "place", "fold"]);
    renderEditor();
    const input = openEditor();

    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "Enter" });

    // Two ArrowDown advances from -1 to 0 then 0 to 1. The current "pick" is
    // filtered out, so suggestions = [place, fold]. Index 1 = "fold".
    expect(useSettingsStore.getState().taskName).toBe("fold");
  });

  it("Escape cancels editing without changing the value", () => {
    taskNamesMock.mockReturnValue(["pick", "place"]);
    renderEditor();
    const input = openEditor();

    fireEvent.change(input, { target: { value: "discarded" } });
    fireEvent.keyDown(input, { key: "Escape" });

    expect(useSettingsStore.getState().taskName).toBe("pick");
  });

  it("Tab commits the highlighted suggestion", () => {
    taskNamesMock.mockReturnValue(["pick", "place"]);
    renderEditor();
    const input = openEditor();

    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "Tab" });

    expect(useSettingsStore.getState().taskName).toBe("place");
  });
});

describe("TaskNameInlineEditor validation feedback", () => {
  it("shows an error popover and keeps edit mode when Enter is pressed on invalid input", () => {
    renderEditor();
    const input = openEditor();

    fireEvent.change(input, { target: { value: "Invalid Task Name" } });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Only letters, digits, hyphens, and underscores are allowed",
    );
    expect(screen.getByRole("combobox", { name: "Task name" })).toBeInTheDocument();
    expect(useSettingsStore.getState().taskName).toBe("pick");
  });

  it("shows an error for empty input on Enter", () => {
    renderEditor();
    const input = openEditor();

    fireEvent.change(input, { target: { value: "   " } });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(screen.getByRole("alert")).toHaveTextContent("Please enter a task name");
    expect(screen.getByRole("combobox", { name: "Task name" })).toBeInTheDocument();
  });

  it("clears the error and hides the popover when the user keeps typing", () => {
    renderEditor();
    const input = openEditor();

    fireEvent.change(input, { target: { value: "bad name" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(screen.getByRole("alert")).toBeInTheDocument();

    fireEvent.change(input, { target: { value: "good_name" } });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("hides suggestions while an error popover is shown", () => {
    taskNamesMock.mockReturnValue(["pick", "place"]);
    renderEditor();
    const input = openEditor();

    fireEvent.change(input, { target: { value: "bad name" } });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(screen.queryByRole("listbox", { name: "Task name suggestions" })).not.toBeInTheDocument();
  });

  it("blur with invalid input silently exits without showing an error", () => {
    renderEditor();
    const input = openEditor();

    fireEvent.change(input, { target: { value: "bad name" } });
    fireEvent.blur(input);

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "Task name" })).not.toBeInTheDocument();
    expect(useSettingsStore.getState().taskName).toBe("pick");
  });

  it("Escape clears the error and exits", () => {
    renderEditor();
    const input = openEditor();

    fireEvent.change(input, { target: { value: "bad name" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(screen.getByRole("alert")).toBeInTheDocument();

    fireEvent.keyDown(input, { key: "Escape" });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "Task name" })).not.toBeInTheDocument();
  });
});
