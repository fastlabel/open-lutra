/**
 * Restores the ROS2 topic name from a preview MP4 filename.
 *
 * The backend names each video `observation.images.<topic>.mp4` with the
 * topic's "/" replaced by "-" (see `derive_video_name` in
 * backend/app/features/media/models.py); "-" cannot appear in a ROS2 topic,
 * so reversing it is exact.
 * "observation.images.camera-color-image_raw-compressed.mp4" → "/camera/color/image_raw/compressed"
 */
export function videoTopicLabel(filename: string): string {
  const name = filename.replace(/^observation\.images\./, "").replace(/\.mp4$/, "");
  return `/${name.replace(/-/g, "/")}`;
}
