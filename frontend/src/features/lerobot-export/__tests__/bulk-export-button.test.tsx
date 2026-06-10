import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TooltipProvider } from "@/components/ui/tooltip";
import { useRecordingsStore } from "@/features/recordings";
import { BulkExportButton } from "../ui/bulk-export-button";

// Mock the API layer so the test does not depend on generated hooks / network.
const { mutateMock, jobMock } = vi.hoisted(() => ({
  mutateMock: vi.fn(),
  jobMock: vi.fn<() => unknown>(() => undefined),
}));

vi.mock("@/api/generated/lerobot/lerobot", () => ({
  useStartLeRobotExport: () => ({ mutate: mutateMock, isPending: false }),
}));

vi.mock("@/hooks/use-api", () => ({
  useLeRobotConfig: () => ({
    data: { configured: true, robot_type: "sim", cameras: ["cam"] },
    isLoading: false,
  }),
}));

// The dialog tracks the enqueued job via useJob; mock it (no QueryClient in this test).
vi.mock("@/hooks/use-jobs-stream", () => ({ useJob: () => jobMock() }));
vi.mock("@/hooks/use-topics-stream", () => ({ useAddLog: () => vi.fn() }));

function renderButton() {
  const wrapper = ({ children }: { children: ReactNode }) => <TooltipProvider>{children}</TooltipProvider>;
  return render(<BulkExportButton />, { wrapper });
}

beforeEach(() => {
  useRecordingsStore.getState().clearChecked();
  mutateMock.mockReset();
  jobMock.mockReset();
  jobMock.mockReturnValue(undefined);
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
  });
});
