import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ConfigResponse, FileEntry, FilesResponse, GetRecordingsParams } from "@/api/generated/schemas";
import { CollectionStatsSummary } from "../collection-stats-summary";
import { localDayRange } from "../day-range";

type FilesResult = { data: FilesResponse | undefined; isError: boolean };

const { useConfigMock, useFilesMock } = vi.hoisted(() => ({
  useConfigMock: vi.fn<() => { data: ConfigResponse | undefined }>(() => ({ data: undefined })),
  useFilesMock: vi.fn<(params?: GetRecordingsParams) => FilesResult>(() => ({ data: undefined, isError: false })),
}));

vi.mock("@/hooks/use-api", () => ({
  useConfig: () => useConfigMock(),
  useFiles: (params?: GetRecordingsParams) => useFilesMock(params),
}));

const SEC = 1_000_000_000;

function makeConfig(overrides: Partial<ConfigResponse> = {}): ConfigResponse {
  return {
    ros_domain_id: 0,
    robot_name: "Robot",
    default_topics: [],
    stamp_quality: false,
    upload_enabled: false,
    metadata_fields: [],
    collection_stats_enabled: true,
    ...overrides,
  };
}

function makeEntry(overrides: Partial<FileEntry> = {}): FileEntry {
  return {
    name: "rec",
    path: "rec",
    size: 0,
    modified_at: 0,
    topic_count: null,
    recording_start_ns: 0,
    duration_ns: 30 * SEC,
    message_count: null,
    has_quality_report: false,
    validation_overall_status: "pass",
    upload_status: null,
    task_name: null,
    recording_config_name: null,
    tags: [],
    metadata: {},
    ...overrides,
  };
}

function files(entries: FileEntry[]): FilesResult {
  return { data: { output_dir: "/out", entries }, isError: false };
}

function openSummary() {
  fireEvent.click(screen.getByRole("button", { name: "Today's collection" }));
}

const row = (label: string) => screen.getByTestId(`breakdown-${label}`);

beforeEach(() => {
  useConfigMock.mockReturnValue({ data: makeConfig() });
  useFilesMock.mockReturnValue(files([]));
});

afterEach(() => {
  vi.clearAllMocks();
  vi.useRealTimers();
});

describe("CollectionStatsSummary", () => {
  it("renders nothing when disabled", () => {
    useConfigMock.mockReturnValue({ data: makeConfig({ collection_stats_enabled: false }) });
    const { container } = render(<CollectionStatsSummary />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing while the config is loading", () => {
    useConfigMock.mockReturnValue({ data: undefined });
    const { container } = render(<CollectionStatsSummary />);
    expect(container).toBeEmptyDOMElement();
  });

  it("issues no recordings request until the dialog is opened", () => {
    render(<CollectionStatsSummary />);
    expect(screen.getByRole("button", { name: "Today's collection" })).toBeInTheDocument();
    expect(useFilesMock).not.toHaveBeenCalled();
  });

  it("requests today's local-day range when opened", () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date(2026, 10, 6, 14, 0));
    render(<CollectionStatsSummary />);
    openSummary();
    expect(useFilesMock).toHaveBeenLastCalledWith(localDayRange(new Date(2026, 10, 6)));
  });

  it("keeps the day it was opened on when it re-renders after midnight", () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date(2026, 10, 6, 23, 59, 30));
    const { rerender } = render(<CollectionStatsSummary />);
    openSummary();

    vi.setSystemTime(new Date(2026, 10, 7, 0, 0, 30));
    useFilesMock.mockReturnValue(files([makeEntry()]));
    rerender(<CollectionStatsSummary />);
    expect(row("Total recorded")).toHaveTextContent("1");
    expect(useFilesMock).toHaveBeenLastCalledWith(localDayRange(new Date(2026, 10, 6)));
  });

  it("shows a loading message while today's recordings load", () => {
    useFilesMock.mockReturnValue({ data: undefined, isError: false });
    render(<CollectionStatsSummary />);
    openSummary();
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });

  it("shows an error message when today's recordings cannot be loaded", () => {
    useFilesMock.mockReturnValue({ data: undefined, isError: true });
    render(<CollectionStatsSummary />);
    openSummary();
    expect(screen.getByText("Could not load today's recordings.")).toBeInTheDocument();
  });

  it("breaks the day down by validation result", () => {
    useFilesMock.mockReturnValue(
      files([
        makeEntry({ validation_overall_status: "pass", duration_ns: 60 * SEC }),
        makeEntry({ validation_overall_status: "warn", duration_ns: 30 * SEC }),
        makeEntry({ validation_overall_status: "fail" }),
        makeEntry({ validation_overall_status: "error" }),
        makeEntry({ validation_overall_status: null }),
      ]),
    );
    render(<CollectionStatsSummary />);
    openSummary();
    expect(screen.getByRole("dialog", { name: "Today's collection" })).toBeInTheDocument();
    expect(row("OK (pass / warn)")).toHaveTextContent("2");
    expect(row("OK (pass / warn)")).toHaveTextContent("1m 30s");
    expect(row("Failed")).toHaveTextContent("1");
    expect(row("Validation error")).toHaveTextContent("1");
    expect(row("No result")).toHaveTextContent("1");
    expect(row("Total recorded")).toHaveTextContent("5");
  });

  it("omits the validation error row when there are none", () => {
    useFilesMock.mockReturnValue(files([makeEntry()]));
    render(<CollectionStatsSummary />);
    openSummary();
    expect(screen.queryByTestId("breakdown-Validation error")).not.toBeInTheDocument();
  });

  it("shows zeros on a day without recordings", () => {
    render(<CollectionStatsSummary />);
    openSummary();
    expect(row("OK (pass / warn)")).toHaveTextContent("0");
    expect(row("OK (pass / warn)")).toHaveTextContent("0s");
    expect(row("Total recorded")).toHaveTextContent("0");
  });
});
