import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ConfigResponse, FileEntry, FilesResponse } from "@/api/generated/schemas";
import { BulkMetaEditDialog } from "../ui/bulk-meta-edit-dialog";

const { configMock, filesMock, mutateMock, addLogMock } = vi.hoisted(() => ({
  configMock: vi.fn<() => { data: ConfigResponse | undefined }>(() => ({
    data: undefined,
  })),
  filesMock: vi.fn<() => { data: FilesResponse | undefined }>(() => ({
    data: undefined,
  })),
  mutateMock: vi.fn(),
  addLogMock: vi.fn(),
}));

vi.mock("@/hooks/use-api", () => ({
  useConfig: () => configMock(),
  useFiles: () => filesMock(),
  useBulkUpdateRecordingMeta: () => ({ mutate: mutateMock, isPending: false }),
}));

vi.mock("@/hooks/use-topics-stream", () => ({
  useAddLog: () => addLogMock,
}));

function makeConfig(fields: ConfigResponse["metadata_fields"] = FIELDS): ConfigResponse {
  return {
    ros_domain_id: 0,
    robot_name: "Robot",
    default_topics: [],
    stamp_quality: false,
    upload_enabled: false,
    metadata_fields: fields,
  };
}

const FIELDS: ConfigResponse["metadata_fields"] = [
  {
    key: "operator_id",
    label: "Operator ID",
    type: "number",
    pattern: null,
    placeholder: null,
    options: [],
  },
  {
    key: "target_object",
    label: "Target Object",
    type: "select",
    pattern: null,
    placeholder: null,
    options: [
      { value: "box", label: "Box" },
      { value: "cup", label: "cup" },
    ],
  },
];

function makeEntry(name: string, tags: string[]): FileEntry {
  return {
    name,
    path: name,
    size: 0,
    modified_at: 0,
    topic_count: null,
    recording_start_ns: null,
    duration_ns: null,
    message_count: null,
    has_quality_report: false,
    validation_overall_status: null,
    upload_status: null,
    task_name: null,
    recording_config_name: null,
    tags,
    metadata: {},
  };
}

const ENTRIES = [
  makeEntry("rec_001", ["good", "retry"]),
  makeEntry("rec_002", ["good"]),
  makeEntry("rec_other", ["x"]),
];

function renderDialog(folders = ["rec_001", "rec_002"]) {
  const onOpenChange = vi.fn();
  const onSaved = vi.fn();
  const view = render(<BulkMetaEditDialog folders={folders} open onOpenChange={onOpenChange} onSaved={onSaved} />);
  return { ...view, onOpenChange, onSaved };
}

function saveButton(count: number) {
  return screen.getByRole("button", {
    name: `Save to ${count} recording${count === 1 ? "" : "s"}`,
  });
}

beforeEach(() => {
  configMock.mockReturnValue({ data: makeConfig() });
  filesMock.mockReturnValue({ data: { output_dir: "/out", entries: ENTRIES } });
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("BulkMetaEditDialog", () => {
  it("lists the tags of the selected recordings with their counts and starts every select as Unchanged", () => {
    renderDialog();

    expect(screen.getByText(/^2 recordings selected/)).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "good" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("checkbox", { name: "retry" })).toHaveAttribute("aria-checked", "mixed");
    expect(screen.queryByRole("checkbox", { name: "x" })).not.toBeInTheDocument();
    expect(screen.getByText("2/2")).toBeInTheDocument();
    expect(screen.getByLabelText<HTMLSelectElement>("Target Object").value).toBe("");
    expect(screen.getByRole("option", { name: "Unchanged" })).toBeInTheDocument();
  });

  it("offers only select metadata fields (no task name or text/number fields)", () => {
    renderDialog(["rec_001"]);

    expect(screen.getByText(/^1 recording selected/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Task name")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Operator ID")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Target Object")).toBeInTheDocument();
  });

  it("hides the Metadata section when the master defines no select field", () => {
    configMock.mockReturnValue({ data: makeConfig([]) });
    renderDialog();

    expect(screen.getByText("Tags")).toBeInTheDocument();
    expect(screen.queryByText("Metadata")).not.toBeInTheDocument();
  });

  it("submits only the select fields that were given a value", () => {
    renderDialog();

    fireEvent.change(screen.getByLabelText("Target Object"), {
      target: { value: "cup" },
    });
    fireEvent.click(saveButton(2));

    expect(mutateMock).toHaveBeenCalledWith(
      {
        data: {
          folders: ["rec_001", "rec_002"],
          metadata: { target_object: "cup" },
          add_tags: [],
          remove_tags: [],
        },
      },
      expect.anything(),
    );
  });

  it("sends checked tags as add_tags and unchecked ones as remove_tags", () => {
    renderDialog();

    expect(saveButton(2)).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox", { name: "retry" }));
    expect(screen.getByRole("checkbox", { name: "retry" })).toHaveAttribute("aria-checked", "true");
    expect(saveButton(2)).toBeEnabled();
    fireEvent.click(screen.getByRole("checkbox", { name: "good" }));
    fireEvent.click(saveButton(2));

    expect(mutateMock).toHaveBeenCalledWith(
      {
        data: {
          folders: ["rec_001", "rec_002"],
          metadata: {},
          add_tags: ["retry"],
          remove_tags: ["good"],
        },
      },
      expect.anything(),
    );
  });

  it("adds a typed tag as checked, and re-checks a listed tag typed again instead of duplicating it", () => {
    renderDialog();
    const input = screen.getByLabelText("Add a tag");

    fireEvent.change(input, { target: { value: "reviewed" } });
    fireEvent.keyDown(input, { key: "Enter" });
    fireEvent.click(screen.getByRole("checkbox", { name: "good" }));
    fireEvent.change(input, { target: { value: "good" } });
    fireEvent.keyDown(input, { key: "Enter" });
    fireEvent.click(saveButton(2));

    expect(screen.getAllByRole("checkbox", { name: "good" })).toHaveLength(1);
    expect(mutateMock).toHaveBeenCalledWith(
      {
        data: {
          folders: ["rec_001", "rec_002"],
          metadata: {},
          add_tags: ["reviewed"],
          remove_tags: [],
        },
      },
      expect.anything(),
    );
  });

  it("disables Save until something changes, and again once every change is undone", () => {
    renderDialog(["rec_001"]);

    const save = saveButton(1);
    const select = screen.getByLabelText("Target Object");
    expect(save).toBeDisabled();
    fireEvent.change(select, { target: { value: "box" } });
    expect(save).toBeEnabled();
    fireEvent.change(select, { target: { value: "" } });
    expect(save).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox", { name: "retry" }));
    expect(save).toBeEnabled();
    fireEvent.click(screen.getByRole("checkbox", { name: "retry" }));
    expect(save).toBeDisabled();
  });

  it("enables Save for a tag that is typed but not committed, and sends it as an addition", () => {
    renderDialog();

    fireEvent.change(screen.getByLabelText("Add a tag"), { target: { value: " reviewed " } });
    expect(saveButton(2)).toBeEnabled();
    fireEvent.click(saveButton(2));

    expect(mutateMock).toHaveBeenCalledWith(
      { data: { folders: ["rec_001", "rec_002"], metadata: {}, add_tags: ["reviewed"], remove_tags: [] } },
      expect.anything(),
    );
  });

  it("shows a tag as mixed when a selected recording is missing from the list", () => {
    renderDialog(["rec_002", "rec_gone"]);

    expect(screen.getByRole("checkbox", { name: "good" })).toHaveAttribute("aria-checked", "mixed");
    expect(screen.getByText("1/2")).toBeInTheDocument();
  });

  it("keeps pending tag changes when the recordings list is refetched", () => {
    const { rerender, onOpenChange, onSaved } = renderDialog();
    fireEvent.click(screen.getByRole("checkbox", { name: "retry" }));

    filesMock.mockReturnValue({
      data: { output_dir: "/out", entries: [makeEntry("rec_001", ["good", "retry"]), makeEntry("rec_002", ["good"])] },
    });
    rerender(
      <BulkMetaEditDialog folders={["rec_001", "rec_002"]} open onOpenChange={onOpenChange} onSaved={onSaved} />,
    );

    expect(screen.getByRole("checkbox", { name: "retry" })).toHaveAttribute("aria-checked", "true");
    fireEvent.click(saveButton(2));
    expect(mutateMock).toHaveBeenCalledWith(
      { data: { folders: ["rec_001", "rec_002"], metadata: {}, add_tags: ["retry"], remove_tags: [] } },
      expect.anything(),
    );
  });

  it("drops pending tag changes when reopened", () => {
    const { rerender, onOpenChange, onSaved } = renderDialog();
    fireEvent.click(screen.getByRole("checkbox", { name: "retry" }));
    expect(saveButton(2)).toBeEnabled();

    rerender(
      <BulkMetaEditDialog
        folders={["rec_001", "rec_002"]}
        open={false}
        onOpenChange={onOpenChange}
        onSaved={onSaved}
      />,
    );
    rerender(
      <BulkMetaEditDialog folders={["rec_001", "rec_002"]} open onOpenChange={onOpenChange} onSaved={onSaved} />,
    );

    expect(screen.getByRole("checkbox", { name: "retry" })).toHaveAttribute("aria-checked", "mixed");
    expect(saveButton(2)).toBeDisabled();
  });

  it("logs, closes and clears the selection after a successful save", () => {
    mutateMock.mockImplementation((_vars, options) => options.onSuccess());
    const { onOpenChange, onSaved } = renderDialog();

    fireEvent.click(screen.getByRole("checkbox", { name: "retry" }));
    fireEvent.click(saveButton(2));

    expect(addLogMock).toHaveBeenCalledWith("info", "Updated 2 recordings");
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(onSaved).toHaveBeenCalled();
  });

  it("shows the error and stays open when the save fails", () => {
    mutateMock.mockImplementation((_vars, options) => options.onError(new Error("disk full")));
    const { onOpenChange } = renderDialog();

    fireEvent.click(screen.getByRole("checkbox", { name: "retry" }));
    fireEvent.click(saveButton(2));

    expect(screen.getByText("Failed to update recordings: disk full")).toBeInTheDocument();
    expect(addLogMock).toHaveBeenCalledWith("danger", "Failed to update recordings: disk full");
    expect(onOpenChange).not.toHaveBeenCalled();
  });

  it("closes without saving on Cancel", () => {
    const { onOpenChange } = renderDialog(["rec_001"]);

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(mutateMock).not.toHaveBeenCalled();
  });
});
