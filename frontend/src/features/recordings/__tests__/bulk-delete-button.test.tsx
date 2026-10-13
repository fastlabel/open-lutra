import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TooltipProvider } from "@/components/ui/tooltip";
import { useToastStore } from "@/stores/toast-store";
import { useRecordingsStore } from "../store";
import { BulkDeleteButton } from "../ui/bulk-delete-button";

const { mutateMock, addLogMock } = vi.hoisted(() => ({
  mutateMock: vi.fn(),
  addLogMock: vi.fn(),
}));

vi.mock("@/hooks/use-api", () => ({
  useDeleteRecordings: () => ({ mutate: mutateMock, isPending: false }),
}));

vi.mock("@/hooks/use-topics-stream", () => ({
  useAddLog: () => addLogMock,
}));

function deleteChecked(folders: string[]) {
  useRecordingsStore.getState().setCheckedFolders(folders);
  const wrapper = ({ children }: { children: ReactNode }) => <TooltipProvider>{children}</TooltipProvider>;
  render(<BulkDeleteButton />, { wrapper });
  fireEvent.click(screen.getByRole("button", { name: "Delete" }));
  fireEvent.click(screen.getByRole("button", { name: "Delete" }));
}

beforeEach(() => {
  useRecordingsStore.getState().clearChecked();
});

afterEach(() => {
  vi.clearAllMocks();
  useToastStore.setState({ toasts: [] });
});

describe("BulkDeleteButton", () => {
  it("toasts the count and clears the selection once every recording is deleted", () => {
    mutateMock.mockImplementation((_vars, options) =>
      options.onSuccess({ status: 200, data: { deleted: ["rec_a", "rec_b"] } }),
    );
    deleteChecked(["rec_a", "rec_b"]);

    expect(mutateMock).toHaveBeenCalledWith({ data: { folders: ["rec_a", "rec_b"] } }, expect.anything());
    expect(addLogMock).toHaveBeenCalledWith("info", "Deleted 2 recordings");
    expect(useToastStore.getState().toasts).toMatchObject([{ variant: "success", title: "Deleted 2 recordings" }]);
    expect(useRecordingsStore.getState().checkedFolders.size).toBe(0);
  });

  it("toasts an error naming the recordings that were not deleted", () => {
    mutateMock.mockImplementation((_vars, options) => options.onSuccess({ status: 200, data: { deleted: ["rec_a"] } }));
    deleteChecked(["rec_a", "rec_b", "rec_c"]);

    expect(addLogMock).toHaveBeenCalledWith("info", "Deleted 1 recording");
    expect(useToastStore.getState().toasts).toMatchObject([
      { variant: "error", title: "Deleted 1 of 3 recordings", description: "Not found: rec_b, rec_c" },
    ]);
  });

  it("treats a non-200 response as nothing deleted", () => {
    mutateMock.mockImplementation((_vars, options) => options.onSuccess({ status: 204, data: undefined }));
    deleteChecked(["rec_a"]);

    expect(useToastStore.getState().toasts).toMatchObject([
      { variant: "error", title: "Deleted 0 of 1 recordings", description: "Not found: rec_a" },
    ]);
  });

  it("toasts the error and keeps the selection when the request fails", () => {
    mutateMock.mockImplementation((_vars, options) => options.onError(new Error("Delete failed: rec_a (busy)")));
    deleteChecked(["rec_a"]);

    expect(addLogMock).toHaveBeenCalledWith("danger", "Delete failed: Delete failed: rec_a (busy)");
    expect(useToastStore.getState().toasts).toMatchObject([
      { variant: "error", title: "Failed to delete recordings", description: "Delete failed: rec_a (busy)" },
    ]);
    expect(useRecordingsStore.getState().checkedFolders).toEqual(new Set(["rec_a"]));
  });

  it("falls back to a generic message for non-Error failures", () => {
    mutateMock.mockImplementation((_vars, options) => options.onError("boom"));
    deleteChecked(["rec_a"]);

    expect(useToastStore.getState().toasts).toMatchObject([
      { variant: "error", title: "Failed to delete recordings", description: "Delete failed" },
    ]);
  });
});
