import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";
import { getGetRecordingsQueryKey } from "@/api/generated/recordings/recordings";
import { localDayRange } from "../day-range";

// Stop, delete, and validation / upload completion refresh the summary by invalidating the unparameterized
// recordings key; this locks in that it prefix-matches the day-filtered key the summary queries.
describe("today's recordings query key", () => {
  it("is invalidated by the unparameterized recordings key", async () => {
    const client = new QueryClient();
    const todayKey = getGetRecordingsQueryKey(localDayRange(new Date(2026, 10, 6)));
    client.setQueryData(todayKey, { stub: true });

    await client.invalidateQueries({ queryKey: getGetRecordingsQueryKey() });

    expect(client.getQueryState(todayKey)?.isInvalidated).toBe(true);
  });
});
