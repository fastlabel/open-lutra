/** General-purpose formatting utilities. */

/** Format a byte count into a human-readable string. */
export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)}GB`;
}

/** Format a storage capacity coarsely (whole GB, one decimal below 10GB or in TB).
 *
 * Deliberately less precise than formatSize: a volume's free space is read at a
 * few discrete moments rather than continuously, and digits that imply live
 * tracking would misrepresent how fresh the number is.
 */
export function formatCapacity(bytes: number): string {
  const gb = bytes / (1024 * 1024 * 1024);
  if (gb >= 1024) return `${(gb / 1024).toFixed(1)} TB`;
  if (gb >= 10) return `${Math.round(gb)} GB`;
  if (gb >= 1) return `${gb.toFixed(1)} GB`;
  return `${Math.round(bytes / (1024 * 1024))} MB`;
}

/** Format a recording time (nanoseconds) as "MM/DD HH:mm~HH:mm". */
export function formatRecordingDate(startNs: number | null, durationNs?: number | null): string {
  if (startNs == null) return "---";
  const startMs = startNs / 1_000_000;
  const d = new Date(startMs);
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  const startTime = `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  if (durationNs == null) return `${month}/${day} ${startTime}`;
  const end = new Date(startMs + durationNs / 1_000_000);
  const endTime = `${String(end.getHours()).padStart(2, "0")}:${String(end.getMinutes()).padStart(2, "0")}`;
  return `${month}/${day} ${startTime}~${endTime}`;
}

/** Format a duration in seconds as MM:SS.s. */
export function formatDuration(sec: number): string {
  if (sec < 60) return `${sec.toFixed(1)}s`;
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}m ${s.toFixed(0)}s`;
}

/** Format a duration in seconds for chart axis labels. Under 60s: 1 decimal place; otherwise M:SS. */
export function formatElapsed(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  if (sec < 60) return `${s.toFixed(1)}s`;
  return `${m}:${Math.floor(s).toString().padStart(2, "0")}`;
}
