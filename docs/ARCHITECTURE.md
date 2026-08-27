# Architecture

> Explains the technical design of this project and the role of each component.

## Table of Contents

- [Tech Stack](TECH_STACK.md)
- [Directory Structure](STRUCTURE.md)
- [Overview](#overview)
- [Hybrid Architecture](#hybrid-architecture)
- [Backend Structure](#backend-structure)
- [Frontend Structure](#frontend-structure)
- [Data Flow](#data-flow)
- [Docker Setup](#docker-setup)
- [Output Format](#output-format)

---

## Tech Stack

→ See [TECH_STACK.md](TECH_STACK.md).

---

## Overview

```
┌─────────────────────────────────────────────────────────────┐
│                  ROS2 Network                                │
│   Robot (or simulator) publishes topics                      │
└────────────────┬────────────────────────────────────────────┘
                 │ DDS (peer-to-peer, CDR serialization)
        ┌────────┴────────────┐
        │                     │
   ┌────▼──────┐        ┌────▼───────────┐
   │subprocess │        │ rclpy Node     │
   │ros2 bag   │        │ TopicMonitor   │
   │record     │        │ (lightweight)  │
   └────┬──────┘        └────┬───────────┘
        │                    │
   Writes MCAP          Python method calls
   file                       │
        │               ┌───▼───────────┐
        │               │ FastAPI       │
        │               │ Backend       │
        │               └───┬───────────┘
        │                   │ SSE / REST API
        │               ┌───▼───────────┐
        │               │ React         │
        │               │ Frontend      │
        │               └───────────────┘
        │
   ┌────▼──────────────────┐
   │ After recording stops │
   │ mcap Python library   │
   │ runs quality analysis │
   └───────────────────────┘
```

### How DDS Communication Works

The robot (or simulator) communicates with this system over **DDS (Data Distribution Service)**.

```
Robot                                     This system
┌──────────────────┐                  ┌──────────────────┐
│ ROS2 driver      │                  │ rclpy / ros2 bag │
│                  │   UDP multicast  │                  │
│ Publisher        │ ◀───────────────▶│ Subscriber       │
│ /robot_slave/... │   DDS Discovery  │                  │
│ /camera/...      │                  │                  │
└──────────────────┘                  └──────────────────┘
```

| Item | Description |
|------|-------------|
| Protocol | DDS — brokerless peer-to-peer (this system uses Fast DDS, the ROS 2 Humble default; can interoperate with Cyclone DDS or others on the robot side via the standard RTPS protocol) |
| Discovery | Auto-discovery via UDP multicast (between nodes with the same `ROS_DOMAIN_ID`) |
| Serialization | **CDR** (Common Data Representation) — the standard DDS binary format. Protobuf is not used |
| Type definitions | `.msg` files (e.g., `sensor_msgs/msg/JointState.msg`) — equivalent to Protobuf's `.proto` |
| Storage in MCAP | The CDR-serialized byte stream is stored as-is. No deserialization is needed, so it is fast |

**Difference from Protobuf**: ROS2 uses its own type system (`.msg` → CDR). The MCAP format itself supports Protobuf and JSON, but CDR is the standard in the ROS2 ecosystem and this project also uses CDR.

---

## Hybrid Architecture

This system adopts a "hybrid architecture" that combines three different technologies.

| Function | Technology | Reason |
|----------|------------|--------|
| Recording | `subprocess` (`ros2 bag record`) | Memory isolation. Even long recordings do not pressure the Python process's memory |
| Real-time monitoring | `rclpy` (ROS2 Python) | Automatic topic discovery, frequency monitoring, and gap detection in real time |
| Quality analysis | `mcap` Python library | Analyzes the MCAP file after recording to compute accurate metrics |

### Why split them?

**Why use a subprocess for recording**: `ros2 bag record` is a C++ optimized tool that runs stably even with high-frequency, high-volume data. If Python (rclpy) received and stored every message, memory would grow and risk crashing during long recordings. Delegating to a subprocess fully isolates the recording process's memory from the application's.

**Why use rclpy for monitoring**: Real-time topic subscription requires ROS2 DDS communication. Running as an rclpy node enables automatic topic discovery (DDS discovery) and message reception. Unlike recording, however, it is designed to be lightweight — keeping only the latest 600 entries.

**Why use the mcap library for quality analysis**: Real-time data during recording is only approximate. Analyzing the MCAP file directly after recording lets us compute accurate quality metrics from every message's timestamp.

---

## Backend Structure

### Directory Structure

→ See the "Backend" section of [STRUCTURE.md](STRUCTURE.md).

### Core Services

#### 1. ROS2BagRecorder (subprocess recording)

Runs `ros2 bag record -s mcap --start-paused` as a child process.

```
FastAPI → ROS2BagRecorder.start(topics, qos_overrides)
  ├─ Creates the output_dir/{timestamp}/ folder
  ├─ Generates a QoS override YAML in tmp/ (when qos_overrides is provided)
  ├─ Creates a pty, bundling stdin/stdout/stderr into it, then subprocess.Popen
  │   ("ros2 bag record -s mcap --start-paused --qos-profile-overrides-path ... -o ... topic1 ...")
  ├─ Continuously drains pty output (prevents PIPE stalls during cleanup)
  ├─ Waits for all topics to be subscribed via DDS discovery (recording_discovery_timeout)
  ├─ Additional wait via recording_start_delay_sec (absorbs camera publish ramp-up, for real hardware)
  ├─ Sends SPACE through the pty to start recording
  └─ Retains the process reference + output_path + start_time
```

**pty-integrated I/O**: Bundling stdout/stderr into the pty makes `ros2 bag record` see a fully-fledged TTY environment. This prevents the massive log output during the cleanup phase after SIGINT from blocking writes due to a full PIPE buffer, so the MCAP writer's flush is not interrupted (eliminating frame loss at the end of recordings). See [DDS communication and gaps §6.5](domain/dds_gap.md) for details.

Graceful shutdown on stop:
1. Send SIGINT (equivalent to Ctrl+C)
2. Wait for completion with a 10-second timeout
3. Force-kill with SIGKILL on timeout
4. Stop the pty drain thread and close the pty master
5. Delete the temporary QoS override file

#### 2. TopicMonitor (rclpy real-time monitoring)

Runs as a ROS2 node in a background thread.

- **Automatic topic discovery**: Scans the ROS2 network every 5 seconds
- **QoS auto-matching**: Detects publisher QoS and auto-adjusts subscriber QoS
- **Lightweight subscription**: Keeps only the latest 600 entries per topic in a `deque(maxlen=600)`
- **Frequency monitoring**: Measured Hz from message intervals + auto-learns the reference Hz after 50 entries
- **Gap detection**: Records gaps that exceed 3× the expected interval
- **Quality metrics**: Computes `loss_rate` and `continuity_score` in real time
- **Thread safety**: All public methods are protected by a `threading.Lock`

#### 3. MCAPAnalyzer (quality analysis)

Located in `backend/app/features/analysis/`. Runs in the background via `asyncio.to_thread()` after recording stops.

- **header.stamp preferred**: Prefers the message's `header.stamp` (sensor sampling time). Falls back to `log_time` when not present (see [DDS communication and gaps](domain/dds_gap.md)). The decision logic is centralized in `resolve_timestamp_sec/ns` of `backend/app/infra/mcap/timestamp.py`
- **IQR-based gap detection**: Uses a statistical threshold (`Q3 + 1.5×IQR`) to accurately detect single-frame gaps. Records them as `LossEvent` (severity=minor/major)
- Computes per-topic quality metrics
- Saves `quality_report.json` to the recording folder (cache)
- See [Quality Analysis](domain/quality_analysis.md) for details

#### 4. TimelineAnalyzer (timeline generation)

Located in `backend/app/features/analysis/`. Provides data for the horizontal-bar heatmap and Message Ticks on the MCAP detail page's timeline.

- **Binning**: Aggregates per-topic `count` vs `expected` into time bins (bin width is adjusted dynamically based on recording length); `expected` reflects the configured `expected_hz` when set
- **Loss marking**: Each bin carries `count` / `expected` (the heatmap shades a smoothed count/expected deficit green→amber→red) plus `has_gap` / `has_minor_loss` flags and gap spans (the discrete IQR dropout overlay)
- **Message retrieval for rug plot**: Returns individual messages within a specified time range (for accurate display at high zoom). `MCAPReader.iter_messages(topics=, start_time_ns=, end_time_ns=)` in `backend/app/infra/mcap` filters by time and topic ranges using the chunk index, so even ~500MB files respond in tens to hundreds of ms
- **Clock-skew handling**: Saves the skew between `log_time` (recorder wall clock) and `header.stamp` (sensor side) as `log_time_offset_ns` in the cache, and converts the rug plot's chunk filter into the correct `log_time` range (see [DDS communication and gaps §6.6](domain/dds_gap.md))
- Caches `timeline_data.json` in the recording folder (includes `recording_start_ns` / `log_time_offset_ns`)

#### 5. MediaConverter (MP4 / Joint time-series)

Located in `backend/app/features/media/`. Generates data for the Preview panel (video + Joint Position Graph) of the recording detail page.

- **mcap_converter**: `convert_mcap()` generates per-camera MP4s from MCAP (streams writes to an ffmpeg subprocess, piping one frame at a time so memory use stays constant regardless of recording length, fixed 30fps). This is the actual `GenerateMediaJob`
- **video_generator**: Enumerates already-generated MP4 files (GET /api/media/video) and defines the fixed FPS constant
- **joint_reader**: Reads + caches Joint time-series (for the Joint Position Graph). Auto-detects whether `decoded.position` exists or is nested (`decoded.joint_state.position`), supporting custom message types (including composite types that also expose `neck_joint_state`)
- **Decimation support**: `decimation=20` or so is sufficient for previews (200Hz × 50s = 10,000 → 500 points)
- **Topic classification**: Uses domain types like `TopicRole` / `JointStateMapping` to identify observation/action (`_slave_` → observation, `_master_` → action)

#### 6. Shared MCAP I/O Layer (`backend/app/infra/mcap/`)

Shared layer through which analysis / media read MCAPs. Hides the initialization and decoding of the `mcap` / `mcap_ros2` libraries.

- **`MCAPReader` (context manager)**: Standardizes `make_reader` + `DecoderFactory`. Provides `iter_messages(topics=, start_time_ns=, end_time_ns=)` / `get_channels()` / `get_time_range_ns()`
- **`timestamp.resolve_timestamp_sec/ns`**: Timestamp normalization that prefers `header.stamp` (shared logic across all consumers)
- **`messages.is_image_message / extract_joint_positions / extract_joint_names`**: Structure-based detection that does not depend on ROS2 type names (supports custom message types with nested `joint_state` and composite types)

#### 7. JobQueue (background job execution platform)

Implemented in `backend/app/features/jobs/`. Runs heavy work such as MCAP conversion and quality analysis sequentially.

```
JobQueue (asyncio.Queue + single worker)
  ├─ media     : MCAP → MP4 (all cameras) + joint_data.json
  ├─ timeline  : MCAP → timeline_data.json
  ├─ quality   : MCAP → quality_report.json
  ├─ validation: QualityReport → validation_result.json
  └─ upload    : recording folder → zip → ship to UploadDestination
```

- **Single worker**: At most one job runs concurrently. Running multiple CPU-bound MCAP conversions/analyses at once would actually slow things down
- **Duplicate prevention**: The same folder + same type is deduplicated
- **Progress over SSE**: `/api/jobs/stream` broadcasts `queue_snapshot` / `job_added` / `job_started` / `job_progress` / `job_completed` / `job_failed` events
- **Log-only on failure**: Does not retry; moves on to the next job. Failed jobs are shown in the Jobs panel
- **Auto-chain**: When a recording stops, both a quality job and a validation job are enqueued. The single-worker FIFO guarantees validation runs *after* the quality report it depends on exists

#### 8. Validation (per-recording rule checks)

Implemented in `backend/app/features/validation/`. Runs a fixed set of builtin checks plus any user-supplied custom checks against a `ValidationContext`, persisting the outcome to `validation_result.json`.

```
ValidationRunner.run(report, recording_dir, mcap_path, recording_meta)
  ├─ Build ValidationContext (report + paths + meta)
  ├─ builtin validators (from active_set.py)
  │     ├─ required_topics_present
  │     └─ total_duration_sec
  ├─ custom validators (from registry; loaded on startup)
  └─► ValidationReport (overall_status + per-validator items)
```

- **Context-driven**: Validators receive a `ValidationContext` carrying the `QualityReport`, the recording folder, the MCAP file path, and the parsed `recording_meta.json`. Light validators read only `ctx.report`; validators that need raw frames open `ctx.mcap_path` with `MCAPReader` from `app.infra.mcap`
- **Builtin vs. custom**: Builtin validators ship in `builtins/` and accept constructor params via `active_set.py`. Custom validators live in `custom/`, are decorated with `@register_validator`, and are auto-discovered at startup via `pkgutil.iter_modules`
- **Exception isolation**: When a validator raises, the runner converts the failure into `status="error"` for that one validator — other validators still run, the app does not crash
- **Output**: `validation_result.json` next to `quality_report.json`. `FileEntry.validation_overall_status` exposes the aggregated pass/warn/fail/error for the recordings list badge
- **How to add a custom validator**: see [docs/domain/custom_validators.md](domain/custom_validators.md)

### Application Lifecycle

Managed by the `lifespan` function in `backend/app/main.py`:

1. **Startup**: Initialize rclpy → start TopicMonitorThread → create ROS2BagRecorder → load custom validators (`load_custom_validators()`)
2. **Running**: FastAPI handles HTTP/SSE requests
3. **Shutdown**: Stop recording if active → stop TopicMonitorThread → shut down rclpy

---

## Frontend Structure

### Architectural Pattern

Adopts the **Bulletproof React** pattern. Components, stores, and utilities are encapsulated per feature domain and exposed externally only through the barrel (`index.ts`).

```
import { RecordingControl } from "@/features/recording";       // OK (via barrel)
import { RecordingControl } from "@/features/recording/store"; // NG (direct internal reference)
```

Direct references matching `@/features/*/*` are forbidden by Biome's `noRestrictedImports` rule.

### orval (auto-generated API types and hooks)

Generates TanStack Query hooks + TypeScript types from the backend's OpenAPI schema. The schema is exported from `create_app()` by `backend/app/openapi.py` into `frontend/openapi.json` (committed, and checked against the code in CI), so generation runs on the host without Docker or a running backend.

```bash
make generate
```

**Import policy:**

| Target | Import source | Example |
|--------|--------------|---------|
| **Types** | Directly from `@/api/generated/schemas` | `import type { TopicInfo } from "@/api/generated/schemas"` |
| **Hooks** (with custom logic) | Wrapper in `@/hooks/use-api` | `import { useRecordingStatus } from "@/hooks/use-api"` |
| **Hooks** (used as-is) | Directly from `@/api/generated/{tag}/{tag}` | When no customization is needed |
| **Query keys** | Directly from `@/api/generated/{tag}/{tag}` | `import { getGetFilesQueryKey } from "@/api/generated/config/config"` |
| **SSE keys** | `@/lib/query-keys` | `import { sseKeys } from "@/lib/query-keys"` |

- `use-api.ts` does not re-export types (not a relay station)
- Use generated type names as-is (aliases only when names collide)
- Do not edit files under `api/generated/` (they are overwritten by `make generate`)

### Directory Structure

→ See the "Frontend" section of [STRUCTURE.md](STRUCTURE.md).

### State Management

Two state-management approaches are used:

**Zustand (client state)** — placed in each feature's `store.ts`:
- Recording operation state: countdown, start/stop flags (`features/recording/store.ts`)
- Currently selected topic (`features/live-topics/store.ts`)
- Panel open/closed state (`stores/panel-store.ts` — shared across features)

**TanStack Query (server state)** — orval-generated hooks + `hooks/use-api.ts` wrappers:
- REST: Uses orval-generated `useGetRecordingStatus`, `useGetFiles`, etc., with select options
- SSE: Manages topic stats, logs, and health checks via custom keys (`lib/query-keys.ts`)
- Query keys: REST uses orval-generated `getXxxQueryKey()` factories; SSE uses custom `sseKeys`

**MutationObserver (mutations from outside React)** — `features/recording/mutations.ts`:
- An orchestration layer for executing TanStack Query mutations from Zustand stores
- Handles cache invalidation and multi-store coordination when recording starts/stops

### Real-time updates via SSE (Server-Sent Events)

```
SSE (/api/topics/stream)
  ├─ topic_stats event (every second)
  │   └─ queryClient.setQueryData(sseKeys.topicStats(), data)
  └─ log event (as they occur)
      └─ queryClient.setQueryData(sseKeys.logs(), ...)

SSE (/api/jobs/stream)
  ├─ queue_snapshot (on connect)
  ├─ job_added / job_started / job_progress / job_completed / job_failed
  └─ Reflects timeline / quality generation status on the MCAP detail page into the cache
```

When an SSE event arrives, the TanStack Query cache is updated directly. This lets the UI reflect updates in real time without polling. `/api/jobs/stream` broadcasts progress for background jobs (MCAP → MP4 conversion / quality analysis / timeline generation).

### Pages and Panel Layout

Uses `react-resizable-panels` v4. The app consists of several pages:

#### Recording page (`/`) — three resizable columns

```
┌──────────────┬──────────────┬──────────────────────┐
│ LiveTopics   │ LiveTopic    │   RecordingControl   │
│ (topic list) │ Details      │   (start/stop)       │
│              │ (Live preview├──────────────────────┤
│              │  / metrics)  │   MonitorTabs        │
│              │              │   (Miss Rate / Logs) │
└──────────────┴──────────────┴──────────────────────┘
```

- Clicking a topic row reveals the **Details column** (a 2-column layout is shown when nothing is selected)
- Recording controls and Loss Rate / Logs are vertically split in the center/right panel

#### Recordings list page (`/recordings`) — table + details

```
┌──────────────────────────────┬──────────────┐
│  Recordings Table             │  MCAP Details │
│  (search / filter / bulk ops) │  (quality)    │
└──────────────────────────────┴──────────────┘
```

Clicking the details panel header navigates to the MCAP detail page (`/recordings/:folder`).

**Filter tabs and search are linked**:

- Filter tabs (All / Report uncreated) and the search box are **linked to the checkboxes**.
- Click a filter tab → clear all existing checks and check every row matching that filter (within the search-applied range).
- Type in the search box → clear all existing checks and check every row matching the filter + search.
- Return to "All" or clear the search → clear all checks.
- This makes "filter or search to narrow down, then bulk-delete with one button" possible with minimal operations.
- The count on each filter tab updates in real time to reflect the breakdown within the current search hits.

**Where bulk actions live**: bulk-action buttons are individual components under `frontend/src/features/recordings/ui/bulk-*.tsx` (today: `bulk-delete-button.tsx`) and mounted inside `features/recordings-table/recordings-table.tsx`. They read the selected set from `useRecordingsStore.checkedFolders` (a Zustand store inside the `recordings` feature). Add new bulk actions by mirroring this pattern.

**Rendering & scan (large lists)**: the table is virtualized with `@tanstack/react-virtual`, so only the rows in view are mounted (each row is absolutely positioned and measured) and the list stays responsive with thousands of recordings. On the backend, `scan_output_dir` caches each folder's parsed metadata keyed by a source-file fingerprint and scans folders in parallel, so repeated list fetches are cheap; file size and mtime are always recomputed fresh so they never go stale.

#### MCAP detail page (`/recordings/:folder`) — integrated timeline view

```
┌─────────────────┬──────────────────────────────────┐
│ Quality Summary │ Timeline Heatmap (always full)    │
│ (quality)        │  └─viewRange overlaid as a band   │
│                  ├──────────────────────────────────┤
│                  │ [▶ Preview] (collapsed by default)│
│ Topics +         │  └─Video + Joint Graph on expand  │
│ Loss Events      ├──────────────────────────────────┤
│ (linked clicks)  │ Loss Rate / Message Ticks         │
│                  │ (Adaptive: rug plot at high zoom) │
│                  ├──────────────────────────────────┤
│                  │ Timeline Controller (pinned)      │
│                  │ time │ ◄◄ ◄ ▶ ► ►► │ ⊙ ⊕        │
│                  │ [seekbar]                          │
│                  │ [minimap + range selector]         │
└─────────────────┴──────────────────────────────────┘
```

**Preview panel separation**:

- The video (MP4) and Joint Graph live inside a collapsible panel that is closed by default. On expand, if MP4 / joint_data have not been generated, a `media` job is enqueued
- **State is not persisted** (the panel is always closed when the page is opened)
- Video grid: up to 4 columns; Joint graphs: up to 2 columns
- Intent: Immediately after navigating to the page, focus resources on timeline generation, and defer the heavy MCAP → MP4 conversion until the user explicitly asks to see it
- Progress is shown in real time via SSE (`useJobsStream`)

**The Timeline Heatmap is independent of viewRange**:

- The heatmap always shows the **entire recording** (acts as an overview map). Narrowing the viewRange via the minimap does not shrink the heatmap
- The current viewRange is overlaid as a semi-transparent **cyan band** on the heatmap, visualizing where the zoom is focused
- Intent: separate "overview" from "detail view". Even when zoomed into a portion, you do not lose sight of which topics drop frames where, across the whole recording

**Timeline Controller layout**:

- Three rows: **row 1** = minimap (range selector), **row 2** = seekbar, **row 3** = control buttons
- The control button row is split into three columns: **left** = time display, **center** = playback controls (play/stop + frame/jump), **right** = zoom
- The center **play/stop button is a large circular button** (echoing the design of the record button), color-coded green when stopped and amber while playing

**Unified topic ordering**:

- LiveTopics / the Topic list on the MCAP detail page / Timeline Heatmap all share the order **"image topics on top, joint (other) below, alphabetical within each category"**
- Implemented by the shared helper [`lib/topic-sort.ts`](../frontend/src/lib/topic-sort.ts) via `sortTopicsByCategory()`. Determined by whether the `msg_type` string contains `Image` (custom message types fall into the joint side)
- Intent: eliminate the confusion of the same topic appearing in different positions on different pages

**Left/right panel coordination**:
- Left: click a topic → the right panel highlights that topic + the minimap background switches to that topic's gaps
- Left: click a loss event → the right panel zooms to that time + moves the playhead
- Right: select a range on the minimap → updates viewRange (does not affect the Timeline Heatmap)
- Right: during playback, the viewRange scrolls to keep the playhead centered

`features/quality-timeline/store.ts` (Zustand) centralizes `viewRange` / `playheadSec` / `selectedTopic` / `isPlaying`, which each UI subscribes to.

---

## Data Flow

### How QoS Auto-Matching Works

Messages are not delivered when publisher and subscriber QoS do not match. In this system, the QoS detected by TopicMonitor is propagated to the recording process so that recordings use the correct QoS without manual configuration.

```
┌──────────────┐                ┌──────────────────────┐
│ Robot         │                │ TopicMonitor (rclpy) │
│ Publisher     │  DDS Discovery │                      │
│ QoS: RELIABLE │ ◀─────────────▶│ get_publishers_info  │
└──────────────┘                │  _by_topic()         │
                                │                      │
                                │ → QoS: RELIABLE [auto]│
                                └──────────┬───────────┘
                                           │ get_topic_stats()
                                           │ (qos_reliability field)
                                           ▼
                                ┌──────────────────────┐
                                │ recording/router.py  │
                                │ _get_qos_overrides() │
                                │                      │
                                │ → {"/topic": "reliable"}
                                └──────────┬───────────┘
                                           │ qos_overrides
                                           ▼
                                ┌──────────────────────┐
                                │ ROS2BagRecorder      │
                                │ _create_qos_override │
                                │  _file()             │
                                │                      │
                                │ → tmp/qos_override_  │
                                │   XXXX.yaml          │
                                └──────────┬───────────┘
                                           │ --qos-profile-overrides-path
                                           ▼
                                ┌──────────────────────┐
                                │ ros2 bag record      │
                                │ (subprocess)         │
                                │                      │
                                │ Records with         │
                                │ QoS: RELIABLE        │
                                └──────────────────────┘
```

When QoS information cannot be obtained, falls back to no override (the default behavior of `ros2 bag record`).

### Recording Workflow

```
1. User clicks the record button
   └─ POST /api/recording/start { topics: [...] }

2. QoS auto-matching (before recording starts)
   ├─ TopicMonitor has already obtained each topic's publisher QoS
   ├─ recording/router.py collects the QoS info from TopicMonitor
   └─ Generates qos_overrides.yaml in tmp/

3. ROS2BagRecorder launches the subprocess
   └─ ros2 bag record -s mcap --qos-profile-overrides-path qos.yaml -o ... {topics...}

4. Recording in progress (minutes to tens of minutes)
   ├─ The subprocess writes to the MCAP file
   ├─ TopicMonitor computes real-time quality
   └─ Broadcasts to the frontend via SSE (every second)

5. User clicks the stop button
   └─ POST /api/recording/stop
       ├─ SIGINT → graceful shutdown
       ├─ Automatically deletes qos_overrides.yaml
       └─ Starts a background task:
           ├─ Wait 2 seconds (let MCAP writes complete)
           ├─ Run analyze_and_save() for quality analysis
           └─ Save quality_report.json

6. The new recording appears in the file list
   └─ Quality report can be viewed
```

### Live Preview

Selecting a topic in Topic Details and pressing the Live button shows real-time data content. Usable while recording is in progress as well.

```
Image topics (CompressedImage):
  Browser <img> ← MJPEG (multipart/x-mixed-replace, normally 2fps / 30fps in Live)
                ← GET /api/topics/image/stream?topic=...
                ← TopicMonitor._live_raw_image (swaps the latest-frame reference)
                ← on_message: bytes(msg.data)

Sensor topics (JointState, etc.):
  Browser (30fps polling) ← GET /api/topics/live/positions?topic=...
                          ← TopicMonitor._live_positions (swaps the array)
                          ← on_message: list(msg.position)
```

| Item | Image | Sensor |
|---|---|---|
| Delivery | MJPEG stream | SSE stream |
| Frame rate | normally 2fps / 30fps in Live | 30fps |
| Extra work in on_message | `bytes(msg.data)` reference swap | `list(msg.position)` swap |
| Max duration | 1 minute (auto-stop) | 1 minute (auto-stop) |
| Performance impact | one topic only, outside the lock | one topic only, O(1) inside the lock |

---

## Docker Setup

### Development environment (`docker-compose.yml`)

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   simulator     │     │    backend      │     │   frontend      │
│ (ROS2 Humble)   │◄───►│ (ROS2 + FastAPI)│◄───►│  (Vite dev)     │
│ Robot           │ DDS │ :8000           │ HTTP│  :5173          │
│ Dummy data feed │     │ Hot reload      │     │  Hot reload     │
│ [profile: sim]  │     │                 │     │                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

- `make up` starts three containers (with the simulator)
- Source code is volume-mounted for hot reloading
- Recording data is mounted at `./output`

### Production environment (`docker-compose.prod.yml`)

```
┌──────────────────────────────────────────────────────────┐
│                        Linux host                        │
│                                                          │
│  ┌────────────────────┐        ┌──────────────────────┐  │
│  │      backend       │  HTTP  │       frontend       │  │
│  │ network_mode: host │◄──────►│      (Vite dev)      │  │
│  │ :8000              │        │        :5173         │  │
│  └─────────┬──────────┘        │ backend:host-gateway │  │
│            │ DDS               └──────────────────────┘  │
│  ┌─────────▼──────────────────────────────────────────┐  │
│  │                     Real Robot                     │  │
│  └────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

- `network_mode: host` on the backend allows ROS2 DDS discovery to talk to the real robot
- The frontend is served by the same Vite dev server as development (`pnpm run dev` on :5173). There is no separate production build or static file server
- Only the backend joins the host network, so the frontend container reaches it through the `backend:host-gateway` entry declared in `extra_hosts`

---

## Output Format

Recording data is saved in the following structure:

```
output/
└── {timestamp}/                     # e.g. 20260308_150000
    ├── {timestamp}_0.mcap           # MCAP file generated by ros2 bag record
    ├── metadata.yaml                # Metadata generated by ros2 bag record
    └── quality_report.json          # Generated by the quality analysis engine (after recording stops)
```

- **MCAP file**: Message data for all topics (with timestamps)
- **metadata.yaml**: Topic list, message counts, recording duration (used by `ros2 bag info`)
- **quality_report.json**: Per-topic quality metrics (stored as a cache)
