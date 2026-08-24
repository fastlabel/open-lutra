import { describe, expect, it } from "vitest";
import type { TopicInfo } from "@/api/generated/schemas";
import { mergeTopicStatsDelta } from "../topic-stats-delta";

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

describe("mergeTopicStatsDelta", () => {
  it("replaces changed rows in place and keeps their position", () => {
    const a = makeTopic("/a");
    const b = makeTopic("/b");
    const changedA = makeTopic("/a", { actual_hz: 10, status: "ok" });

    const merged = mergeTopicStatsDelta([a, b], { changed: [changedA], removed: [] });

    expect(merged).toEqual([changedA, b]);
    expect(merged[0]).toBe(changedA);
  });

  it("keeps object identity for unchanged rows", () => {
    const a = makeTopic("/a");
    const b = makeTopic("/b");

    const merged = mergeTopicStatsDelta([a, b], { changed: [makeTopic("/a", { actual_hz: 5 })], removed: [] });

    expect(merged[1]).toBe(b);
  });

  it("removes vanished rows", () => {
    const merged = mergeTopicStatsDelta([makeTopic("/a"), makeTopic("/gone")], { changed: [], removed: ["/gone"] });

    expect(merged.map((t) => t.name)).toEqual(["/a"]);
  });

  it("appends rows first seen in a delta (newly discovered topics)", () => {
    const a = makeTopic("/a");
    const fresh = makeTopic("/new");

    const merged = mergeTopicStatsDelta([a], { changed: [fresh], removed: [] });

    expect(merged).toEqual([a, fresh]);
  });

  it("returns an equal list for an empty delta", () => {
    const prev = [makeTopic("/a"), makeTopic("/b")];

    expect(mergeTopicStatsDelta(prev, { changed: [], removed: [] })).toEqual(prev);
  });

  it("merges from an empty previous list (delta before any snapshot)", () => {
    const fresh = makeTopic("/new");

    expect(mergeTopicStatsDelta([], { changed: [fresh], removed: ["/stale"] })).toEqual([fresh]);
  });
});
