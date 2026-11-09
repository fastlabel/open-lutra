/** Duration format for a day's collected total: `16s`, `32m 10s`, `1h 05m` (hours drop the seconds). */
export function formatCollectedDuration(sec: number): string {
  const total = Math.floor(sec);
  if (total < 60) return `${total}s`;
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  if (h === 0) return `${m}m ${String(total % 60).padStart(2, "0")}s`;
  return `${h}h ${String(m).padStart(2, "0")}m`;
}
