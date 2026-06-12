"""Robot simulator for development and testing.

Publishes simulated ROS2 topics that mimic a real robot
with multiple depth cameras, allowing end-to-end testing without
physical hardware.

Published topics:
  /sim/slave_arm_left                                         (sensor_msgs/JointState)     @ 100Hz
  /sim/slave_arm_left/gripper                                 (std_msgs/Float64)           @ 100Hz
  /sim/slave_arm_left/pose                                    (geometry_msgs/Point)        @ 100Hz
  /sim/master_arm_left                                        (sensor_msgs/JointState)     @ 100Hz
  /sim/master_arm_left/hand                                   (std_msgs/Float64)           @ 100Hz
  /chest_depth_cam/color/image_raw/compressed                 (sensor_msgs/CompressedImage) @ 30Hz
  /head_depth_cam/color/image_raw/compressed                  (sensor_msgs/CompressedImage) @ 30Hz
  /left_arm_depth_cam/color/image_raw/compressed              (sensor_msgs/CompressedImage) @ 30Hz

Data sources:
  - Cameras: loops real-recording JPEGs from `simulator/frames/<cam>/`
    (chest / head / left_arm).
  - Joints: replays the recorded trajectory from `simulator/joint_replay.json`.
    Slave arm positions (radians) and master positions (encoder counts) are keyed
    by arm name. Gripper / hand are scalar float values. End-effector Cartesian
    position (pose) comes from forward-kinematics solved at record time.

Simulation modes: see config.py
"""

import bisect
import json
from pathlib import Path

import rclpy
from config import SIM_MODE
from fault_modes import FaultInjector
from geometry_msgs.msg import Point
from rclpy.node import Node
from sensor_msgs.msg import CompressedImage, JointState
from std_msgs.msg import Float64, Header

# Frame ID shared by all cameras (matches the `frame_id` from real-hardware recordings)
CAMERA_FRAME_ID = "camera_color_optical_frame"
JOINT_FRAME_ID = "base_link"

# One topic per camera directory.
CAMERA_TOPICS_BY_DIR: dict[str, str] = {
    "chest": "/chest_depth_cam/color/image_raw/compressed",
    "head": "/head_depth_cam/color/image_raw/compressed",
    "left_arm": "/left_arm_depth_cam/color/image_raw/compressed",
}

TOPIC_SLAVE_JOINT = "/sim/slave_arm_left"
TOPIC_SLAVE_GRIPPER = "/sim/slave_arm_left/gripper"
TOPIC_SLAVE_POSE = "/sim/slave_arm_left/pose"
TOPIC_MASTER_JOINT = "/sim/master_arm_left"
TOPIC_MASTER_HAND = "/sim/master_arm_left/hand"

FRAMES_DIR = Path(__file__).parent / "frames"
JOINT_REPLAY_PATH = Path(__file__).parent / "joint_replay.json"

CAMERA_HZ = 30
JOINT_HZ = 100


def _load_camera_frames() -> dict[str, list[bytes]]:
    """Load `frames/<cam>/*.jpg` for each camera directory and key by topic name."""
    frames: dict[str, list[bytes]] = {}
    for cam_dir, topic in CAMERA_TOPICS_BY_DIR.items():
        cam_path = FRAMES_DIR / cam_dir
        if not cam_path.is_dir():
            continue
        loaded = [p.read_bytes() for p in sorted(cam_path.glob("*.jpg"))]
        if loaded:
            frames[topic] = loaded
    return frames


def _load_joint_replay() -> dict | None:
    """Load joint_replay.json. Returns None if it does not exist."""
    if not JOINT_REPLAY_PATH.is_file():
        return None
    return json.loads(JOINT_REPLAY_PATH.read_text())


class RobotSimulator(Node):
    """ROS2 node that simulates robot data."""

    def __init__(self) -> None:
        super().__init__("robot_simulator")
        self.get_logger().info(f"Starting robot simulator (mode: {SIM_MODE})...")

        self._camera_frame_idx = 0
        self._joint_tick = 0  # tick count of the 100Hz timer

        # Fault injection
        self._fault = FaultInjector(
            SIM_MODE,
            log=lambda level, msg: getattr(self.get_logger(), level)(msg),
        )

        # Camera frames (per topic)
        self._camera_frames = _load_camera_frames()
        if self._camera_frames:
            counts = ", ".join(f"{t.split('/')[1]}={len(v)}" for t, v in self._camera_frames.items())
            self.get_logger().info(f"Loaded camera frames: {counts}")
        else:
            self.get_logger().warn("No camera frames found, camera topics will not be published")

        # Joint replay
        self._joint_replay = _load_joint_replay()
        if self._joint_replay is None:
            self.get_logger().warn(f"{JOINT_REPLAY_PATH.name} not found, joint topics will not be published")
        else:
            n = len(self._joint_replay["timestamps"])
            dur = self._joint_replay["timestamps"][-1]
            self.get_logger().info(f"Loaded joint replay: {n} samples over {dur:.1f}s")

        # Publishers — joint topics
        self._slave_joint_pub = self.create_publisher(JointState, TOPIC_SLAVE_JOINT, 10)
        self._slave_gripper_pub = self.create_publisher(Float64, TOPIC_SLAVE_GRIPPER, 10)
        self._slave_pose_pub = self.create_publisher(Point, TOPIC_SLAVE_POSE, 10)
        self._master_joint_pub = self.create_publisher(JointState, TOPIC_MASTER_JOINT, 10)
        self._master_hand_pub = self.create_publisher(Float64, TOPIC_MASTER_HAND, 10)

        # Publishers — camera topics
        self._camera_pubs = {topic: self.create_publisher(CompressedImage, topic, 10) for topic in self._camera_frames}

        # Timers
        if self._joint_replay is not None:
            self.create_timer(1.0 / JOINT_HZ, self._publish_joints)
        if self._camera_frames:
            self.create_timer(1.0 / CAMERA_HZ, self._publish_cameras)

        self._fault.log_config()

    def _make_header(self, frame_id: str) -> Header:
        header = Header()
        header.stamp = self.get_clock().now().to_msg()
        header.frame_id = frame_id
        return header

    def _build_joint_state(self, names: list[str], positions: list[float], *, with_velocity: bool) -> JointState:
        msg = JointState()
        msg.header = self._make_header(JOINT_FRAME_ID)
        msg.name = names
        msg.position = list(positions)
        msg.velocity = [0.0] * len(positions) if with_velocity else []
        msg.effort = [0.0] * len(positions)
        return msg

    def _joint_index_for_tick(self, tick: int) -> int:
        """100Hz tick → index in joint_replay.timestamps. Loops at the end of the trajectory."""
        timestamps: list[float] = self._joint_replay["timestamps"]  # type: ignore[index]
        duration = timestamps[-1]
        elapsed = (tick / JOINT_HZ) % duration
        idx = bisect.bisect_right(timestamps, elapsed) - 1
        return max(0, idx)

    def _publish_joints(self) -> None:
        """Publish all five joint topics following the recorded trajectory."""
        burst_state = self._fault.update_burst()
        if burst_state == "gap":
            return

        idx = self._joint_index_for_tick(self._joint_tick)
        replay = self._joint_replay  # type: ignore[index]
        slave = replay["slave_arm_left"]
        master = replay["master_arm_left"]

        if not self._fault.is_stopped(TOPIC_SLAVE_JOINT) and not self._fault.should_drop(TOPIC_SLAVE_JOINT):
            self._slave_joint_pub.publish(
                self._build_joint_state(slave["joint_names"], slave["positions"][idx], with_velocity=True)
            )

        if not self._fault.is_stopped(TOPIC_SLAVE_GRIPPER) and not self._fault.should_drop(TOPIC_SLAVE_GRIPPER):
            msg = Float64()
            msg.data = slave["gripper"][idx]
            self._slave_gripper_pub.publish(msg)

        if not self._fault.is_stopped(TOPIC_SLAVE_POSE) and not self._fault.should_drop(TOPIC_SLAVE_POSE):
            msg_p = Point()
            msg_p.x = slave["pose_x"][idx]
            msg_p.y = slave["pose_y"][idx]
            msg_p.z = slave["pose_z"][idx]
            self._slave_pose_pub.publish(msg_p)

        if not self._fault.is_stopped(TOPIC_MASTER_JOINT) and not self._fault.should_drop(TOPIC_MASTER_JOINT):
            self._master_joint_pub.publish(
                self._build_joint_state(master["joint_names"], master["positions"][idx], with_velocity=False)
            )

        if not self._fault.is_stopped(TOPIC_MASTER_HAND) and not self._fault.should_drop(TOPIC_MASTER_HAND):
            msg_h = Float64()
            msg_h.data = master["hand"][idx]
            self._master_hand_pub.publish(msg_h)

        # During burst: send extra messages to slave joint topic all at once
        if burst_state == "burst" and self._fault.burst_remaining > 0:
            n = min(self._fault.burst_remaining, 10)
            for _ in range(n):
                self._slave_joint_pub.publish(
                    self._build_joint_state(slave["joint_names"], slave["positions"][idx], with_velocity=True)
                )
            self._fault.consume_burst(n)

        self._joint_tick += 1

    def _publish_cameras(self) -> None:
        """Loop-publish each camera's corresponding frame sequence."""
        empty_idx_map = {topic: i for i, topic in enumerate(self._camera_frames)}
        for topic, frames in self._camera_frames.items():
            if self._fault.is_stopped(topic):
                continue
            if self._fault.should_drop(topic):
                continue

            jpeg_data = frames[self._camera_frame_idx % len(frames)]
            msg = CompressedImage()
            msg.header = self._make_header(CAMERA_FRAME_ID)
            msg.format = "jpeg"
            msg.data = b"" if self._fault.should_send_empty_frame(empty_idx_map[topic]) else jpeg_data
            self._camera_pubs[topic].publish(msg)

        self._camera_frame_idx += 1


def main() -> None:
    rclpy.init()
    node = RobotSimulator()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("Simulator shutting down...")
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
