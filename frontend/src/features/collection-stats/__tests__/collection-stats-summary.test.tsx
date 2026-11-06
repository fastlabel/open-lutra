import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ConfigResponse, FileEntry, FilesResponse, GetRecordingsParams } from "@/api/generated/schemas";
import { CollectionStatsSummary } from "../collection-stats-summary";
import { localDayRange } from "../day-range";

const { useConfigMock, useFilesMock } = vi.hoisted(() => ({
  useConfigMock: vi.fn<() => { data: ConfigResponse | undefined }>(() => ({ data: undefined })),
  useFilesMock: vi.fn<(params?: GetRecordingsParams) => { data: FilesResponse | undefined }>(() => ({
    data: undefined,
  })),
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

function files(entries: FileEntry[]): { data: FilesResponse } {
  return { data: { output_dir: "/out", entries } };
}

const chip = () => screen.getByRole("button", { name: /Today/ });

function openBreakdown() {
  fireEvent.click(chip());
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
  it("renders nothing and issues no recordings request when disabled", () => {
    useConfigMock.mockReturnValue({ data: makeConfig({ collection_stats_enabled: false }) });
    const { container } = render(<CollectionStatsSummary />);
    expect(container).toBeEmptyDOMElement();
    expect(useFilesMock).not.toHaveBeenCalled();
  });

  it("renders nothing while the config is loading", () => {
    useConfigMock.mockReturnValue({ data: undefined });
    const { container } = render(<CollectionStatsSummary />);
    expect(container).toBeEmptyDOMElement();
    expect(useFilesMock).not.toHaveBeenCalled();
  });

  it("renders nothing while today's recordings are loading", () => {
    useFilesMock.mockReturnValue({ data: undefined });
    const { container } = render(<CollectionStatsSummary />);
    expect(container).toBeEmptyDOMElement();
  });

  it("requests today's local-day range", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 10, 6, 14, 0));
    render(<CollectionStatsSummary />);
    expect(useFilesMock).toHaveBeenLastCalledWith(localDayRange(new Date(2026, 10, 6)));
  });

  it("shows OK episodes and their duration on the chip, flagging failed takes with a dot", () => {
    useFilesMock.mockReturnValue(
      files([
        makeEntry({ validation_overall_status: "pass", duration_ns: 60 * SEC }),
        makeEntry({ validation_overall_status: "warn", duration_ns: 30 * SEC }),
        makeEntry({ validation_overall_status: "fail" }),
        makeEntry({ validation_overall_status: null }),
      ]),
    );
    render(<CollectionStatsSummary />);
    expect(chip()).toHaveTextContent("Today2 episodes · 1m 30s");
    expect(screen.getByTitle("Some takes failed")).toBeInTheDocument();
  });

  it("flags a validation error with the dot as well", () => {
    useFilesMock.mockReturnValue(files([makeEntry({ validation_overall_status: "error" })]));
    render(<CollectionStatsSummary />);
    expect(screen.getByTitle("Some takes failed")).toBeInTheDocument();
  });

  it("shows no dot when nothing failed", () => {
    useFilesMock.mockReturnValue(files([makeEntry(), makeEntry({ validation_overall_status: null })]));
    render(<CollectionStatsSummary />);
    expect(screen.queryByTitle("Some takes failed")).not.toBeInTheDocument();
  });

  it("breaks the day down by validation result in the popover", () => {
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
    openBreakdown();
    expect(row("OK (pass / warn)")).toHaveTextContent("2");
    expect(row("OK (pass / warn)")).toHaveTextContent("1m 30s");
    expect(row("Failed")).toHaveTextContent("1");
    expect(row("Validation error")).toHaveTextContent("1");
    expect(row("Checking")).toHaveTextContent("1");
    expect(row("Total recorded")).toHaveTextContent("5");
  });

  it("omits the validation error row when there are none", () => {
    useFilesMock.mockReturnValue(files([makeEntry()]));
    render(<CollectionStatsSummary />);
    openBreakdown();
    expect(screen.queryByTestId("breakdown-Validation error")).not.toBeInTheDocument();
  });

  it("shows zeros on a day without recordings", () => {
    render(<CollectionStatsSummary />);
    expect(chip()).toHaveTextContent("0 episodes · 0s");
    openBreakdown();
    expect(row("Total recorded")).toHaveTextContent("0");
  });

  it("moves a recording from checking to OK when its validation completes", () => {
    useFilesMock.mockReturnValue(files([makeEntry({ validation_overall_status: null })]));
    const { rerender } = render(<CollectionStatsSummary />);
    expect(chip()).toHaveTextContent("0 episodes · 0s");

    useFilesMock.mockReturnValue(files([makeEntry({ validation_overall_status: "pass" })]));
    rerender(<CollectionStatsSummary />);
    expect(chip()).toHaveTextContent("1 episode · 30s");
  });

  it("requests the new day's range when the date rolls over", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 10, 6, 23, 59, 30));
    render(<CollectionStatsSummary />);
    expect(useFilesMock).toHaveBeenLastCalledWith(localDayRange(new Date(2026, 10, 6)));

    act(() => {
      vi.advanceTimersByTime(60_000);
    });
    expect(useFilesMock).toHaveBeenLastCalledWith(localDayRange(new Date(2026, 10, 7)));
  });
});
