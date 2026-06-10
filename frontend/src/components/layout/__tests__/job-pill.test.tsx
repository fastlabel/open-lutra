import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { JobSchema } from "@/api/generated/schemas";
import { isInFlight, JobPill } from "../job-pill";

function makeJob(overrides: Partial<JobSchema> = {}): JobSchema {
  return {
    job_id: "j1",
    type: "validation",
    folder: "rec_001",
    status: "running",
    progress: { step: "", step_label: "", current: 0, total: 1 },
    error: null,
    created_at: "2026-05-25T00:00:00",
    started_at: null,
    finished_at: null,
    ...overrides,
  };
}

describe("isInFlight", () => {
  it.each(["queued", "running"] as const)("returns true for status=%s", (status) => {
    expect(isInFlight(makeJob({ status }))).toBe(true);
  });

  it.each(["completed", "failed"] as const)("returns false for status=%s", (status) => {
    expect(isInFlight(makeJob({ status }))).toBe(false);
  });
});

describe("JobPill", () => {
  it.each([
    ["validation", "Validation"],
    ["quality", "Quality"],
    ["timeline", "Timeline"],
    ["media", "Media"],
    ["lerobot_export", "LeRobot"],
  ])("renders the %s label", (type, label) => {
    render(<JobPill job={makeJob({ type })} />);
    expect(screen.getByText(label)).toBeInTheDocument();
  });

  it("falls back to 'Job' label for unknown job types", () => {
    render(<JobPill job={makeJob({ type: "mystery" })} />);
    expect(screen.getByText("Job")).toBeInTheDocument();
  });

  it("shows progress fraction only while running and total > 1", () => {
    const { rerender } = render(
      <JobPill
        job={makeJob({
          status: "running",
          progress: { step: "frames", step_label: "frames", current: 3, total: 10 },
        })}
      />,
    );
    expect(screen.getByText("3/10")).toBeInTheDocument();

    rerender(
      <JobPill
        job={makeJob({
          status: "running",
          progress: { step: "frames", step_label: "frames", current: 0, total: 1 },
        })}
      />,
    );
    expect(screen.queryByText(/\d+\/\d+/)).not.toBeInTheDocument();

    rerender(
      <JobPill
        job={makeJob({
          status: "queued",
          progress: { step: "frames", step_label: "frames", current: 0, total: 10 },
        })}
      />,
    );
    // queued: no progress numbers (work hasn't started)
    expect(screen.queryByText(/\d+\/\d+/)).not.toBeInTheDocument();
  });
});
