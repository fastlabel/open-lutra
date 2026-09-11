import { describe, expect, it } from "vitest";
import type { TopicInfo } from "@/api/generated/schemas";
import { upsertTopicStats } from "../topic-stats";

function makeTopic(name: string, overrides: Partial<TopicInfo> = {}): TopicInfo {
  return {
    name,
    msg_type: "std_msgs/msg/String",
    actual_hz: 0,
    status: "inactive",
    message_count: 0,
    is_subscribed: false,
    baseline_hz: null,
    baseline_fixed: false,
    loss_rate: 0,
    drop_count: 0,
    continuity_score: 1,
    qos_reliability: "",
    ...overrides,
  };
}

describe("upsertTopicStats", () => {
  it("replaces changed rows in place and keeps their position", () => {
    const a = makeTopic("/a");
    const b = makeTopic("/b");
    const changedA = makeTopic("/a", { actual_hz: 10, status: "ok" });

    const merged = upsertTopicStats([a, b], [changedA]);

    expect(merged).toEqual([changedA, b]);
    expect(merged[0]).toBe(changedA);
  });

  it("keeps object identity for unchanged rows", () => {
    const a = makeTopic("/a");
    const b = makeTopic("/b");

    const merged = upsertTopicStats([a, b], [makeTopic("/a", { actual_hz: 5 })]);

    expect(merged[1]).toBe(b);
  });

  it("appends rows first seen in an event (newly discovered topics)", () => {
    const a = makeTopic("/a");
    const fresh = makeTopic("/new");

    const merged = upsertTopicStats([a], [fresh]);

    expect(merged).toEqual([a, fresh]);
  });

  it("returns the previous list unchanged (same reference) for an empty event", () => {
    const prev = [makeTopic("/a"), makeTopic("/b")];

    expect(upsertTopicStats(prev, [])).toBe(prev);
  });

  it("merges from an empty previous list", () => {
    const fresh = makeTopic("/new");

    expect(upsertTopicStats([], [fresh])).toEqual([fresh]);
  });
});
