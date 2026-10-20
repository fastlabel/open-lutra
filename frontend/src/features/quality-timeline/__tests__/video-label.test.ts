import { describe, expect, it } from "vitest";
import { videoTopicLabel } from "../video-label";

describe("videoTopicLabel", () => {
  it("restores the topic name from a full-topic filename", () => {
    expect(videoTopicLabel("observation.images.camera-color-image_raw-compressed.mp4")).toBe(
      "/camera/color/image_raw/compressed",
    );
  });

  it("keeps underscores inside segments", () => {
    expect(videoTopicLabel("observation.images.left_arm_depth_cam-color.mp4")).toBe("/left_arm_depth_cam/color");
  });

  it("shows a single-segment name as a one-segment topic", () => {
    expect(videoTopicLabel("observation.images.chest_depth_cam.mp4")).toBe("/chest_depth_cam");
  });
});
