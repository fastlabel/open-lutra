import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ConfigResponse } from "@/api/generated/schemas";
import { useSettingsStore } from "../store";
import { RecordingMetadataPanel } from "../ui/recording-metadata-panel";

// Mock useConfig directly so the test does not depend on the query client.
const { configMock } = vi.hoisted(() => ({
  configMock: vi.fn<() => { data: ConfigResponse | undefined }>(() => ({ data: undefined })),
}));

vi.mock("@/hooks/use-api", () => ({
  useConfig: () => configMock(),
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

function makeConfig(metadata_fields: ConfigResponse["metadata_fields"]): ConfigResponse {
  return {
    ros_domain_id: 0,
    robot_name: "Robot",
    default_topics: [],
    stamp_quality: false,
    upload_enabled: false,
    metadata_fields,
  };
}

beforeEach(() => {
  useSettingsStore.getState().reset();
  configMock.mockReturnValue({ data: makeConfig(FIELDS) });
});

afterEach(() => {
  useSettingsStore.getState().reset();
  configMock.mockReset();
});

describe("RecordingMetadataPanel", () => {
  it("renders nothing when the config defines no metadata fields", () => {
    configMock.mockReturnValue({ data: makeConfig([]) });
    const { container } = render(<RecordingMetadataPanel />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the set-field count on the trigger", () => {
    useSettingsStore.setState({ metadata: { operator_id: "007" } });
    render(<RecordingMetadataPanel />);
    expect(screen.getByText("Metadata 1/2")).toBeInTheDocument();
  });

  it("renders a select field with master options and updates the store on selection", () => {
    render(<RecordingMetadataPanel />);
    fireEvent.click(screen.getByRole("button"));

    const target = screen.getByLabelText("Target Object");
    expect(screen.getByRole("option", { name: "Box" })).toBeInTheDocument();

    fireEvent.change(target, { target: { value: "box" } });
    expect(useSettingsStore.getState().metadata).toEqual({ target_object: "box" });
  });

  it("renders a number field that accepts digits (leading zeros kept as a string)", () => {
    render(<RecordingMetadataPanel />);
    fireEvent.click(screen.getByRole("button"));

    const operator = screen.getByLabelText("Operator ID");
    fireEvent.change(operator, { target: { value: "007" } });
    expect(useSettingsStore.getState().metadata).toEqual({ operator_id: "007" });
  });

  it("rejects non-digit input on a number field", () => {
    useSettingsStore.setState({ metadata: { operator_id: "007" } });
    render(<RecordingMetadataPanel />);
    fireEvent.click(screen.getByRole("button"));

    fireEvent.change(screen.getByLabelText("Operator ID"), { target: { value: "12a" } });
    // The non-digit change is ignored, so the stored value is unchanged.
    expect(useSettingsStore.getState().metadata).toEqual({ operator_id: "007" });
  });

  it("clears the field from the store when emptied", () => {
    useSettingsStore.setState({ metadata: { operator_id: "007" } });
    render(<RecordingMetadataPanel />);
    fireEvent.click(screen.getByRole("button"));

    fireEvent.change(screen.getByLabelText("Operator ID"), { target: { value: "" } });
    expect(useSettingsStore.getState().metadata).toEqual({});
  });
});
