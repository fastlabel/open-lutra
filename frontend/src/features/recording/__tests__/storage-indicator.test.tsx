import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { StorageInfo } from "@/api/generated/schemas";
import { StorageIndicator } from "../storage-indicator";

type StorageResult = {
  data: StorageInfo | undefined;
  isPending: boolean;
  isFetching: boolean;
  refetch: () => void;
};

const { useStorageMock, refetchMock } = vi.hoisted(() => ({
  useStorageMock: vi.fn<() => StorageResult>(),
  refetchMock: vi.fn(),
}));

vi.mock("@/hooks/use-api", () => ({
  useStorage: () => useStorageMock(),
}));

function storage(overrides: Partial<StorageInfo> = {}): StorageInfo {
  return { path: "/data/output", free_bytes: 731 * 1024 ** 3, ...overrides };
}

function result(overrides: Partial<StorageResult> = {}): StorageResult {
  return { data: storage(), isPending: false, isFetching: false, refetch: refetchMock, ...overrides };
}

beforeEach(() => {
  useStorageMock.mockReturnValue(result());
});

afterEach(() => {
  useStorageMock.mockReset();
  refetchMock.mockReset();
});

describe("StorageIndicator", () => {
  it("renders the free space of the output volume, with the volume in the tooltip", () => {
    render(<StorageIndicator />);
    expect(screen.getByText("731 GB free")).toHaveAttribute("title", "/data/output");
  });

  it("says it is still reading before the first fetch resolves", () => {
    // Distinct from a failure: a normal page load must not read as an error.
    useStorageMock.mockReturnValue(result({ data: undefined, isPending: true, isFetching: true }));
    render(<StorageIndicator />);
    expect(screen.getByText("Reading…")).toBeInTheDocument();
  });

  it("reports a failed request separately from an uninspectable volume", () => {
    useStorageMock.mockReturnValue(result({ data: undefined }));
    render(<StorageIndicator />);
    expect(screen.getByText("Read failed")).toBeInTheDocument();
  });

  it("names the volume it could not inspect", () => {
    useStorageMock.mockReturnValue(result({ data: storage({ free_bytes: null }) }));
    render(<StorageIndicator />);
    expect(screen.getByText("Unavailable")).toHaveAttribute("title", "Cannot inspect /data/output");
  });

  it("re-reads the volume when the refresh button is pressed", () => {
    render(<StorageIndicator />);
    fireEvent.click(screen.getByLabelText("Refresh free space"));
    expect(refetchMock).toHaveBeenCalledOnce();
  });

  it("disables the refresh button while a read is in flight", () => {
    useStorageMock.mockReturnValue(result({ isFetching: true }));
    render(<StorageIndicator />);
    expect(screen.getByLabelText("Refresh free space")).toBeDisabled();
  });
});
