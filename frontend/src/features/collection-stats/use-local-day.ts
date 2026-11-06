/** Current time that changes only when the local date does, so day-scoped views roll over without a reload. */

import { useEffect, useState } from "react";

/** How often the local date is re-checked. The rollover lands at most this long after midnight or a wake-up. */
const DAY_CHECK_INTERVAL_MS = 60_000;

export function useLocalDay(): Date {
  const [now, setNow] = useState(() => new Date());

  // --- Side effects ---
  // Polls rather than scheduling one timeout to midnight: timers do not advance while the machine sleeps, so a
  // single long timeout can fire hours late. Within the same date the previous value is kept, so nothing re-renders.
  useEffect(() => {
    const timer = setInterval(() => {
      const next = new Date();
      setNow((prev) => (prev.toDateString() === next.toDateString() ? prev : next));
    }, DAY_CHECK_INTERVAL_MS);
    return () => clearInterval(timer);
  }, []);

  return now;
}
