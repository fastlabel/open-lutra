# Robot Simulator - ROS2 Dummy Data Publisher
# Lightweight container that publishes simulated robot data

FROM ros:humble-ros-base-jammy

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /simulator

COPY *.py .
COPY frames/ ./frames/
COPY joint_replay.json .

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
