import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { StorageInfo } from "@/api/generated/schemas";
import { StorageIndicator } from "../storage-indicator";

type StorageResult = { data: StorageInfo | undefined; isFetching: boolean; refetch: () => void };

const { useStorageMock, refetchMock } = vi.hoisted(() => ({
  useStorageMock: vi.fn<() => StorageResult>(),
  refetchMock: vi.fn(),
}));

vi.mock("@/hooks/use-api", () => ({
  useStorage: () => useStorageMock(),
}));

function storage(overrides: Partial<StorageInfo> = {}): StorageInfo {
  return {
    path: "/data/output",
    total_bytes: 1024 ** 4,
    used_bytes: 224 * 1024 ** 3,
    free_bytes: 731 * 1024 ** 3,
    ...overrides,
  };
}

beforeEach(() => {
  useStorageMock.mockReturnValue({ data: storage(), isFetching: false, refetch: refetchMock });
});

afterEach(() => {
  useStorageMock.mockReset();
  refetchMock.mockReset();
});

describe("StorageIndicator", () => {
  it("renders the free space of the output volume", () => {
    render(<StorageIndicator />);
    expect(screen.getByText("731 GB free")).toBeInTheDocument();
  });

  it("reports an uninspectable volume instead of a byte count", () => {
    useStorageMock.mockReturnValue({
      data: storage({ total_bytes: null, used_bytes: null, free_bytes: null }),
      isFetching: false,
      refetch: refetchMock,
    });
    render(<StorageIndicator />);
    expect(screen.getByText("Unavailable")).toBeInTheDocument();
  });

  it("renders before the first fetch resolves", () => {
    useStorageMock.mockReturnValue({ data: undefined, isFetching: true, refetch: refetchMock });
    render(<StorageIndicator />);
    expect(screen.getByText("Unavailable")).toBeInTheDocument();
  });

  it("re-reads the volume when the refresh button is pressed", () => {
    render(<StorageIndicator />);
    fireEvent.click(screen.getByLabelText("Refresh free space"));
    expect(refetchMock).toHaveBeenCalledOnce();
  });

  it("disables the refresh button while a read is in flight", () => {
    useStorageMock.mockReturnValue({ data: storage(), isFetching: true, refetch: refetchMock });
    render(<StorageIndicator />);
    expect(screen.getByLabelText("Refresh free space")).toBeDisabled();
  });
});
