import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TooltipProvider } from "@/components/ui/tooltip";
import { useRecordingsStore } from "@/features/recordings";
import { BulkExportButton } from "../ui/bulk-export-button";
import { ExportDialog } from "../ui/export-dialog";

// Mock the API layer so the test does not depend on generated hooks / network.
const { mutateMock, jobMock, configMock } = vi.hoisted(() => ({
  mutateMock: vi.fn(),
  jobMock: vi.fn<() => unknown>(() => undefined),
  configMock: vi.fn<() => unknown>(),
}));

vi.mock("@/api/generated/lerobot/lerobot", () => ({
  useStartLeRobotExport: () => ({ mutate: mutateMock, isPending: false }),
}));

vi.mock("@/hooks/use-api", () => ({
  useLeRobotConfig: () => configMock(),
}));

// The dialog tracks the enqueued job via useJob; mock it (no QueryClient in this test).
vi.mock("@/hooks/use-jobs-stream", () => ({ useJob: () => jobMock() }));

function renderButton() {
  const wrapper = ({ children }: { children: ReactNode }) => <TooltipProvider>{children}</TooltipProvider>;
  return render(<BulkExportButton />, { wrapper });
}

beforeEach(() => {
  useRecordingsStore.getState().clearChecked();
  mutateMock.mockReset();
  jobMock.mockReset();
  jobMock.mockReturnValue(undefined);
  configMock.mockReset();
  configMock.mockReturnValue({
    data: { configured: true, robot_type: "sim", cameras: ["cam"] },
    isLoading: false,
  });
});

afterEach(() => {
  useRecordingsStore.getState().clearChecked();
});

describe("BulkExportButton", () => {
  it("renders nothing when no recordings are checked", () => {
    const { container } = renderButton();
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the export button once recordings are checked", () => {
    useRecordingsStore.setState({ checkedFolders: new Set(["rec1", "rec2"]) });
    renderButton();
    expect(screen.getByRole("button", { name: /Export to LeRobot/ })).toBeInTheDocument();
  });

  it("disables the button when the recording config has no lerobot_export mapping", () => {
    configMock.mockReturnValue({
      data: { configured: false, robot_type: null, cameras: [] },
      isLoading: false,
    });
    useRecordingsStore.setState({ checkedFolders: new Set(["rec1"]) });
    renderButton();
    const button = screen.getByRole("button", { name: /Export to LeRobot/ });
    expect(button).toBeDisabled();
    fireEvent.click(button);
    expect(screen.queryByRole("heading", { name: "Export to LeRobot" })).not.toBeInTheDocument();
  });

  it("disables the button while the lerobot config is still loading", () => {
    configMock.mockReturnValue({ data: undefined, isLoading: true });
    useRecordingsStore.setState({ checkedFolders: new Set(["rec1"]) });
    renderButton();
    expect(screen.getByRole("button", { name: /Export to LeRobot/ })).toBeDisabled();
  });

  it("opens the export dialog with the output field", () => {
    useRecordingsStore.setState({ checkedFolders: new Set(["rec1"]) });
    renderButton();
    fireEvent.click(screen.getByRole("button", { name: /Export to LeRobot/ }));
    expect(screen.getByRole("heading", { name: "Export to LeRobot" })).toBeInTheDocument();
    expect(screen.getByLabelText("Output name")).toBeInTheDocument();
  });

  it("submits the export with the folders and output name", () => {
    useRecordingsStore.setState({ checkedFolders: new Set(["rec1", "rec2"]) });
    renderButton();
    fireEvent.click(screen.getByRole("button", { name: /Export to LeRobot/ }));
    fireEvent.change(screen.getByLabelText("Output name"), { target: { value: "ds_v1" } });
    fireEvent.click(screen.getByRole("button", { name: "Export" }));
    expect(mutateMock).toHaveBeenCalledTimes(1);
    expect(mutateMock.mock.calls[0][0]).toEqual({
      data: { folders: ["rec1", "rec2"], output_name: "ds_v1" },
    });
  });

  it("shows live progress and the completion result in the dialog", () => {
    // mutate immediately resolves with a job id; the tracked job reports completion.
    mutateMock.mockImplementation((_vars, opts) => opts.onSuccess({ data: { job_id: "lex-1" } }));
    jobMock.mockReturnValue({
      job_id: "lex-1",
      type: "lerobot_export",
      folder: "ds_v1",
      status: "completed",
      progress: { step: "finalize", step_label: "Finalizing", current: 1, total: 1 },
      error: null,
    });

    useRecordingsStore.setState({ checkedFolders: new Set(["rec1"]) });
    renderButton();
    fireEvent.click(screen.getByRole("button", { name: /Export to LeRobot/ }));
    fireEvent.change(screen.getByLabelText("Output name"), { target: { value: "ds_v1" } });
    fireEvent.click(screen.getByRole("button", { name: "Export" }));

    expect(screen.getByText(/Export completed/)).toBeInTheDocument();
    expect(screen.getByText("_lerobot_exports/ds_v1/")).toBeInTheDocument();
    expect(screen.queryByLabelText("Output name")).not.toBeInTheDocument(); // form replaced by status

    // A native download link points at the zip endpoint for the exported dataset.
    const link = screen.getByRole("link", { name: /Download \.zip/ });
    expect(link).toHaveAttribute("href", "/api/lerobot/exports/ds_v1/download");
    expect(link).toHaveAttribute("download");
  });

  it("closes the dialog (open=false) when a completed export is dismissed", () => {
    // Otherwise BulkExportButton (mounted but rendering null) keeps open=true and
    // the dialog re-pops the next time a recording is checked.
    mutateMock.mockImplementation((_vars, opts) => opts.onSuccess({ data: { job_id: "lex-1" } }));
    jobMock.mockReturnValue({
      job_id: "lex-1",
      type: "lerobot_export",
      folder: "ds_v1",
      status: "completed",
      progress: { step: "finalize", step_label: "Finalizing", current: 1, total: 1 },
      error: null,
    });
    const onOpenChange = vi.fn();
    const onExported = vi.fn();
    const wrapper = ({ children }: { children: ReactNode }) => <TooltipProvider>{children}</TooltipProvider>;
    render(<ExportDialog folders={["rec1"]} open onOpenChange={onOpenChange} onExported={onExported} />, { wrapper });

    fireEvent.change(screen.getByLabelText("Output name"), { target: { value: "ds_v1" } });
    fireEvent.click(screen.getByRole("button", { name: "Export" }));
    fireEvent.click(screen.getByRole("button", { name: "Close" }));

    expect(onExported).toHaveBeenCalledTimes(1);
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("routes Escape through the same close handler as the Close button", () => {
    mutateMock.mockImplementation((_vars, opts) => opts.onSuccess({ data: { job_id: "lex-1" } }));
    jobMock.mockReturnValue({
      job_id: "lex-1",
      type: "lerobot_export",
      folder: "ds_v1",
      status: "completed",
      progress: { step: "finalize", step_label: "Finalizing", current: 1, total: 1 },
      error: null,
    });
    const onOpenChange = vi.fn();
    const onExported = vi.fn();
    const wrapper = ({ children }: { children: ReactNode }) => <TooltipProvider>{children}</TooltipProvider>;
    render(<ExportDialog folders={["rec1"]} open onOpenChange={onOpenChange} onExported={onExported} />, { wrapper });

    fireEvent.change(screen.getByLabelText("Output name"), { target: { value: "ds_v1" } });
    fireEvent.click(screen.getByRole("button", { name: "Export" }));
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });

    expect(onExported).toHaveBeenCalledTimes(1); // same as Close button: clears selection
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
