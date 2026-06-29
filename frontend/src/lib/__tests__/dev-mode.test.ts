import { afterEach, describe, expect, it, vi } from "vitest";
import { isDevMode } from "../dev-mode";

describe("isDevMode", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("returns false when VITE_DEV_MODE is unset", () => {
    expect(isDevMode()).toBe(false);
  });

  it("returns true only when VITE_DEV_MODE is exactly 'true'", () => {
    vi.stubEnv("VITE_DEV_MODE", "true");
    expect(isDevMode()).toBe(true);
  });

  it("returns false for any other value", () => {
    vi.stubEnv("VITE_DEV_MODE", "1");
    expect(isDevMode()).toBe(false);
  });
});
