/** The operator's local calendar day, expressed as the start-time filter of `GET /api/recordings`.
 *
 * "Today" is `[local midnight, next local midnight)` in the browser's time zone. Each bound carries its
 * own UTC offset, so a day that crosses a daylight-saving change still maps to the right instants.
 */

export function localDayRange(now: Date) {
  return {
    started_after: toLocalRfc3339(startOfLocalDay(now, 0)),
    started_before: toLocalRfc3339(startOfLocalDay(now, 1)),
  };
}

/** Format a Date as RFC 3339 in local time with its UTC offset (e.g. `2026-11-06T00:00:00+09:00`). */
export function toLocalRfc3339(date: Date): string {
  const offsetMin = -date.getTimezoneOffset();
  const absOffset = Math.abs(offsetMin);
  const sign = offsetMin >= 0 ? "+" : "-";
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}` +
    `${sign}${pad(Math.floor(absOffset / 60))}:${pad(absOffset % 60)}`
  );
}

function startOfLocalDay(date: Date, dayOffset: number): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate() + dayOffset);
}

function pad(n: number): string {
  return String(n).padStart(2, "0");
}
