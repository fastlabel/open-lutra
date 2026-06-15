import { fireEvent, render } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { BulkUploadResponse, ConfigResponse } from "@/api/generated/schemas";
import { TooltipProvider } from "@/components/ui/tooltip";
import { useRecordingsStore } from "@/features/recordings";
import { BulkUploadButton } from "../bulk-upload-button";

function renderButton() {
  const wrapper = ({ children }: { children: ReactNode }) => <TooltipProvider>{children}</TooltipProvider>;
  return render(<BulkUploadButton />, { wrapper });
}

const { useConfigMock, useStartBulkUploadMock, startBulkUploadMock, addLogMock } = vi.hoisted(() => ({
  useConfigMock: vi.fn<() => { data: ConfigResponse | undefined }>(() => ({ data: undefined })),
  useStartBulkUploadMock: vi.fn(),
  startBulkUploadMock: vi.fn(),
  addLogMock: vi.fn(),
}));

vi.mock("@/hooks/use-api", () => ({
  useConfig: () => useConfigMock(),
  useStartBulkUpload: () => useStartBulkUploadMock(),
}));
vi.mock("@/hooks/use-topics-stream", () => ({ useAddLog: () => addLogMock }));

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

function setChecked(folders: string[]): void {
  useRecordingsStore.setState({ checkedFolders: new Set(folders) });
}

function envelope(body: BulkUploadResponse): { status: 200; data: BulkUploadResponse } {
  return { status: 200, data: body };
}

beforeEach(() => {
  useConfigMock.mockReturnValue({ data: makeConfig() });
  useStartBulkUploadMock.mockReturnValue({ mutate: startBulkUploadMock, isPending: false });
  setChecked([]);
});

afterEach(() => {
  useConfigMock.mockReset();
  useStartBulkUploadMock.mockReset();
  startBulkUploadMock.mockReset();
  addLogMock.mockReset();
  setChecked([]);
});

describe("BulkUploadButton", () => {
  it("renders nothing when upload_enabled is false", () => {
    useConfigMock.mockReturnValue({ data: makeConfig({ upload_enabled: false }) });
    setChecked(["rec_001"]);
    const { container } = renderButton();
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing when no folder is selected", () => {
    const { container } = renderButton();
    expect(container.firstChild).toBeNull();
  });

  it("invokes startBulkUpload with the checked folders when clicked", () => {
    setChecked(["rec_a", "rec_b"]);
    const { getByRole } = renderButton();
    fireEvent.click(getByRole("button"));
    expect(startBulkUploadMock).toHaveBeenCalledTimes(1);
    const [payload] = startBulkUploadMock.mock.calls[0];
    expect(new Set(payload.data.folders)).toEqual(new Set(["rec_a", "rec_b"]));
  });

  it("logs the enqueued count and clears the selection on success", () => {
    setChecked(["rec_a", "rec_b"]);
    startBulkUploadMock.mockImplementation((_payload, opts) => {
      opts.onSuccess(
        envelope({
          results: [
            { folder: "rec_a", status: "uploading", error: null },
            { folder: "rec_b", status: "uploading", error: null },
          ],
        }),
      );
    });
    const { getByRole } = renderButton();
    fireEvent.click(getByRole("button"));
    expect(addLogMock).toHaveBeenCalledWith("info", "Enqueued 2 uploads");
    expect(useRecordingsStore.getState().checkedFolders.size).toBe(0);
  });

  it("logs each per-folder failure alongside the success count", () => {
    setChecked(["rec_a", "missing"]);
    startBulkUploadMock.mockImplementation((_payload, opts) => {
      opts.onSuccess(
        envelope({
          results: [
            { folder: "rec_a", status: "uploading", error: null },
            { folder: "missing", status: "failed", error: "Folder not found" },
          ],
        }),
      );
    });
    const { getByRole } = renderButton();
    fireEvent.click(getByRole("button"));
    expect(addLogMock).toHaveBeenCalledWith("info", "Enqueued 1 upload");
    expect(addLogMock).toHaveBeenCalledWith("danger", "Upload skipped for missing: Folder not found");
  });

  it("logs the error message when the mutation fails", () => {
    setChecked(["rec_a"]);
    startBulkUploadMock.mockImplementation((_payload, opts) => {
      opts.onError(new Error("S3_BUCKET is not configured"));
    });
    const { getByRole } = renderButton();
    fireEvent.click(getByRole("button"));
    expect(addLogMock).toHaveBeenCalledWith("danger", "Bulk upload failed: S3_BUCKET is not configured");
    // Selection should NOT be cleared on failure so the user can retry.
    expect(useRecordingsStore.getState().checkedFolders.has("rec_a")).toBe(true);
  });

  it("disables the click while the mutation is pending", () => {
    setChecked(["rec_a"]);
    useStartBulkUploadMock.mockReturnValue({ mutate: startBulkUploadMock, isPending: true });
    const { getByRole } = renderButton();
    expect(getByRole("button")).toBeDisabled();
  });
});
