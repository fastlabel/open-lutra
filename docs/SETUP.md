# Setup Guide

> Walks through everything from setting up a development environment to deploying to production.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Development Environment Setup](#development-environment-setup)
- [Local Development Tools](#local-development-tools)
- [Production Deployment](#production-deployment)
- [Configuration](#configuration)
- [Upload (optional)](#upload-optional)
- [Simulator](#simulator)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

| Tool | Version | Purpose |
|--------|-----------|------|
| Docker | 20.10+ | Container runtime |
| Docker Compose | 2.0+ | Multi-container management |
| Node.js | 22.x | Frontend development (local lint/type-check) |
| pnpm | 11.x | Frontend package manager (also available via Node.js Corepack) |
| Python | 3.11+ | Backend development (local lint) |
| uv | latest | Python package manager |

> **A local ROS2 install is not required.** ROS2 runs inside a Docker container, so there is no need to install ROS2 on a developer's machine.

---

## Development Environment Setup

### 1. Clone the Repository

```bash
git clone <repository-url>
cd open-lutra
```

> If your robot publishes topics that use **custom ROS2 message types** (vendor-specific or user-defined), see [`examples/custom_ros2_messages/`](../examples/custom_ros2_messages/) for how to build those message packages into the container before bringing the stack up.

### 2. Initial Setup

```bash
make setup
```

This command performs the following:
- Installs Python dependencies (`uv sync --extra dev`)
- Installs frontend dependencies (`cd frontend && pnpm install`)
- Copies `.env.example` → `.env` (only if it does not already exist)

### 3. Recording Configuration

Use `RECORDING_CONFIG` in `.env` to select a recording configuration. The topic list, expected Hz, validators, and ROS_DOMAIN_ID are managed in YAML:

```bash
# .env
RECORDING_CONFIG=config/simulator.yaml   # Required: use the bundled simulator config
# RECORDING_CONFIG=config/myrobot.yaml   # Your own physical-robot config (copy simulator.yaml as a template)
```

### 4. Start the Development Environment

```bash
make up
```

Three containers start:

| Service | URL | Description |
|----------|-----|------|
| Frontend | http://localhost:5173 | Vite dev server (HMR enabled) |
| Backend | http://localhost:8000 | FastAPI (auto-reload enabled) |
| Simulator | - | Robot dummy data publisher |

### 5. Verify

Open http://localhost:5173 in a browser. If the simulator's topics appear in the left panel, everything is working.

### Frequently Used Commands

| Command | Description |
|----------|------|
| `make up` | Start the development environment (with simulator) |
| `make down` | Stop |
| `make restart` | Restart (down + up) |
| `make logs` | Tail logs in real time |
| `make ps` | Show container status |
| `make build` | Rebuild Docker images |
| `make stream` | Inspect the SSE stream (for debugging) |

---

## Local Development Tools

Tools that run on your local machine (not inside Docker):

### Lint

```bash
make lint
```

Runs the following in order:
1. `ruff check` - Python linter
2. `mypy` - Python type checking
3. `tsc --noEmit` - TypeScript type checking
4. `biome check` - TypeScript lint + format check

### Tests

```bash
make test
```

Runs pytest inside the Docker container (rclpy is required).

### Formatting

```bash
make format
```

Runs the Python (ruff) and TypeScript (biome) code formatters.

---

## Production Deployment

### Prerequisites (Production)

- Ubuntu 22.04 (an OS supported by ROS2 Humble)
- A real robot must be connected to the same network
- `ros_domain_id` in `config/*.yaml` must match the robot's setting

### Deployment Steps

```bash
# 1. Configure environment variables
cp .env.example .env
# Edit .env: set RECORDING_CONFIG to your physical-robot config (copy config/simulator.yaml as a template)

# 2. (Optional) Add custom ROS2 message packages
# If your robot publishes topics that use custom message types, follow
# examples/custom_ros2_messages/ to build those packages into the image.

# 3. Build Docker images
make build

# 4. Start the production environment
make prod-up
```

In production, the environment starts with `network_mode: host`. This is required so that ROS2's DDS (peer-to-peer communication) can discover the real robot.

### Production Commands

| Command | Description |
|----------|------|
| `make prod-up` | Start the production environment (host network) |
| `make prod-down` | Stop the production environment |
| `make prod-logs` | Show production logs |

---

## Configuration

### Recording Configuration (YAML)

Recording-specific configuration is managed in YAML files under the `config/` directory. Use `RECORDING_CONFIG` in `.env` to choose the file.

```yaml
# config/myrobot.yaml (example — copy config/simulator.yaml and adjust)
robot_name: Robot
ros_domain_id: 124
recording_discovery_timeout: 10
recording_start_delay_sec: 2.0   # Wait for the camera publish ramp-up (physical robot)
monitor_qos_depth: 30
stamp_quality: true   # Physical robot: judge quality based on header.stamp

default_topics:
  - /right_arm_depth_cam/color/image_raw/compressed
  - /mcap/master_arm_right

expected_hz_patterns:
  - pattern: "**/compressed"
    hz: 30
  - pattern: "/mcap/*"
    hz: 200
```

| Preset | File | Use Case |
|---|---|---|
| Simulator (default) | `config/simulator.yaml` | 4 cameras (30Hz) + 2 joint-data channels (100Hz); also serves as a template for physical-robot configs |

#### YAML Configuration Items

| Item | Description |
|---|---|
| `robot_name` | Robot name displayed in the UI status bar |
| `ros_domain_id` | ROS2 domain ID. Must match the robot's setting |
| `recording_discovery_timeout` | Maximum number of seconds to wait for DDS discovery when starting a recording (0 disables it) |
| `recording_start_delay_sec` | Additional seconds to wait after DDS discovery completes before sending SPACE to actually start recording. RealSense cameras and the like have a roughly one-second lag between subscribe confirmation and the first frame, so waiting for the ramp-up before starting eliminates the empty gap at the beginning of recordings (for real robots; default 0) |
| `monitor_qos_depth` | QoS queue depth for topic-monitoring subscriptions |
| `default_topics` | List of topic names recorded by default |
| `expected_hz_patterns` | Expected Hz for quality monitoring. Specified by pattern (`fnmatch`); the first match wins |
| `stamp_quality` | Whether the live-quality `loss_rate` is computed from `header.stamp` (for real robots, `true`) or by count (for the simulator, `false`). See [DDS Communication and Gaps](domain/dds_gap.md) for details |
| `metadata_fields` | Optional pre-registered metadata fields (operator ID, target object, …) offered before recording. See [Pre-registered metadata](domain/metadata.md) for the field schema |

`default_topics` can also be toggled individually in the UI's left panel. Hz is also automatically applied to dynamically discovered topics via `expected_hz_patterns`.

#### Fixed vs Dynamically Learned Baseline Hz

If you specify `hz` in `expected_hz_patterns`, the baseline is **fixed**; if you omit it, it is **dynamically learned** (calculated automatically from message intervals after subscribing):

```yaml
expected_hz_patterns:
  - pattern: "**/compressed"
    hz: 30                    # Fixed: monitor quality against a 30Hz baseline
  - pattern: "/sensor/*"      # Dynamically learned: determines the baseline Hz from measured values
```

The UI shows an `auto` label on dynamically learned baselines (for example, `100/100Hz auto`). Hz values discovered through dynamic learning can be written back into YAML as fixed values for stable monitoring.

### Environment Variables (.env)

The `.env` file holds only infrastructure and connection settings:

| Variable | Default | Description |
|------|-----------|------|
| `RECORDING_CONFIG` | _required_ | Path to the recording configuration YAML (startup fails if unset) |
| `OUTPUT_DIR` | _required_ | Directory where recording data is stored (startup fails if unset) |
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `8000` | Server port number |
| `DEBUG` | `false` | Debug mode (affects log level) |
| `GAP_THRESHOLD_SEC` | `3.0` | Threshold (in seconds) for considering a topic gap |
| `MONITOR_BUFFER_SIZE` | `600` | Number of recent messages kept for topic monitoring |
| `MAX_LOG_ENTRIES` | `500` | Maximum number of entries kept in the log panel |

> The frame rate of MP4 files generated by the Preview panel on the recording detail page is fixed at 30fps (`backend/app/features/media/video_generator.py:VIDEO_FPS`). It is persisted in the recording directory and is not regenerated when re-opened, which is why it is not exposed as an environment variable.

---

## Upload (optional)

Recordings can be shipped from the recording machine to an external storage backend with one click on the recording detail page. Two backends are available today: **Amazon S3** (or any S3-compatible endpoint) and a **local-network filesystem** (an NFS / SMB share mounted on the host).

`UPLOAD_DESTINATION` in `.env` selects which backend is active per machine — `s3` or `local`. When unset, the upload feature is disabled: `/api/upload/start` refuses to enqueue and the UI hides its affordances.

> This section covers only operator configuration — what to set in `.env` and how to mount a share. For how uploads work end to end (lifecycle, the destination abstraction, key-template rules, and failure modes), see [Upload to a destination](domain/upload.md).

### Amazon S3

Set `UPLOAD_DESTINATION=s3` and configure the bucket and key template. Authenticate either with env-var keys or a named profile (exactly one of the two paths).

| Variable | Required | Description |
|------|------|------|
| `UPLOAD_DESTINATION` | yes | Set to `s3`. Selects the active destination; when unset the upload feature is disabled |
| `S3_BUCKET` | yes | Destination bucket name |
| `S3_KEY_TEMPLATE` | yes | Object-key template. Supports `{recording_name}` and `{yyyymmddhhmmss}` placeholders |
| `AWS_REGION` | yes\* | AWS region |
| `AWS_ACCESS_KEY_ID` | \*\* | Access key (env-var auth) |
| `AWS_SECRET_ACCESS_KEY` | \*\* | Secret key (env-var auth) |
| `AWS_SESSION_TOKEN` | no | Session token for STS temporary credentials (env-var auth) |
| `AWS_PROFILE` | \*\* | Named profile (profile auth; mutually exclusive with the access-key pair) |
| `AWS_ENDPOINT_URL` | no | Custom S3 endpoint (MinIO / R2 / LocalStack) |
| `S3_MULTIPART_THRESHOLD_MB` | no | `boto3` TransferConfig override (default 8 MB) |
| `S3_MULTIPART_CHUNKSIZE_MB` | no | `boto3` TransferConfig override (default 8 MB) |
| `S3_MAX_CONCURRENCY` | no | `boto3` TransferConfig override (default 10) |

\* `AWS_REGION` may be resolved from the profile when using `AWS_PROFILE`.
\*\* Exactly one of the two auth paths (env-var keys **or** profile) must be configured. With env-var auth, add `AWS_SESSION_TOKEN` when the access key is a temporary STS credential.

Example `.env` snippet (env-var auth):

```env
UPLOAD_DESTINATION=s3
S3_BUCKET=lutra-recordings
S3_KEY_TEMPLATE=lutra-recordings/operation-files/{yyyymmddhhmmss}/{recording_name}.zip
AWS_REGION=ap-northeast-1
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
# AWS_SESSION_TOKEN=...   # only for temporary STS credentials
```

#### Local testing with MinIO

A `pgsty/minio` container is wired into `docker-compose.yml` behind the `s3` profile so the upload feature can be tested without touching real AWS. A one-shot `minio-init` container auto-creates the bucket on startup.

```bash
make minio-up    # Start MinIO + create the bucket defined by S3_BUCKET
make minio-down  # Stop MinIO
```

| Endpoint | URL | Default credentials |
|---|---|---|
| S3 API | http://localhost:9000 | `minioadmin` / `minioadmin` |
| Web console | http://localhost:9001 | `minioadmin` / `minioadmin` |

`.env` snippet to point the backend at the local MinIO (used alongside `make up`):

```env
UPLOAD_DESTINATION=s3
S3_BUCKET=lutra-recordings
S3_KEY_TEMPLATE=lutra-recordings/operation-files/{yyyymmddhhmmss}/{recording_name}.zip
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=minioadmin
AWS_SECRET_ACCESS_KEY=minioadmin
AWS_ENDPOINT_URL=http://minio:9000
```

The backend reaches MinIO via the compose-internal hostname `minio:9000`. From the host (browser, `aws s3` CLI), use `http://localhost:9000` instead. The bucket name and the root credentials are configurable via `S3_BUCKET`, `MINIO_ROOT_USER`, and `MINIO_ROOT_PASSWORD` in `.env`.

After editing `.env`, restart the backend so the new values are picked up — `env_file` is read on container start, so plain `make up` against an already-running stack will keep the old values:

```bash
make restart
```

### Local-network filesystem

Set `UPLOAD_DESTINATION=local` to copy recordings to a directory on the backend container's filesystem instead of shipping them to S3 — typically an NFS or SMB share that the operator has mounted on the host and bind-mounted into the container.

| Variable | Required | Description |
|------|------|------|
| `UPLOAD_DESTINATION` | yes | Set to `local`. Selects the active destination; when unset the upload feature is disabled |
| `LOCAL_UPLOAD_DIR` | yes | Absolute path inside the container where the share is mounted (e.g. `/mnt/recordings`) |
| `LOCAL_UPLOAD_PATH_TEMPLATE` | yes | Relative path template under `LOCAL_UPLOAD_DIR`. Supports the same `{recording_name}` and `{yyyymmddhhmmss}` placeholders as `S3_KEY_TEMPLATE` |

Example `.env` snippet:

```env
UPLOAD_DESTINATION=local
LOCAL_UPLOAD_DIR=/mnt/recordings
LOCAL_UPLOAD_PATH_TEMPLATE=operation-files/{yyyymmddhhmmss}/{recording_name}.zip
```

#### Mounting the share into the container

The backend container does not run NFS / SMB clients itself — it just reads and writes a directory. Mount the share on the **host**, then bind-mount the host path into the container at `LOCAL_UPLOAD_DIR`.

Example host-side NFS mount (`/etc/fstab`):

```fstab
nfs-server.local:/exports/recordings  /mnt/recordings  nfs  defaults,_netdev  0  0
```

Bind-mount into the backend container via `docker-compose.yml`:

```yaml
services:
  backend:
    volumes:
      - /mnt/recordings:/mnt/recordings
```

Match `LOCAL_UPLOAD_DIR` in `.env` to the container-side path of the bind-mount.

> **Permissions** — NFS / SMB servers usually export with specific uid/gid. The backend container runs as a non-root user; ensure the share is writable by that user (NFS: `anonuid` / `anongid` or matching uid mapping; SMB: `uid=` / `gid=` mount options). A mount that is present but unresponsive (or unwritable) at runtime surfaces as a failed upload rather than a startup error — see [Upload to a destination — Failure modes](domain/upload.md#failure-modes).

---

## Simulator

In the development environment, the simulator publishes dummy data in place of a real robot.

### Published Topics

| Topic | Type | Frequency |
|---|---|---|
| `/robot_slave/states` | JointState | 100 Hz |
| `/robot_master/cmd` | JointState | 100 Hz |
| `/right_arm_depth_cam/.../compressed` | CompressedImage | 30 Hz |
| `/right_arm_depth_cam_2/.../compressed` | CompressedImage | 30 Hz |
| `/left_arm_depth_cam/.../compressed` | CompressedImage | 30 Hz |
| `/left_arm_depth_cam_2/.../compressed` | CompressedImage | 30 Hz |

### How It Works

- `simulator/robot_simulator.py` runs as an rclpy node
- Publishes dummy data with the same topic names, message types, and frequencies as the real robot
- JointState: joint angle values from a sine-wave motion
- CompressedImage: replays sample JPEG frames extracted from real recordings in a loop

### Fault Simulation Modes

The `SIM_MODE` environment variable reproduces abnormal topic-publication patterns. Use it to verify the real-time monitoring UI and to debug.

| Mode | Behavior |
|---|---|
| `normal` | Stable publishing (default) |
| `unstable` | Random drops on some topics |
| `topic_stop` | Stops publishing after N seconds |
| `camera_empty` | Mixes empty frames (0 bytes) into the camera topics |
| `burst` | Periodic gaps + DDS-burst-like continuous publishing |
| `mixed` | A combination of the above (closest to the real robot) |

```bash
# Restart the simulator with a specific mode
SIM_MODE=unstable make restart-sim

# Parameters can also be specified
SIM_MODE=topic_stop SIM_STOP_AFTER_SEC=10 make restart-sim
```

For the full list of environment variables, see [simulator/README.md](simulator/README.md).

### Starting/Stopping the Simulator

The simulator is started automatically by `make up` (via the `sim` profile in `docker-compose.yml`).

```bash
make restart-sim              # Restart only the simulator
docker compose up -d          # Start without the simulator (omit --profile sim)
```

---

## Troubleshooting

### Topics Are Not Shown

1. **Check `ROS_DOMAIN_ID`**: ensure `ros_domain_id` in `config/*.yaml` matches the robot's setting
2. **Check the network**: production requires `network_mode: host`
3. **CycloneDDS configuration**: ensure the correct network interface is specified in `cyclonedds.xml`

### Docker Build Fails

```bash
# Rebuild without using the cache
docker compose build --no-cache
```

### Recording Data Is Not Saved

1. Check that the `OUTPUT_DIR` path is correct
2. Check that the Docker volume mount is correct (see the `volumes` section in `docker-compose.yml`)
3. Check that the directory inside the container is writable

### Frontend Changes Are Not Reflected

```bash
# Clear the Vite cache and restart
make restart
```

### Python Dependency Errors

```bash
# Rebuild the Docker image
make build
make restart
```
