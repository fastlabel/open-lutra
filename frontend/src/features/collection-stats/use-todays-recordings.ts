/** Recordings that started on the operator's current local day; follows the date across midnight. */

import { useFiles } from "@/hooks/use-api";
import { localDayRange } from "./day-range";
import { useLocalDay } from "./use-local-day";

export function useTodaysRecordings() {
  return useFiles(localDayRange(useLocalDay()));
}
