# Custom ROS2 Message Types

This example shows how to record topics that use **custom ROS2 message types** (vendor-specific message packages or user-defined `.msg` files) with OpenLUTRA.

> Licensed under [BSD Zero Clause License (0BSD)](../LICENSE). Copy and adapt freely.

## Files in this directory

| File / directory | Purpose |
|---|---|
| [`README.md`](./README.md) | This walkthrough. |
| [`Dockerfile`](./Dockerfile) | Sample Docker image that bundles a custom message package on top of OpenLUTRA's base image. Buildable as-is. |
| [`example_robot_msgs/`](./example_robot_msgs/) | Minimal ROS2 message package illustrating the two nested-`JointState` patterns OpenLUTRA detects. |

## Why this is needed

OpenLUTRA's runtime detection of images and joint states is **structure-based** — it inspects the decoded message for `format` + `data` fields (image) or `position` / nested `joint_state.position` (joint state). It does **not** depend on the ROS2 type name.

However, before runtime detection can run, ROS2 must be able to **deserialize** the message. That requires the message package's generated Python bindings to be on `PYTHONPATH` inside the container. For built-in types (`sensor_msgs/msg/Image`, `sensor_msgs/msg/JointState`, etc.) this is already provided by the base ROS image. For custom types you have to build the package yourself.

## How OpenLUTRA picks up custom messages

The base container entrypoint runs:

```bash
source /opt/ros/humble/setup.bash
[ -f /ros2_ws/install/setup.bash ] && source /ros2_ws/install/setup.bash
```

If you build any ROS2 packages into `/ros2_ws/install/` at image-build time, the entrypoint automatically picks them up. That's the integration point.

## The bundled `example_robot_msgs` package

```
example_robot_msgs/
├── package.xml         # ROS2 ament/CMake manifest, declares rosidl_default_generators
├── CMakeLists.txt      # Generates Python/C++ bindings from the two .msg files
└── msg/
    ├── ArmState.msg    # Nested pattern:    JointState wrapped in a larger message
    └── BodyState.msg   # Composite pattern: two JointState groups bundled on one topic
```

`ArmState.msg`:

```
std_msgs/Header header
sensor_msgs/JointState joint_state
```

OpenLUTRA reads this via `extract_joint_positions()` in `backend/app/infra/mcap/messages.py`: when `decoded.position` is absent, it walks `decoded.joint_state.position`.

`BodyState.msg`:

```
std_msgs/Header header
sensor_msgs/JointState joint_state
sensor_msgs/JointState neck_joint_state
```

OpenLUTRA concatenates `joint_state.position` and `neck_joint_state.position` in declaration order — useful when a single topic publishes coordinated joint groups (e.g. arm + neck).

You do not need to register any code in OpenLUTRA — as long as the structure exposes `position` (directly or under `joint_state`), it just works.

## Try it (uses the bundled package as-is)

The sample [`Dockerfile`](./Dockerfile) builds `example_robot_msgs` into the image. From the project root:

```bash
docker build -f examples/custom_ros2_messages/Dockerfile -t open-lutra:custom-msgs .
```

Once the image is built, OpenLUTRA inside it can subscribe to topics that publish `example_robot_msgs/msg/ArmState` or `example_robot_msgs/msg/BodyState`.

## Adapt it for your own message package

1. **Drop your package next to OpenLUTRA.** It must be a valid ROS2 ament/CMake package that uses `rosidl_default_generators`. The simplest path is to place it alongside `example_robot_msgs/` in this directory.

2. **Apply the two build lines** to the project root `Dockerfile` (or copy the sample Dockerfile as a starting point):

   ```dockerfile
   COPY examples/custom_ros2_messages/your_robot_msgs/ /ros2_ws/src/your_robot_msgs/
   RUN /bin/bash -c "\
       source /opt/ros/humble/setup.bash && \
       cd /ros2_ws && \
       colcon build --packages-select your_robot_msgs --cmake-args -DCMAKE_BUILD_TYPE=Release \
       "
   ```

   Replace `your_robot_msgs` with your package name. If you have multiple packages, pass them all to `--packages-select` (space-separated) and add a matching `COPY` for each.

3. **Rebuild and start:**

   ```bash
   make build
   make up
   ```

## Compatibility notes

- The sample `Dockerfile` is a snapshot of the project root `Dockerfile` plus the COPY + `colcon build` block. If the root Dockerfile diverges over time, treat this file as a reference and apply the build block to whatever the current Dockerfile looks like.
