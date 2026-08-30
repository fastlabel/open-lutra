# Directory Structure

> Single source of truth for the project's directory structure. Update this file when adding new files or directories.

## Project Root

```
open-lutra/
├── backend/                    # Backend (FastAPI, Bulletproof pattern)
│   ├── pyproject.toml          # Python settings
│   ├── uv.lock                 # uv lockfile
│   ├── app/                    # Python package (source)
│   └── tests/                  # Backend tests (mirrors backend/app/)
├── frontend/                   # Frontend (React + Vite, Bulletproof React)
├── simulator/                  # Development simulator
│   ├── robot_simulator.py
│   └── Dockerfile
├── docs/                       # Documentation
├── .devcontainer/              # Dev Container settings
├── .local/                     # Local materials (gitignored)
├── docker-compose.yml          # Development environment
├── docker-compose.prod.yml     # Production overrides
├── Dockerfile                  # Backend image
├── Makefile                    # Command collection
└── .env                        # Environment variables (gitignored)
```

## Backend (`backend/app/`)

```
backend/app/
├── main.py                    # FastAPI entry point, lifecycle management
├── settings.py                # pydantic-settings configuration class
├── dependencies/              # FastAPI Depends (DI, path validation, exception handlers)
├── features/                  # Feature domains (Bulletproof pattern)
│   ├── recording/             # Recording start/stop/status
│   │   ├── router.py          # API endpoints
│   │   ├── service.py         # ROS2BagRecorder (subprocess recording)
│   │   ├── models.py          # Domain models / exceptions (RecorderStatus, etc.)
│   │   └── schemas.py         # API schemas (RecordingStartRequest, etc.)
│   ├── topics/                # Topic monitoring, SSE streams
│   │   ├── router.py          # API endpoints
│   │   ├── service.py         # TopicMonitorService (rclpy-independent)
│   │   ├── models.py          # Domain models (TopicStats, etc.)
│   │   └── schemas.py         # API schemas (TopicInfo, etc.)
│   ├── recordings/            # Recording directory operations (list / rename / delete)
│   │   ├── router.py          # API endpoints (/api/recordings)
│   │   ├── scanner.py         # Scans recording folders directly under output_dir
│   │   └── schemas.py         # API schemas (FileEntry, FilesResponse, etc.)
│   ├── analysis/              # Post-recording analysis (quality_report.json / timeline_data.json)
│   │   ├── router.py          # API endpoints (/api/analysis/*)
│   │   ├── mcap_analyzer.py   # MCAP file I/O (header.stamp preferred)
│   │   ├── quality_analyzer.py # Background quality analysis management
│   │   ├── timeline_analyzer.py # Timeline binning + cache + rug plot message retrieval
│   │   ├── models.py          # Domain models (QualityReport, TopicQuality, LossEvent, etc.)
│   │   └── schemas.py         # API schemas (QualityResponse, TimelineResponse, etc.)
│   ├── media/                 # Preview-panel data generation for the recording detail page (MP4 / Joint)
│   │   ├── router.py          # API endpoints (/api/media/video, /api/media/joints)
│   │   ├── mcap_converter.py  # MCAP→MP4 streaming conversion engine (ffmpeg subprocess)
│   │   ├── video_generator.py # Enumerates generated MP4 files + fixed-FPS constant
│   │   ├── joint_reader.py    # Reads JointState time-series + cache (for preview graph)
│   │   ├── models.py          # Domain models (JointStateMapping, TopicRole, etc.)
│   │   └── schemas.py         # API schemas (VideoResponse, VideoProgress)
│   ├── jobs/                  # Background job queue
│   │   ├── router.py          # API endpoints (/jobs/stream SSE, etc.)
│   │   ├── service.py         # JobQueue (asyncio.Queue + single worker, SSE broadcasting)
│   │   ├── models.py          # Job / JobStatus / JobType (media/timeline/quality/validation/upload)
│   │   └── schemas.py         # API schemas
│   ├── validation/            # Per-recording rule checks (validation_result.json)
│   │   ├── router.py          # API endpoints (/api/validation)
│   │   ├── service.py         # ValidationService (API facade; delegates to JobQueue)
│   │   ├── runner.py          # ValidationRunner (orchestrates builtin + custom validators)
│   │   ├── context.py         # ValidationContext (frozen dataclass bundling report + paths + meta)
│   │   ├── registry.py        # @register_validator + custom-validator discovery
│   │   ├── active_set.py      # Builtin validator config (which builtins are on + their params)
│   │   ├── builtins/          # Builtin validators (required_topics_present, total_duration_sec, ...)
│   │   ├── custom/            # User-defined validators (auto-loaded on startup)
│   │   ├── cache.py           # Load / save validation_result.json
│   │   ├── models.py          # Domain models (ValidationReport, ValidationResult, ValidationStatus)
│   │   └── schemas.py         # API schemas (ValidationResponse)
│   ├── upload/                # Recording → zip → upload destination (S3 / local; future GCS)
│   │   ├── router.py          # API endpoints (/api/upload, /api/upload/start)
│   │   ├── service.py         # UploadService + is_upload_enabled (API facade; delegates to JobQueue)
│   │   ├── destinations/      # Pluggable upload-destination backends
│   │   │   ├── base.py        # UploadDestination Protocol + UploadResult + ProgressCallback
│   │   │   ├── registry.py    # get_active_destination(settings) — switches on UPLOAD_DESTINATION
│   │   │   ├── disabled.py    # DisabledDestination (returned when UPLOAD_DESTINATION is unset)
│   │   │   ├── s3.py          # S3Destination (boto3 + S3-compatible endpoints incl. MinIO)
│   │   │   └── local.py       # LocalDestination (shutil.copyfile to a bind-mounted directory)
│   │   ├── zip_builder.py     # Zip the recording folder (mtime-keyed reuse)
│   │   ├── key_template.py    # Render the destination key from {recording_name} / {yyyymmddhhmmss}
│   │   ├── progress.py        # ThrottledProgress callback (boto3 → SSE / state-file, 1 Hz)
│   │   ├── cache.py           # Load / save upload_state.json
│   │   ├── models.py          # UploadState (status / destination / key / etag / bytes / timestamps)
│   │   └── schemas.py         # API schemas (UploadResponse)
│   └── config/                # System configuration, memory / storage info
│       ├── router.py          # API endpoints
│       ├── memory_reader.py   # Reads memory usage from cgroup
│       ├── mapper.py          # Pure mapping to API responses (metadata fields, storage)
│       └── schemas.py         # ConfigResponse, MemoryInfo, StorageInfo
├── infra/                     # Infrastructure layer
│   ├── mcap/                  # Shared MCAP file I/O layer (used by analysis / media)
│   │   ├── reader.py          # MCAPReader (context manager) + find_mcap_files
│   │   ├── timestamp.py       # header.stamp-preferred timestamp normalization
│   │   └── messages.py        # Image detection / JointState structure extraction (supports custom message types)
│   └── ros2/                  # ROS2-related (rclpy-dependent, CLI, QoS)
│       ├── command.py         # ROS2 CLI wrapper (subprocess)
│       ├── qos.py             # QoS override YAML management
│       ├── topic_node.py      # TopicMonitorNode (rclpy-dependent)
│       ├── message.py         # Message conversion / sanitization
│       └── thread.py          # Background thread management
└── shared/                    # Modules shared across multiple features
    ├── log_manager.py         # Log management
    ├── disk.py                # Capacity of the volume holding the recordings (statvfs)
    └── stamp.py               # ROS2 message header.stamp extraction utility
```

## Frontend (`frontend/src/`)

```
frontend/src/
├── App.tsx                        # Root: TanStack Router initialization
├── main.tsx                       # ReactDOM entry point
├── api/                           # API client layer
│   ├── fetch-client.ts            # Custom fetch client (orval mutator)
│   └── generated/                 # Auto-generated by orval (do not edit, tags-split mode)
│       ├── recording/             # Recording API (hooks + MSW mocks)
│       ├── recordings/            # Recording directory operations API
│       ├── topics/                # Topic monitoring API
│       ├── analysis/              # Quality / timeline analysis API
│       ├── media/                 # MP4 / Joint preview API
│       ├── config/                # System config API
│       ├── jobs/                  # Job queue API
│       ├── validation/            # Validation API
│       ├── upload/                # Upload API (/api/upload)
│       └── schemas/               # TypeScript type definitions (barrel export)
├── features/                      # Feature domains (Bulletproof React)
│   ├── recording/                 # Recording controls
│   │   ├── index.ts               # Barrel (public API)
│   │   ├── recording-control.tsx  # Record button + delay / sound-toggle settings
│   │   ├── completion-banner.tsx  # Latest-record banner (open details / delete / dismiss)
│   │   ├── storage-indicator.tsx  # Free space on the output volume (event-refreshed, manual reload)
│   │   ├── timer.tsx              # Timer display
│   │   ├── store.ts               # Zustand: countdown, start/stop state, sound preference
│   │   ├── mutations.ts           # MutationObserver: recording ops from outside React
│   │   ├── sounds.ts              # Web Audio notification tones (countdown / start / stop)
│   │   └── create-timer.ts        # setTimeout/clearTimeout wrapper
│   ├── live-topics/               # ROS2 topic live quality monitoring + preview (left panel of the recording page)
│   │   ├── index.ts               # Barrel
│   │   ├── live-topics.tsx        # LiveTopics (topic list)
│   │   ├── store.ts               # Zustand: selected topic, focus, Live mode
│   │   └── ui/
│   │       ├── topic-list.tsx     # Topic list
│   │       ├── topic-item.tsx     # Topic row (shows Hz/loss/drop)
│   │       └── topic-details.tsx  # Mini dashboard + Live (image MJPEG / sensor bar gauge)
│   ├── monitor/                   # Quality charts + logs
│   │   ├── index.ts               # Barrel
│   │   ├── monitor-tabs.tsx       # Tab switcher (Loss Rate / Logs)
│   │   ├── loss-rate-chart.tsx    # uPlot Loss Rate real-time chart
│   │   ├── log-viewer.tsx         # Log list + severity filter
│   │   └── store.ts               # Zustand: log filter settings
│   ├── quality-summary/           # Static summary of the quality report (shared across 3 pages)
│   │   ├── index.ts               # Barrel
│   │   ├── quality-summary.tsx    # QualitySummary (displays the quality report)
│   │   ├── quality-utils.tsx      # Quality display utilities (statusIcon / shortMsgType, etc.)
│   │   └── ui/
│   │       ├── topic-quality-row.tsx  # Topic quality row (linked to loss-event clicks)
│   │       ├── topic-metrics.tsx      # Metrics row (type / msgs / loss rate / delay / empty / expand toggle)
│   │       └── topic-details.tsx      # Expanded details (size stats, timing, loss events)
│   ├── quality-timeline/          # Timeline visualization of the quality report (right panel of the MCAP detail page)
│   │   ├── index.ts               # Barrel
│   │   ├── quality-timeline.tsx   # QualityTimeline (integrated UI for timeline, video, and graphs)
│   │   ├── store.ts               # Zustand: viewRange, playheadSec, selectedTopic, isPlaying
│   │   ├── use-timeline.ts        # Timeline / message-detail API hook
│   │   ├── loss-rate-utils.ts     # Pure helpers that build the Loss Rate sliding-window series
│   │   └── ui/
│   │       ├── timeline-heatmap.tsx   # Horizontal bar heatmap of all topics
│   │       ├── timeline-controller.tsx # Playback, seek, zoom, minimap (pinned at the bottom)
│   │       ├── minimap.tsx            # Minimap (background heatmap + range selector)
│   │       ├── video-grid.tsx         # Multi-camera video grid + progress display
│   │       ├── video-player.tsx       # Individual video player (playhead-synced)
│   │       ├── joint-graph.tsx        # Joint position uPlot graph
│   │       ├── loss-rate-chart.tsx    # Loss Rate uPlot graph
│   │       ├── rug-plot.tsx           # Message ticks (shown at high zoom)
│   │       ├── adaptive-detail.tsx    # Wrapper around Loss Rate / Rug Plot
│   │       └── preview-panel.tsx      # Collapsible panel containing video + Joint Graph
│   ├── recordings/                # Recording list (right panel)
│   │   ├── index.ts               # Barrel
│   │   ├── store.ts               # Zustand: selected folder / check state
│   │   └── ui/                    # UI components
│   │       ├── recording-list-item.tsx
│   │       ├── bulk-delete-button.tsx
│   │       ├── file-meta-line.tsx
│   │       └── file-state-badges.tsx  # Timeline generation status badges
│   ├── recordings-table/          # Recordings table (/recordings page)
│   │   ├── index.ts               # Barrel
│   │   ├── recordings-table.tsx   # Table body (search / filter / bulk operations)
│   │   ├── store.ts               # Zustand: filter tab / search text
│   │   ├── utils.ts               # Filter / search utilities (applyFilter / applySearchAndFilter)
│   │   └── ui/                    # UI components
│   │       ├── filter-tabs.tsx        # Filter tabs (All / Report uncreated, shows search hit counts)
│   │       └── quality-create-button.tsx
│   ├── settings/                  # Settings (inline task-name editor in the header)
│   │   ├── index.ts               # Barrel
│   │   ├── schema.ts              # Valibot validation schema for the task name
│   │   ├── store.ts               # Zustand: persisted task name
│   │   └── ui/
│   │       └── task-name-inline-editor.tsx # Inline task-name editor in the header
│   ├── validation/                # Validation summary panel + per-row badge
│   │   ├── index.ts               # Barrel (ValidationSummary, ValidationBadge)
│   │   ├── validation-summary.tsx # Per-validator pass/warn/fail/error panel
│   │   ├── validation-badge.tsx   # Row badge (validation_overall_status)
│   │   └── ui/
│   │       └── status-badge.tsx   # Status icon primitive shared between summary + badge
│   └── upload/                    # Upload-to-destination button + per-row badge
│       ├── index.ts               # Barrel (UploadButton, UploadBadge)
│       ├── upload-button.tsx      # Detail-page action (Upload / Uploading N% / Re-upload / Retry)
│       └── upload-badge.tsx       # Row badge (FileEntry.upload_status + live job progress)
├── components/
│   ├── layout/
│   │   ├── header.tsx             # Header (OpenLUTRA brand + nav + task name)
│   │   ├── StatusBar.tsx          # Status bar (development-only)
│   │   └── logo-mark.tsx          # Logo mark used as favicon
│   └── ui/                        # shadcn/ui primitives
├── hooks/                         # Shared hooks
│   ├── use-api.ts                 # TanStack Query wrapper (extensions of orval-generated hooks)
│   ├── use-topics-stream.ts       # SSE connection → Query cache update
│   ├── use-jobs-stream.ts         # Job queue SSE connection (progress → cache update)
│   ├── use-upload-status.ts       # Persisted upload state + live job progress, fused
│   └── use-file-entries.ts        # FileEntry[] thin wrapper
├── lib/                           # Shared utilities
│   ├── query-keys.ts              # SSE Query Keys (REST keys are orval-generated)
│   ├── query-client.ts            # QueryClient instance
│   ├── format.ts                  # Size / time formatting
│   ├── file-utils.ts              # File utilities
│   ├── topic-sort.ts              # Unified topic ordering (images on top, joint on bottom)
│   └── utils.ts                   # General utilities such as cn()
├── stores/                        # Shared Zustand stores (used by multiple features)
│   ├── panel-store.ts             # UI state such as bottom-panel tab selection and DevTools visibility
│   └── quality-history-store.ts   # Quality data time-series (for the Hz Chart)
└── routes/                        # TanStack Router page definitions
    ├── __root.tsx                 # Root layout (QueryClientProvider, etc.)
    ├── index.tsx                  # Recording page (/)
    ├── tasks.tsx                  # Tasks list page (/tasks) — currently an empty placeholder
    ├── recordings.tsx             # Recordings list page (/recordings)
    └── recordings_.$folder.tsx    # MCAP detail page (/recordings/:folder) — standalone route
```

## Tests

### Backend (`backend/tests/`)

Mirrors the `backend/app/` directory structure to make each test file's responsibility clear.

```
backend/tests/
├── conftest.py                          # Shared fixtures
├── dependencies/
│   ├── test_path_validators.py          # Path validation (resolve_safe_path, require_dir, require_file)
│   ├── test_services.py                 # DI dependency functions (get_recorder, get_monitor)
│   └── test_exception_handlers.py       # Exception handlers
├── features/
│   ├── recording/
│   │   ├── conftest.py                  # Recorder fixtures (settings, mock_ros2)
│   │   ├── test_service.py              # ROS2BagRecorder (start, stop, status, QoS)
│   │   └── test_router.py               # Recording API endpoints
│   ├── topics/
│   │   ├── conftest.py                  # Monitor fixtures (log_manager, mock_subscriber)
│   │   ├── test_models.py               # TopicStats properties (actual_hz, status, etc.)
│   │   ├── test_service.py              # TopicMonitorService (discover, message, gap_check)
│   │   └── test_router.py               # Topic API endpoints
│   ├── recordings/
│   │   └── test_scanner.py              # scan_output_dir, read_metadata_summary
│   ├── analysis/
│   │   ├── test_models.py               # TopicQuality, QualityReport (quality-metric computation)
│   │   ├── test_mcap_analyzer.py        # load_report (JSON I/O)
│   │   └── test_timeline_analyzer.py    # Timeline binning / gap detection
│   ├── media/
│   │   └── test_models.py               # JointStateMapping (topic classification for preview)
│   └── config/
│       ├── test_mapper.py               # Mapping to API responses (metadata fields, storage)
│       └── test_router.py               # Config API endpoints
├── infra/ros2/
│   ├── test_message.py                  # sanitize_value (message conversion)
│   └── test_qos.py                      # QoSOverrideFile (YAML generation / deletion)
└── shared/
    ├── test_log_manager.py              # LogManager (append, fetch, filter)
    ├── test_disk.py                     # read_disk_usage (capacity / uninspectable path)
    └── test_stamp.py                    # extract_stamp_sec/ns (header.stamp extraction)
```

### Frontend

```
frontend/src/
├── __mocks__/zustand.ts                          # Zustand auto-reset mock
├── test/setup.ts                                 # MSW server startup / reset
├── test/test-utils.tsx                           # render with QueryClientProvider
├── mocks/server.ts                               # MSW server (orval-generated handlers)
├── lib/__tests__/*.test.ts                       # Unit tests for utilities
├── hooks/__tests__/*.test.tsx                    # Unit tests for hooks
├── stores/__tests__/*.test.ts                    # Unit tests for shared stores
└── features/{feature}/__tests__/*.test.ts        # Feature-specific unit tests
```
