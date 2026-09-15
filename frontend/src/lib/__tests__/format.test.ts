import { describe, expect, it } from "vitest";
import { formatDuration, formatElapsed, formatRecordingDate, formatSize } from "../format";

describe("formatSize", () => {
  it("renders 0 bytes", () => {
    expect(formatSize(0)).toBe("0B");
  });

  it("renders in bytes (below 1024)", () => {
    expect(formatSize(512)).toBe("512B");
    expect(formatSize(1023)).toBe("1023B");
  });

  it("renders in KB (1024 and above, below 1MB)", () => {
    expect(formatSize(1024)).toBe("1.0KB");
    expect(formatSize(1536)).toBe("1.5KB");
    expect(formatSize(1024 * 1024 - 1)).toBe("1024.0KB");
  });

  it("renders in MB (1MB and above, below 1GB)", () => {
    expect(formatSize(1024 * 1024)).toBe("1.0MB");
    expect(formatSize(1024 * 1024 * 500)).toBe("500.0MB");
  });

  it("renders in GB (1GB and above)", () => {
    expect(formatSize(1024 * 1024 * 1024)).toBe("1.00GB");
    expect(formatSize(1024 * 1024 * 1024 * 5.4)).toBe("5.40GB");
  });
});

describe("formatRecordingDate", () => {
  it("returns --- for null", () => {
    expect(formatRecordingDate(null)).toBe("---");
  });

  it("returns MM/DD HH:mm with only a start time (no durationNs)", () => {
    const startNs = new Date("2025-01-15T09:30:00Z").getTime() * 1_000_000;
    const result = formatRecordingDate(startNs);
    // Timezone-dependent, but verify the MM/DD HH:mm shape
    expect(result).toMatch(/^\d{2}\/\d{2} \d{2}:\d{2}$/);
  });

  it("returns MM/DD HH:mm~HH:mm when durationNs is provided", () => {
    const startNs = new Date("2025-01-15T09:30:00Z").getTime() * 1_000_000;
    const durationNs = 90 * 60 * 1_000_000_000;
    const result = formatRecordingDate(startNs, durationNs);
    expect(result).toMatch(/^\d{2}\/\d{2} \d{2}:\d{2}~\d{2}:\d{2}$/);
  });

  it("returns only the start time when durationNs is null", () => {
    const startNs = new Date("2025-01-15T09:30:00Z").getTime() * 1_000_000;
    const result = formatRecordingDate(startNs, null);
    expect(result).toMatch(/^\d{2}\/\d{2} \d{2}:\d{2}$/);
  });
});

describe("formatDuration", () => {
  it("renders 0 seconds", () => {
    expect(formatDuration(0)).toBe("0.0s");
  });

  it("renders in seconds below 60s", () => {
    expect(formatDuration(1.5)).toBe("1.5s");
    expect(formatDuration(59.9)).toBe("59.9s");
  });

  it("renders in minutes and seconds at 60s and above", () => {
    expect(formatDuration(60)).toBe("1m 0s");
    expect(formatDuration(90)).toBe("1m 30s");
    expect(formatDuration(3661)).toBe("61m 1s");
  });

  it("rounds the fractional second (at 60s and above)", () => {
    expect(formatDuration(90.7)).toBe("1m 31s");
  });
});

describe("formatElapsed", () => {
  it("renders seconds with 1 decimal place below 60s", () => {
    expect(formatElapsed(0)).toBe("0.0s");
    expect(formatElapsed(12.34)).toBe("12.3s");
    expect(formatElapsed(59.9)).toBe("59.9s");
  });

  it("renders as M:SS with zero-padded seconds at 60s and above", () => {
    expect(formatElapsed(60)).toBe("1:00");
    expect(formatElapsed(75)).toBe("1:15");
    expect(formatElapsed(125.9)).toBe("2:05");
    expect(formatElapsed(3600)).toBe("60:00");
  });
});
