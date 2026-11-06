/** Current time that advances once per local midnight, so day-scoped views roll over without a reload. */

import { useEffect, useState } from "react";
import { msUntilNextLocalMidnight } from "./day-range";

/** Fire slightly after midnight so the new Date is unambiguously on the next day. */
const ROLLOVER_MARGIN_MS = 1000;

export function useLocalDay(): Date {
  const [now, setNow] = useState(() => new Date());

  // --- Side effects ---
  // Re-armed on every rollover; the delay is recomputed each day, so 23 h / 25 h DST days stay correct.
  useEffect(() => {
    const timer = setTimeout(() => setNow(new Date()), msUntilNextLocalMidnight(now) + ROLLOVER_MARGIN_MS);
    return () => clearTimeout(timer);
  }, [now]);

  return now;
}
