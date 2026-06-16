import { render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ConfigResponse, FileEntry, JobSchema } from "@/api/generated/schemas";
import { UploadBadge } from "../upload-badge";

const { useConfigMock, useJobsMock } = vi.hoisted(() => ({
  useConfigMock: vi.fn<() => { data: ConfigResponse | undefined }>(() => ({ data: undefined })),
  useJobsMock: vi.fn<() => JobSchema[]>(() => []),
}));

vi.mock("@/hooks/use-api", () => ({ useConfig: () => useConfigMock() }));
vi.mock("@/hooks/use-jobs-stream", () => ({ useJobs: () => useJobsMock() }));

function makeConfig(overrides: Partial<ConfigResponse> = {}): ConfigResponse {
  return {
    ros_domain_id: 0,
    robot_name: "Robot",
    default_topics: [],
    stamp_quality: false,
    upload_enabled: true,
    ...overrides,
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
    ...overrides,
  };
}

type JobOverrides = Omit<Partial<JobSchema>, "progress"> & { progress?: Partial<JobSchema["progress"]> };

function makeJob(overrides: JobOverrides = {}): JobSchema {
  const { progress = {}, ...rest } = overrides;
  return {
    job_id: "upl_test",
    type: "upload",
    folder: "rec_001",
    status: "running",
    progress: { step: "upload", step_label: "Uploading", current: 0, total: 1, ...progress },
    error: null,
    created_at: "2026-05-25T12:00:00+00:00",
    started_at: "2026-05-25T12:00:00+00:00",
    finished_at: null,
    ...rest,
  };
}

beforeEach(() => {
  useConfigMock.mockReturnValue({ data: makeConfig() });
  useJobsMock.mockReturnValue([]);
});

afterEach(() => {
  useConfigMock.mockReset();
  useJobsMock.mockReset();
});

describe("UploadBadge", () => {
  it("renders nothing when upload_enabled is false", () => {
    useConfigMock.mockReturnValue({ data: makeConfig({ upload_enabled: false }) });
    const { container } = render(<UploadBadge entry={makeEntry({ upload_status: "uploaded" })} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders an empty slot when no upload has happened", () => {
    const { container } = render(<UploadBadge entry={makeEntry({ upload_status: null })} />);
    const slot = container.firstChild as HTMLElement | null;
    expect(slot).not.toBeNull();
    expect(slot?.getAttribute("data-status")).toBeNull();
    expect(slot?.querySelector("svg")).toBeNull();
  });

  it("shows the uploaded icon when entry.upload_status is uploaded", () => {
    const { container } = render(<UploadBadge entry={makeEntry({ upload_status: "uploaded" })} />);
    const slot = container.querySelector('[data-status="uploaded"]');
    expect(slot).not.toBeNull();
    expect(slot?.querySelector("svg")).not.toBeNull();
  });

  it("shows the failed icon when entry.upload_status is failed", () => {
    const { container } = render(<UploadBadge entry={makeEntry({ upload_status: "failed" })} />);
    const slot = container.querySelector('[data-status="failed"]');
    expect(slot).not.toBeNull();
  });

  it("shows live progress when an active upload job matches this folder", () => {
    useJobsMock.mockReturnValue([
      makeJob({ folder: "rec_001", status: "running", progress: { current: 50, total: 100 } }),
    ]);
    const { container, getByText } = render(<UploadBadge entry={makeEntry({ upload_status: "uploaded" })} />);
    // Live job wins over the persisted status.
    expect(container.querySelector('[data-status="uploading"]')).not.toBeNull();
    expect(getByText("50%")).toBeInTheDocument();
  });

  it("clamps progress to 100% when current exceeds total", () => {
    useJobsMock.mockReturnValue([
      makeJob({ folder: "rec_001", status: "running", progress: { current: 200, total: 100 } }),
    ]);
    const { getByText } = render(<UploadBadge entry={makeEntry()} />);
    expect(getByText("100%")).toBeInTheDocument();
  });

  it("falls back to 0% when total is zero", () => {
    useJobsMock.mockReturnValue([
      makeJob({ folder: "rec_001", status: "running", progress: { current: 0, total: 0 } }),
    ]);
    const { getByText } = render(<UploadBadge entry={makeEntry()} />);
    expect(getByText("0%")).toBeInTheDocument();
  });

  it("ignores jobs for other folders", () => {
    useJobsMock.mockReturnValue([makeJob({ folder: "other_folder", status: "running" })]);
    const { container } = render(<UploadBadge entry={makeEntry({ upload_status: "uploaded", name: "rec_001" })} />);
    expect(container.querySelector('[data-status="uploaded"]')).not.toBeNull();
    expect(container.querySelector('[data-status="uploading"]')).toBeNull();
  });
});
