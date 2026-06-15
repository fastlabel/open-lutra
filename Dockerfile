# OpenLUTRA - Backend
# ROS2 Humble + FastAPI

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

# To subscribe to topics that use custom ROS2 message types (vendor-specific or
# user-defined), build the message package(s) into /ros2_ws here. The entrypoint
# sources /ros2_ws/install/setup.bash when present. See
# examples/custom_ros2_messages/ for a working pattern.

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
# Source the custom-message workspace when it exists (see examples/custom_ros2_messages/)
[ -f /ros2_ws/install/setup.bash ] && source /ros2_ws/install/setup.bash
if [ -f "${RECORDING_CONFIG:-}" ]; then
  export ROS_DOMAIN_ID=$(python3 -c "import yaml; print(yaml.safe_load(open('${RECORDING_CONFIG}')).get('ros_domain_id', 0))")
fi
exec uv run --offline uvicorn app.main:app --host ${HOST:-0.0.0.0} --port ${PORT:-8000}
EOF

RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
