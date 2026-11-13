# OpenLUTRA - Backend
# ROS2 (Humble / Jazzy) + FastAPI

# ROS 2 distro of the image: humble (Python 3.10) or jazzy (Python 3.12).
ARG ROS_DISTRO=humble
FROM ros:${ROS_DISTRO}-ros-base

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip \
    python3-venv \
    curl \
    ffmpeg \
    ros-${ROS_DISTRO}-rosbag2-storage-mcap \
    python3-colcon-common-extensions \
    ros-${ROS_DISTRO}-rosidl-default-generators \
    && rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# To subscribe to topics that use custom ROS2 message types (vendor-specific or
# user-defined), build the message package(s) into /ros2_ws here. The entrypoint
# sources /ros2_ws/install/setup.bash when present. See
# examples/custom_ros2_messages/ for a working pattern.

WORKDIR /app

# Copy dependency files first for better caching
COPY backend/pyproject.toml backend/uv.lock* ./

# --system-site-packages exposes the system ROS 2 Python packages to the venv
RUN uv venv --system-site-packages && \
    uv sync --no-dev --frozen 2>/dev/null || uv sync --no-dev

COPY backend/app/ ./app/
COPY config/ ./config/
COPY .env.example .env

RUN mkdir -p /data/output

EXPOSE 8000

ENV OUTPUT_DIR=/data/output
ENV HOST=0.0.0.0
ENV PORT=8000

COPY <<'EOF' /entrypoint.sh
#!/bin/bash
set -e
source /opt/ros/${ROS_DISTRO}/setup.bash
# Source the custom-message workspace when it exists (see examples/custom_ros2_messages/)
[ -f /ros2_ws/install/setup.bash ] && source /ros2_ws/install/setup.bash
if [ -f "${RECORDING_CONFIG:-}" ]; then
  export ROS_DOMAIN_ID=$(python3 -c "import yaml; print(yaml.safe_load(open('${RECORDING_CONFIG}')).get('ros_domain_id', 0))")
fi
# Hand over to `command:` when one is given, so compose can add flags such as
# --reload. Everything above is the ROS 2 environment the command needs.
if [ "$#" -gt 0 ]; then
  exec "$@"
fi
# --locked reports a pyproject.toml / uv.lock mismatch as such instead of
# re-resolving, which --offline could not complete anyway.
exec uv run --locked --offline uvicorn app.main:app --host ${HOST:-0.0.0.0} --port ${PORT:-8000}
EOF

RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
