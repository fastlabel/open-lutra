import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RecordingGlow } from "../recording-glow";

const { useIsRecordingMock } = vi.hoisted(() => ({ useIsRecordingMock: vi.fn<() => boolean>() }));

vi.mock("@/hooks/use-api", () => ({
  useIsRecording: () => useIsRecordingMock(),
}));

afterEach(() => {
  useIsRecordingMock.mockReset();
});

describe("RecordingGlow", () => {
  it("renders the edge glow while recording", () => {
    useIsRecordingMock.mockReturnValue(true);
    render(<RecordingGlow />);
    expect(screen.getByTestId("recording-glow")).toBeInTheDocument();
  });

  it("renders nothing when not recording", () => {
    useIsRecordingMock.mockReturnValue(false);
    render(<RecordingGlow />);
    expect(screen.queryByTestId("recording-glow")).not.toBeInTheDocument();
  });
});
