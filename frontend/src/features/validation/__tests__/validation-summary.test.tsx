import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ValidationResponse } from "@/api/generated/schemas";
import { ValidationSummary } from "../validation-summary";

// Mock the API hooks directly so the component tests do not depend on
// the query-client or fetch infrastructure. `vi.hoisted` lets the mock
// references survive the hoisting that `vi.mock` performs.
const { useValidationMock, startAnalysisMock, useStartValidationMock } = vi.hoisted(() => ({
  useValidationMock: vi.fn<() => { data: ValidationResponse | undefined; isLoading: boolean }>(() => ({
    data: undefined,
    isLoading: false,
  })),
  startAnalysisMock: vi.fn(),
  useStartValidationMock: vi.fn(),
}));

vi.mock("@/hooks/use-api", () => ({
  useValidation: () => useValidationMock(),
  useStartValidation: () => useStartValidationMock(),
}));

beforeEach(() => {
  useValidationMock.mockReturnValue({ data: undefined, isLoading: false });
  useStartValidationMock.mockReturnValue({ mutate: startAnalysisMock, isPending: false });
});

afterEach(() => {
  useValidationMock.mockReset();
  useStartValidationMock.mockReset();
  startAnalysisMock.mockReset();
});

describe("ValidationSummary", () => {
  it("shows a placeholder when folderPath is null", () => {
    render(<ValidationSummary selectedFolder={null} />);
    expect(screen.getByText(/Select a recording/i)).toBeInTheDocument();
  });

  it("shows a spinner while analyzing", () => {
    useValidationMock.mockReturnValue({
      data: { status: "analyzing", report: null, error: null },
      isLoading: false,
    });
    render(<ValidationSummary selectedFolder="rec_001" />);
    expect(screen.getByText(/Running validators/i)).toBeInTheDocument();
  });

  it("displays the error-state message", () => {
    useValidationMock.mockReturnValue({
      data: { status: "error", report: null, error: "boom" },
      isLoading: false,
    });
    render(<ValidationSummary selectedFolder="rec_001" />);
    expect(screen.getByText(/Validation error: boom/i)).toBeInTheDocument();
  });

  it("calls startAnalysis when status is not_found and triggerAnalysis=true", async () => {
    useValidationMock.mockReturnValue({
      data: { status: "not_found", report: null, error: null },
      isLoading: false,
    });
    render(<ValidationSummary selectedFolder="rec_001" triggerAnalysis />);
    await waitFor(() => expect(startAnalysisMock).toHaveBeenCalledWith({ params: { path: "rec_001" } }));
  });

  it("does not call startAnalysis when triggerAnalysis=false even if not_found", () => {
    useValidationMock.mockReturnValue({
      data: { status: "not_found", report: null, error: null },
      isLoading: false,
    });
    render(<ValidationSummary selectedFolder="rec_001" />);
    expect(startAnalysisMock).not.toHaveBeenCalled();
  });

  it("shows 'No validators configured' for ready with empty report", () => {
    useValidationMock.mockReturnValue({
      data: {
        status: "ready",
        report: {
          overall_status: "pass",
          results: [],
          task_name: null,
          executed_at: "2026-05-25T00:00:00",
        },
        error: null,
      },
      isLoading: false,
    });
    render(<ValidationSummary selectedFolder="rec_001" />);
    expect(screen.getByText(/No validators configured/i)).toBeInTheDocument();
  });

  it("renders validator results and overall status when ready", () => {
    useValidationMock.mockReturnValue({
      data: {
        status: "ready",
        report: {
          overall_status: "warn",
          results: [
            {
              validator_name: "required_topics_present",
              source: "builtin",
              source_module: null,
              status: "pass",
              message: "All required topics present",
              details: null,
            },
            {
              validator_name: "total_duration_sec",
              source: "custom",
              source_module: "app.features.validation.custom.my_check",
              status: "warn",
              message: "Recording is short",
              details: null,
            },
          ],
          task_name: "pick",
          executed_at: "2026-05-25T00:00:00",
        },
        error: null,
      },
      isLoading: false,
    });
    render(<ValidationSummary selectedFolder="rec_001" />);

    expect(screen.getByText("required_topics_present")).toBeInTheDocument();
    expect(screen.getByText(/All required topics present/i)).toBeInTheDocument();
    expect(screen.getByText("total_duration_sec")).toBeInTheDocument();
    expect(screen.getByText(/Recording is short/i)).toBeInTheDocument();
    expect(screen.getByText("custom")).toBeInTheDocument();
  });

  it("renders an unknown status as error (fallback)", () => {
    useValidationMock.mockReturnValue({
      data: {
        status: "ready",
        report: {
          overall_status: "bogus",
          results: [
            {
              validator_name: "weird",
              source: "builtin",
              source_module: null,
              status: "bogus",
              message: "",
              details: null,
            },
          ],
          task_name: null,
          executed_at: "2026-05-25T00:00:00",
        },
        error: null,
      } as unknown as ValidationResponse,
      isLoading: false,
    });
    const { container } = render(<ValidationSummary selectedFolder="rec_001" />);
    // Expect at least 2 error badges (header + row)
    const errorBadges = container.querySelectorAll('[data-status="error"]');
    expect(errorBadges.length).toBeGreaterThanOrEqual(2);
  });

  it("shows a spinner when isLoading=true (data not yet received)", () => {
    useValidationMock.mockReturnValue({ data: undefined, isLoading: true });
    render(<ValidationSummary selectedFolder="rec_001" />);
    expect(screen.getByText(/Running validators/i)).toBeInTheDocument();
  });

  it("toggles formatted details JSON when a row with details is clicked", () => {
    useValidationMock.mockReturnValue({
      data: {
        status: "ready",
        report: {
          overall_status: "fail",
          results: [
            {
              validator_name: "required_topics_present",
              source: "builtin",
              source_module: null,
              status: "fail",
              message: "Missing required topics",
              details: { missing_topics: ["/cam/front"], required_topics: ["/cam/front", "/joint_states"] },
            },
          ],
          task_name: null,
          executed_at: "2026-05-25T00:00:00",
        },
        error: null,
      },
      isLoading: false,
    });
    render(<ValidationSummary selectedFolder="rec_001" />);

    // Collapsed by default — JSON not visible.
    expect(screen.queryByText(/missing_topics/)).not.toBeInTheDocument();

    const toggle = screen.getByRole("button", { name: /required_topics_present/i });
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    // Formatted JSON appears with both keys visible.
    expect(screen.getByText(/"missing_topics"/)).toBeInTheDocument();
    expect(screen.getByText(/"\/cam\/front"/)).toBeInTheDocument();

    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText(/"missing_topics"/)).not.toBeInTheDocument();
  });

  it("does not render a toggle for rows without details", () => {
    useValidationMock.mockReturnValue({
      data: {
        status: "ready",
        report: {
          overall_status: "pass",
          results: [
            {
              validator_name: "required_topics_present",
              source: "builtin",
              source_module: null,
              status: "pass",
              message: "All required topics present",
              details: null,
            },
          ],
          task_name: null,
          executed_at: "2026-05-25T00:00:00",
        },
        error: null,
      },
      isLoading: false,
    });
    render(<ValidationSummary selectedFolder="rec_001" />);
    expect(screen.queryByRole("button", { name: /required_topics_present/i })).not.toBeInTheDocument();
  });

  it("shows the no-results message when status is unknown / report is not fetched", () => {
    useValidationMock.mockReturnValue({
      data: { status: "ready", report: null, error: null },
      isLoading: false,
    });
    render(<ValidationSummary selectedFolder="rec_001" />);
    expect(screen.getByText(/No validation results yet/i)).toBeInTheDocument();
  });
});
