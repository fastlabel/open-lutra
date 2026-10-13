import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { FileEntry } from "@/api/generated/schemas";
import { useRecordingsStore } from "../store";
import { RecordingListItem } from "../ui/recording-list-item";

const { navigateMock } = vi.hoisted(() => ({ navigateMock: vi.fn() }));

vi.mock("@tanstack/react-router", () => ({ useNavigate: () => navigateMock }));
vi.mock("@/features/upload", () => ({ UploadBadge: () => null }));
vi.mock("@/features/validation", () => ({ ValidationBadge: () => null }));
vi.mock("@/hooks/use-api", () => ({
  useConfig: () => ({ data: undefined }),
  useDeleteRecordings: () => ({ mutate: vi.fn(), isPending: false }),
  useRenameRecording: () => ({ mutate: vi.fn(), isPending: false }),
  useUpdateRecordingMeta: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock("@/hooks/use-topics-stream", () => ({ useAddLog: () => vi.fn() }));

const DISPLAYED = ["rec_a", "rec_b", "rec_c", "rec_d"];

function makeEntry(name: string): FileEntry {
  return {
    name,
    path: name,
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
    metadata: {},
  };
}

function renderRows(displayedFolders?: string[], checkDisabled?: boolean) {
  render(
    <div>
      {DISPLAYED.map((name) => (
        <RecordingListItem
          key={name}
          entry={makeEntry(name)}
          displayedFolders={displayedFolders}
          checkDisabled={checkDisabled}
        />
      ))}
    </div>,
  );
}

const checkbox = (name: string) => screen.getByRole("checkbox", { name: `Select ${name}` });
/** The widened hit area wrapping the checkbox. */
const checkCell = (name: string) => checkbox(name).parentElement as HTMLElement;

beforeEach(() => {
  useRecordingsStore.getState().clearChecked();
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("RecordingListItem checkbox", () => {
  it("selects the displayed range on Shift+click after a plain click", () => {
    renderRows(DISPLAYED);

    fireEvent.click(checkbox("rec_b"));
    fireEvent.click(checkbox("rec_d"), { shiftKey: true });

    expect(useRecordingsStore.getState().checkedFolders).toEqual(new Set(["rec_b", "rec_c", "rec_d"]));
    expect(checkbox("rec_c")).toHaveAttribute("aria-checked", "true");
    expect(checkbox("rec_a")).toHaveAttribute("aria-checked", "false");
  });

  it("toggles only the clicked row on Shift+click when the display order is unknown", () => {
    renderRows();

    fireEvent.click(checkbox("rec_a"));
    fireEvent.click(checkbox("rec_c"), { shiftKey: true });

    expect(useRecordingsStore.getState().checkedFolders).toEqual(new Set(["rec_a", "rec_c"]));
  });

  it("toggles the row from a click anywhere in the checkbox cell without opening the recording", () => {
    renderRows(DISPLAYED);

    fireEvent.click(checkCell("rec_b"));
    expect(checkbox("rec_b")).toHaveAttribute("aria-checked", "true");

    fireEvent.click(checkCell("rec_b"));
    expect(checkbox("rec_b")).toHaveAttribute("aria-checked", "false");
    expect(navigateMock).not.toHaveBeenCalled();
  });

  it("selects a range on Shift+click in the checkbox cell", () => {
    renderRows(DISPLAYED);

    fireEvent.click(checkCell("rec_a"));
    fireEvent.click(checkCell("rec_c"), { shiftKey: true });

    expect(useRecordingsStore.getState().checkedFolders).toEqual(new Set(["rec_a", "rec_b", "rec_c"]));
  });

  it("ignores clicks in the checkbox cell while checking is disabled", () => {
    renderRows(DISPLAYED, true);

    fireEvent.click(checkCell("rec_a"));

    expect(useRecordingsStore.getState().checkedFolders.size).toBe(0);
    expect(navigateMock).not.toHaveBeenCalled();
  });

  it("suppresses text selection on Shift+mousedown only", () => {
    renderRows(DISPLAYED);

    expect(fireEvent.mouseDown(checkCell("rec_a"), { shiftKey: true })).toBe(false);
    expect(fireEvent.mouseDown(checkCell("rec_a"))).toBe(true);
  });
});
