import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ConfigResponse, FileEntry } from "@/api/generated/schemas";
import { MetaEditDialog } from "../ui/meta-edit-dialog";

// Mock the API/log hooks directly so the test does not depend on the query client.
const { configMock, mutateMock, updateMock, addLogMock } = vi.hoisted(() => ({
  configMock: vi.fn<() => { data: ConfigResponse | undefined }>(() => ({ data: undefined })),
  mutateMock: vi.fn(),
  updateMock: vi.fn(),
  addLogMock: vi.fn(),
}));

vi.mock("@/hooks/use-api", () => ({
  useConfig: () => configMock(),
  useUpdateRecordingMeta: () => updateMock(),
}));

vi.mock("@/hooks/use-topics-stream", () => ({
  useAddLog: () => addLogMock,
}));

const FIELDS: ConfigResponse["metadata_fields"] = [
  {
    key: "operator_id",
    label: "Operator ID",
    type: "number",
    pattern: "^[0-9]+$",
    placeholder: "e.g. 007",
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

function makeConfig(): ConfigResponse {
  return {
    ros_domain_id: 0,
    robot_name: "Robot",
    default_topics: [],
    stamp_quality: false,
    upload_enabled: false,
    metadata_fields: FIELDS,
  };
}

function makeEntry(overrides: Partial<FileEntry> = {}): FileEntry {
  return {
    name: "rec_001",
    path: "rec_001",
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
    tags: [],
    metadata: {},
    ...overrides,
  };
}

beforeEach(() => {
  configMock.mockReturnValue({ data: makeConfig() });
  updateMock.mockReturnValue({ mutate: mutateMock, isPending: false });
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("MetaEditDialog metadata fields", () => {
  it("renders each master field pre-filled from the entry's metadata", () => {
    render(
      <MetaEditDialog
        entry={makeEntry({ metadata: { operator_id: "007", target_object: "box" } })}
        open
        onOpenChange={() => {}}
      />,
    );

    expect(screen.getByLabelText<HTMLInputElement>("Operator ID").value).toBe("007");
    expect(screen.getByLabelText<HTMLSelectElement>("Target Object").value).toBe("box");
    expect(screen.getByRole("option", { name: "Box" })).toBeInTheDocument();
  });

  it("saves the edited metadata via the update mutation (number kept as a string)", () => {
    render(<MetaEditDialog entry={makeEntry()} open onOpenChange={() => {}} />);

    fireEvent.change(screen.getByLabelText("Operator ID"), { target: { value: "007" } });
    fireEvent.change(screen.getByLabelText("Target Object"), { target: { value: "cup" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(mutateMock).toHaveBeenCalledWith(
      expect.objectContaining({
        name: "rec_001",
        data: expect.objectContaining({ metadata: { operator_id: "007", target_object: "cup" } }),
      }),
      expect.anything(),
    );
  });

  it("rejects non-digit input on a number field", () => {
    render(<MetaEditDialog entry={makeEntry({ metadata: { operator_id: "007" } })} open onOpenChange={() => {}} />);

    const operator = screen.getByLabelText<HTMLInputElement>("Operator ID");
    fireEvent.change(operator, { target: { value: "12a" } });
    // The non-digit change is ignored, so the field keeps its previous value.
    expect(operator.value).toBe("007");
  });
});
