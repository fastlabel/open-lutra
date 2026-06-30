import { fireEvent, render } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ConfigResponse } from "@/api/generated/schemas";
import { TooltipProvider } from "@/components/ui/tooltip";
import type { UploadStatusView } from "@/hooks/use-upload-status";
import { UploadButton } from "../upload-button";

function renderButton(folderPath = "rec_001") {
  const wrapper = ({ children }: { children: ReactNode }) => <TooltipProvider>{children}</TooltipProvider>;
  return render(<UploadButton folderPath={folderPath} />, { wrapper });
}

const { useConfigMock, useUploadStatusMock, startUploadMock, useStartUploadMock } = vi.hoisted(() => ({
  useConfigMock: vi.fn<() => { data: ConfigResponse | undefined }>(() => ({ data: undefined })),
  useUploadStatusMock: vi.fn<(folder: string | null) => UploadStatusView>(() => ({
    status: "not_found",
    percent: null,
    error: null,
  })),
  startUploadMock: vi.fn(),
  useStartUploadMock: vi.fn(),
}));

vi.mock("@/hooks/use-api", () => ({
  useConfig: () => useConfigMock(),
  useStartUpload: () => useStartUploadMock(),
}));
vi.mock("@/hooks/use-upload-status", () => ({
  useUploadStatus: (folder: string | null) => useUploadStatusMock(folder),
}));

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

beforeEach(() => {
  useConfigMock.mockReturnValue({ data: makeConfig() });
  useUploadStatusMock.mockReturnValue({ status: "not_found", percent: null, error: null });
  useStartUploadMock.mockReturnValue({ mutate: startUploadMock, isPending: false });
});

afterEach(() => {
  useConfigMock.mockReset();
  useUploadStatusMock.mockReset();
  useStartUploadMock.mockReset();
  startUploadMock.mockReset();
});

describe("UploadButton", () => {
  it("renders a disabled button when upload_enabled is false", () => {
    useConfigMock.mockReturnValue({ data: makeConfig({ upload_enabled: false }) });
    const { getByRole } = renderButton();
    const button = getByRole("button", { name: /Upload/ });
    expect(button).toBeDisabled();
    fireEvent.click(button);
    expect(startUploadMock).not.toHaveBeenCalled();
  });

  it("shows the idle label when there is no prior upload", () => {
    const { getByRole } = renderButton();
    expect(getByRole("button", { name: /^Upload$/ })).toBeEnabled();
  });

  it("shows the percent label while uploading and disables the click", () => {
    useUploadStatusMock.mockReturnValue({ status: "uploading", percent: 42, error: null });
    const { getByRole } = renderButton();
    const button = getByRole("button", { name: /Uploading 42%/ });
    expect(button).toBeDisabled();
  });

  it("falls back to an indeterminate label while uploading without percent", () => {
    useUploadStatusMock.mockReturnValue({ status: "uploading", percent: null, error: null });
    const { getByRole } = renderButton();
    expect(getByRole("button", { name: /Uploading…/ })).toBeDisabled();
  });

  it("flips to Re-upload when an upload completed", () => {
    useUploadStatusMock.mockReturnValue({ status: "uploaded", percent: null, error: null });
    const { getByRole } = renderButton();
    expect(getByRole("button", { name: /Re-upload/ })).toBeEnabled();
  });

  it("shows the failure message alongside a Retry button when failed", () => {
    useUploadStatusMock.mockReturnValue({ status: "failed", percent: null, error: "network down" });
    const { getByRole, getByText } = renderButton();
    expect(getByRole("button", { name: /Retry upload/ })).toBeEnabled();
    expect(getByText("network down")).toBeInTheDocument();
  });

  it("invokes startUpload with the folder path when clicked", () => {
    const { getByRole } = renderButton();
    fireEvent.click(getByRole("button"));
    expect(startUploadMock).toHaveBeenCalledWith({ params: { path: "rec_001" } });
  });

  it("disables the click while the mutation is pending", () => {
    useStartUploadMock.mockReturnValue({ mutate: startUploadMock, isPending: true });
    const { getByRole } = renderButton();
    expect(getByRole("button")).toBeDisabled();
  });
});
