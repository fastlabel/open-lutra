import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { Header } from "../header";

vi.mock("@tanstack/react-router", () => ({
  Link: ({ children }: { children: ReactNode }) => <a href="/">{children}</a>,
}));

describe("Header", () => {
  it("renders the right-hand slot", () => {
    render(<Header right={<button type="button">Utility</button>} />);
    expect(screen.getByRole("button", { name: "Utility" })).toBeInTheDocument();
  });

  it("renders only the brand and navigation without a right-hand slot", () => {
    render(<Header />);
    expect(screen.getByText("Recordings")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
