# Robot Simulator - ROS2 Dummy Data Publisher
# Lightweight container that publishes simulated robot data

FROM ros:humble-ros-base-jammy

ENV DEBIAN_FRONTEND=noninteractive

# Install Python ROS2 dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /simulator

# Copy simulator scripts and sample data (camera frames + joint replay)
COPY *.py .
COPY frames/ ./frames/
COPY joint_replay.json .

# Entrypoint: read ROS_DOMAIN_ID from RECORDING_CONFIG and start ROS2
COPY <<'EOF' /entrypoint.sh
#!/bin/bash
set -e
source /opt/ros/humble/setup.bash
if [ -f "${RECORDING_CONFIG:-}" ]; then
  export ROS_DOMAIN_ID=$(python3 -c "import yaml; print(yaml.safe_load(open('${RECORDING_CONFIG}')).get('ros_domain_id', 0))")
fi
exec python3 /simulator/robot_simulator.py
EOF

RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
