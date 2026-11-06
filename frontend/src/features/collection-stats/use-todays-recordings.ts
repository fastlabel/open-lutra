/** Recordings that started on the operator's current local day; follows the date across midnight. */

import { useFiles } from "@/hooks/use-api";
import { localDayRange } from "./day-range";
import { useLocalDay } from "./use-local-day";

export function useTodaysRecordings() {
  // Keep the previous day's list while the new day's range loads, so the chip does not disappear at midnight.
  return useFiles(localDayRange(useLocalDay()), { keepPreviousWhileLoading: true });
}
