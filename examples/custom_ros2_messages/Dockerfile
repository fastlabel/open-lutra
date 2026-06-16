# OpenLUTRA - Backend (sample with custom ROS2 message types built in)
#
# This is a reference snapshot of the project root Dockerfile with a custom
# message package added. As shipped, it builds the bundled `example_robot_msgs`
# package from this directory so the image is buildable as-is. For your own
# project, replace `examples/custom_ros2_messages/example_robot_msgs` /
# `example_robot_msgs` with the path and name of your package.
#
# See README.md in this directory for the full walkthrough.

FROM ros:humble-ros-base-jammy

# Avoid interactive prompts
ENV DEBIAN_FRONTEND=noninteractive

# Install Python and dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip \
    python3-venv \
    curl \
    ffmpeg \
    ros-humble-rosbag2-storage-mcap \
    python3-colcon-common-extensions \
    ros-humble-rosidl-default-generators \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency management
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# --- Custom ROS2 message types ---
# Builds the bundled `example_robot_msgs` package from this directory. Replace
# the COPY source path and the `--packages-select` argument with your package
# name. List multiple packages space-separated after `--packages-select` if you
# have more than one.
COPY examples/custom_ros2_messages/example_robot_msgs/ /ros2_ws/src/example_robot_msgs/
RUN /bin/bash -c "\
    source /opt/ros/humble/setup.bash && \
    cd /ros2_ws && \
    colcon build --packages-select example_robot_msgs --cmake-args -DCMAKE_BUILD_TYPE=Release \
    "

# Set working directory
WORKDIR /app

# Copy dependency files first for better caching
COPY backend/pyproject.toml backend/uv.lock* ./

# Install dependencies (allow access to system ROS2 Python packages)
RUN uv venv --system-site-packages && \
    uv sync --no-dev --frozen 2>/dev/null || uv sync --no-dev

# Copy application code and config
COPY backend/app/ ./app/
COPY config/ ./config/
COPY .env.example .env

# Create output directory
RUN mkdir -p /data/output

# Expose port
EXPOSE 8000

# Set environment variables
ENV OUTPUT_DIR=/data/output
ENV HOST=0.0.0.0
ENV PORT=8000

# Entrypoint script: read ROS_DOMAIN_ID from RECORDING_CONFIG and launch ROS2
COPY <<'EOF' /entrypoint.sh
#!/bin/bash
set -e
source /opt/ros/humble/setup.bash
# The custom-message workspace is always present in this sample image.
source /ros2_ws/install/setup.bash
if [ -f "${RECORDING_CONFIG:-}" ]; then
  export ROS_DOMAIN_ID=$(python3 -c "import yaml; print(yaml.safe_load(open('${RECORDING_CONFIG}')).get('ros_domain_id', 0))")
fi
exec uv run --offline uvicorn app.main:app --host ${HOST:-0.0.0.0} --port ${PORT:-8000}
EOF

RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
