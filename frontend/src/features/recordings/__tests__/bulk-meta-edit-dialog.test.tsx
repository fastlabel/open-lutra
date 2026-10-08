import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ConfigResponse } from "@/api/generated/schemas";
import { BulkMetaEditDialog } from "../ui/bulk-meta-edit-dialog";

const { configMock, mutateMock, addLogMock } = vi.hoisted(() => ({
  configMock: vi.fn<() => { data: ConfigResponse | undefined }>(() => ({ data: undefined })),
  mutateMock: vi.fn(),
  addLogMock: vi.fn(),
}));

vi.mock("@/hooks/use-api", () => ({
  useConfig: () => configMock(),
  useBulkUpdateRecordingMeta: () => ({ mutate: mutateMock, isPending: false }),
}));

vi.mock("@/hooks/use-topics-stream", () => ({
  useAddLog: () => addLogMock,
}));

function makeConfig(): ConfigResponse {
  return {
    ros_domain_id: 0,
    robot_name: "Robot",
    default_color_mode: "dark",
    default_topics: [],
    stamp_quality: false,
    upload_enabled: false,
    metadata_fields: [
      { key: "operator_id", label: "Operator ID", type: "number", pattern: null, placeholder: null, options: [] },
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
    ],
  };
}

beforeEach(() => {
  configMock.mockReturnValue({ data: makeConfig() });
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("BulkMetaEditDialog", () => {
  it("starts every field as Unchanged", () => {
    render(<BulkMetaEditDialog folders={["rec_001", "rec_002"]} open onOpenChange={() => {}} onSaved={() => {}} />);

    expect(screen.getByText(/^2 recordings selected/)).toBeInTheDocument();
    expect(screen.getByLabelText<HTMLSelectElement>("Target Object").value).toBe("");
    expect(screen.getByRole("option", { name: "Unchanged" })).toBeInTheDocument();
  });

  it("offers only select metadata fields (no task name, tags, or text/number fields)", () => {
    render(<BulkMetaEditDialog folders={["rec_001"]} open onOpenChange={() => {}} onSaved={() => {}} />);

    expect(screen.getByText(/^1 recording selected/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Task name")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Tags")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Operator ID")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Target Object")).toBeInTheDocument();
  });

  it("submits only the fields that were given a value", () => {
    render(<BulkMetaEditDialog folders={["rec_001", "rec_002"]} open onOpenChange={() => {}} onSaved={() => {}} />);

    fireEvent.change(screen.getByLabelText("Target Object"), { target: { value: "cup" } });
    fireEvent.click(screen.getByRole("button", { name: "Save to 2 recordings" }));

    expect(mutateMock).toHaveBeenCalledWith(
      { data: { folders: ["rec_001", "rec_002"], metadata: { target_object: "cup" } } },
      expect.anything(),
    );
  });

  it("disables Save until a field is given a value, and again once it is reset to Unchanged", () => {
    render(<BulkMetaEditDialog folders={["rec_001"]} open onOpenChange={() => {}} onSaved={() => {}} />);

    const save = screen.getByRole("button", { name: "Save to 1 recording" });
    const select = screen.getByLabelText("Target Object");
    expect(save).toBeDisabled();
    fireEvent.change(select, { target: { value: "box" } });
    expect(save).toBeEnabled();
    fireEvent.change(select, { target: { value: "" } });
    expect(save).toBeDisabled();
  });

  it("closes without saving on Cancel", () => {
    const onOpenChange = vi.fn();
    render(<BulkMetaEditDialog folders={["rec_001"]} open onOpenChange={onOpenChange} onSaved={() => {}} />);

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(mutateMock).not.toHaveBeenCalled();
  });
});
