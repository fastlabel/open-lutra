# Robot Simulator

ROS2 topic simulator for development and testing. Lets you verify Recorder UI behavior without real hardware.

## Published topics

| Topic | Message type | Frequency |
|---------|-------------|--------|
| `/sim/slave_arm_left` | `sensor_msgs/JointState` | 100Hz |
| `/sim/slave_arm_left/gripper` | `std_msgs/Float64` | 100Hz |
| `/sim/slave_arm_left/pose` | `geometry_msgs/Point` | 100Hz |
| `/sim/master_arm_left` | `sensor_msgs/JointState` | 100Hz |
| `/sim/master_arm_left/hand` | `std_msgs/Float64` | 100Hz |
| `/chest_depth_cam/color/image_raw/compressed` | `sensor_msgs/CompressedImage` | 30Hz |
| `/head_depth_cam/color/image_raw/compressed` | `sensor_msgs/CompressedImage` | 30Hz |
| `/left_arm_depth_cam/color/image_raw/compressed` | `sensor_msgs/CompressedImage` | 30Hz |

## Behavior

- **Joint data**: Replays the recorded trajectory in `joint_replay.json` (left arm, 5 s loop) by indexing into it from a 100Hz timer based on elapsed time, looping at the end. Slave joint positions are in radians; master positions are encoder counts. Gripper/hand are scalar floats (0.0 = closed). End-effector Cartesian position (pose) was solved by forward kinematics at record time.
- **Camera data**: Loops per-camera JPEGs under `simulator/frames/<cam>/` (150 frames each / 5 seconds) at 30Hz for three cameras: `chest`, `head`, and `left_arm`.

## How to run

```bash
# Via Docker Compose (recommended)
make restart-sim  # started automatically with --profile sim

# Start with a specific fault mode
SIM_MODE=unstable make restart-sim

# Standalone (inside a ROS2 environment)
source /opt/ros/humble/setup.bash
python3 robot_simulator.py
```

## Fault simulation modes

Switch modes via the `SIM_MODE` environment variable. Set it in `.env` or pass it at startup.

| Mode | Behavior |
|---|---|
| `normal` | Stable publishing (default) |
| `unstable` | Random drops on some topics (reproduces unstable hardware publishing) |
| `topic_stop` | Completely stops publishing the specified topic after N seconds (reproduces node-connected but no-data state) |
| `camera_empty` | Camera topics keep publishing but some frames are empty (0 bytes) |
| `burst` | Periodic gap + DDS-burst-style consecutive sends |
| `mixed` | Combines unstable + topic_stop + camera_empty (closest to real hardware) |

### Environment variables

| Variable | Default | Applies to | Description |
|---|---|---|---|
| `SIM_MODE` | `normal` | all | Simulation mode |
| `SIM_DROP_RATE` | `0.1` | unstable, mixed | Message drop rate (0.0-1.0) |
| `SIM_UNSTABLE_TOPICS` | `all` | unstable, mixed | Topics to drop (`all` for every topic, or a comma-separated list) |
| `SIM_STOP_AFTER_SEC` | `15` | topic_stop, mixed | Seconds before publishing stops |
| `SIM_STOP_TOPICS` | `/sim/slave_arm_left,/sim/master_arm_left` | topic_stop, mixed | Topics to stop (comma-separated) |
| `SIM_EMPTY_CAMERA_INDICES` | `0` | camera_empty, mixed | Cameras to send empty frames for (0-based indices, comma-separated) |
| `SIM_EMPTY_FRAME_RATE` | `0.3` | camera_empty, mixed | Empty-frame rate (0.0-1.0) |
| `SIM_BURST_INTERVAL_SEC` | `10` | burst | Interval between bursts (seconds) |
| `SIM_BURST_GAP_SEC` | `2.0` | burst | Gap (publishing-stopped) length (seconds) |
| `SIM_BURST_COUNT` | `50` | burst | Number of messages sent in a single burst |

### Examples

```bash
# Drop the slave topic with 20% probability
SIM_MODE=unstable SIM_DROP_RATE=0.2 make restart-sim

# Stop slave and master after 10 seconds
SIM_MODE=topic_stop SIM_STOP_AFTER_SEC=10 make restart-sim

# Send empty frames for 50% of chest camera messages
SIM_MODE=camera_empty SIM_EMPTY_FRAME_RATE=0.5 make restart-sim

# Every 5 seconds: 1s gap → burst of 30 messages
SIM_MODE=burst SIM_BURST_INTERVAL_SEC=5 SIM_BURST_GAP_SEC=1.0 SIM_BURST_COUNT=30 make restart-sim
```

## File layout

| File | Responsibility |
|---|---|
| `robot_simulator.py` | ROS2 node itself (Publisher + Timer) |
| `config.py` | Reads environment variables and defines defaults |
| `fault_modes.py` | Fault-injection logic (ROS2-independent) |
| `frames/<cam>/` | Per-camera sample JPEGs for `chest`, `head`, and `left_arm` (extracted from a real MCAP recording at 30Hz, re-compressed with Pillow). Recorded in-house at FastLabel and bundled here under the project license. |
| `joint_replay.json` | Left-arm trajectory: slave joint positions (radians), gripper scalar, end-effector Cartesian pose, master joint positions (encoder counts), hand scalar. 500 samples at 100Hz (5 s). |

## References

- [Writing a simple publisher and subscriber (Python) - ROS 2 Humble](https://docs.ros.org/en/humble/Tutorials/Beginner-Client-Libraries/Writing-A-Simple-Py-Publisher-And-Subscriber.html) - Basic patterns for `Node`, `create_publisher`, `create_timer`
- [rclpy API Reference (Humble)](https://docs.ros.org/en/ros2_packages/humble/api/rclpy/rclpy.html) - Full API spec for the rclpy Node class
- [sensor_msgs (Humble)](https://docs.ros.org/en/ros2_packages/humble/api/sensor_msgs/) - Message definitions for `JointState`, `CompressedImage`
- [About Quality of Service Settings - ROS 2](https://docs.ros.org/en/humble/Concepts/Intermediate/About-Quality-of-Service-Settings.html) - Design guidance for QoS profiles (Reliability, History, etc.)
- [common_interfaces/sensor_msgs (GitHub)](https://github.com/ros2/common_interfaces/tree/humble/sensor_msgs) - Source for sensor_msgs
