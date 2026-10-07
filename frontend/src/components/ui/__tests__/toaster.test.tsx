import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TOAST_DURATION_MS, toast, useToastStore } from "@/stores/toast-store";
import { Toaster } from "../toaster";

describe("Toaster", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    useToastStore.setState({ toasts: [] });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("auto-dismisses a toast after its duration", () => {
    render(<Toaster />);
    act(() => {
      toast.info("Hello");
    });
    expect(screen.getByText("Hello")).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(TOAST_DURATION_MS + 100);
    });
    expect(screen.queryByText("Hello")).not.toBeInTheDocument();
  });

  it("keeps auto-dismissing after a toast is closed while hovered", () => {
    render(<Toaster />);
    act(() => {
      toast.info("First");
    });

    const viewport = screen.getByRole("region");
    fireEvent.pointerMove(viewport);
    fireEvent.click(screen.getByRole("button", { name: /close/i }));
    expect(screen.queryByText("First")).not.toBeInTheDocument();

    act(() => {
      toast.info("Second");
    });
    expect(screen.getByText("Second")).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(TOAST_DURATION_MS + 100);
    });
    expect(screen.queryByText("Second")).not.toBeInTheDocument();
  });
});
