import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { RecordingControl } from "../recording-control";

vi.mock("@/features/collection-stats", () => ({
  CollectionStatsSummary: () => <div data-testid="collection-stats-summary" />,
}));
vi.mock("@/features/settings", () => ({
  RecordingMetadataPanel: () => null,
  TaskNameInlineEditor: () => null,
}));
vi.mock("@/hooks/use-api", () => ({
  useConfig: () => ({ data: undefined }),
  useIsRecording: () => false,
}));
vi.mock("@/hooks/use-topics-stream", () => ({ useTopicStats: () => [] }));
vi.mock("../record-button", () => ({ RecordButton: () => null }));
vi.mock("../timer", () => ({ Timer: () => null }));
vi.mock("../store", () => ({
  DELAY_OPTIONS: [0],
  useRecordingStore: (selector: (s: Record<string, unknown>) => unknown) =>
    selector({
      countdownSec: null,
      isStarting: false,
      isStopping: false,
      delaySec: 0,
      setDelay: () => {},
      soundEnabled: true,
      setSoundEnabled: () => {},
    }),
}));

describe("RecordingControl", () => {
  it("mounts today's collection summary in the recording bar", () => {
    render(<RecordingControl />);
    expect(screen.getByTestId("collection-stats-summary")).toBeInTheDocument();
  });
});
