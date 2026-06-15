# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A ROS2-based robot data recording system. Records ROS2 topics from ROS2-compatible robots and outputs them in MCAP format. Targets robot teaching and teleoperation workflows.

## Development Commands

```bash
make setup             # Initial setup
make up                # Start the dev environment (with simulator; Frontend: :5173, Backend: :8000)
make dev-up            # Start in dev mode (VITE_DEV_MODE=true: shows developer UI such as command copy and StatusBar)
make down              # Stop
make logs              # Show logs
make ps                # Show container status
make lint              # Lint (everything: backend + frontend)
make lint-backend      # Lint (ruff + mypy)
make lint-frontend     # Lint (tsc + biome)
make test              # Test (everything: backend + frontend)
make test-backend      # Test (pytest, inside Docker)
make test-frontend     # Test (vitest)
make test-cov          # Test + coverage (everything)
make test-cov-backend  # Test + coverage (pytest, inside Docker)
make test-cov-frontend # Test + coverage (vitest)
make format            # Format (everything: backend + frontend)
make format-backend    # Format (ruff)
make format-frontend   # Format (biome)
make generate          # Regenerate API types (requires: backend running)
make build             # Build Docker images
make minio-up          # Start the local MinIO sandbox + auto-create the bucket (for upload-feature testing)
make minio-down        # Stop the local MinIO sandbox
make prod-up           # Production start (host network)
```

## Architecture

→ Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

A **hybrid architecture** is used:

| Function | Technology | Reason |
|------|------|------|
| Recording | `subprocess` (`ros2 bag record`) | Memory isolation; safe even for long recordings |
| Monitoring | `rclpy` (lightweight) | For real-time alerts; keeps only the latest N messages |
| Quality analysis | `mcap` Python library | Accurate metrics computed via post-hoc analysis |

## Key Technical Decisions

- **Recording runs via subprocess**: `ros2 bag record -s mcap` runs in a separate process. No buffering on the Python side (for memory safety).
- **Output format is MCAP**: Explicitly specified via the `-s mcap` option (not the default sqlite3).
- **Recording configuration is YAML**: Topics, expected Hz, ROS_DOMAIN_ID, validators, etc. are managed via YAML files in the `config/` directory. Switched via the `RECORDING_CONFIG` environment variable.
- **Docker required**: Both development and production run via Docker Compose.
- **Timestamps prefer header.stamp**: MCAP quality analysis, MP4 generation, and live quality (when `stamp_quality: true`) prefer `header.stamp`. This eliminates DDS delivery jitter for accurate quality evaluation. For message types without `header`, falls back to `log_time` (`backend/app/shared/stamp.py`).
- **Loss detection is IQR-based**: Instead of a fixed multiplier, uses a statistical threshold (`Q3 + 1.5×IQR`) to detect per-frame losses. Recorded as `LossEvent` (severity=minor/major) and used for per-topic status determination.
- **Image/Joint detection is automatic**: Determined by structure (presence of `format` + `data` fields), not by hard-coded message type names. Also supports vendor-specific or user-defined message types that nest a `JointState` inside a `joint_state` field. See [examples/custom_ros2_messages/](examples/custom_ros2_messages/) for how to plug in custom message packages.
- **Video preview is MCAP → MP4 conversion**: When the Preview on the recording detail page is opened, per-camera MP4s are generated from the MCAP and persisted in the recording directory. FPS is fixed at 30 (`backend/app/features/media/video_generator.py:VIDEO_FPS`). Frames are piped to ffmpeg one at a time to keep memory usage constant.
- **Feature boundaries follow the "recording lifecycle"**: `recordings` (directory operations) / `analysis` (quality and timeline; persistent findings) / `media` (MP4 / Joint data generation for preview) / `validation` (per-recording rule checks) / `upload` (zip + ship to an `UploadDestination`) are managed as independent features.
- **MCAP I/O is consolidated in `backend/app/infra/mcap/`**: Centralizes `make_reader` + `DecoderFactory` initialization, header.stamp-preferred timestamp normalization, and image/Joint structure detection. All consumers in analysis / media read MCAP through this layer.
- **Validation takes a ValidationContext as input**: After a recording stops, quality → validation runs automatically as a chain in JobQueue, and results are saved to `validation_result.json`. `ValidationContext` is a frozen dataclass bundling `QualityReport` / `recording_dir` / `mcap_path` / `recording_meta`; it also exposes the MCAP path so validators can read raw frames with `MCAPReader` when needed (if you only need aggregated values, `ctx.report` is enough). Builtins live in `backend/app/features/validation/builtins/` with their params controlled by `active_set.py`; user-defined validators go in `backend/app/features/validation/custom/` registered via `@register_validator` and applied on restart. See [docs/domain/custom_validators.md](docs/domain/custom_validators.md) for how to add a custom validator.
- **Upload destinations are pluggable behind a Protocol**: The upload feature is generic over the storage backend. `UploadDestination` (in `backend/app/features/upload/destinations/base.py`) defines `configuration_error()` + `upload(local_path, key, progress) -> UploadResult`; `S3Destination` is the only implementation today (also covers MinIO / R2 / LocalStack via `AWS_ENDPOINT_URL`), and the registry returns a single active destination per machine. Adding a new backend (GCS, local-network server) means one new module under `destinations/` + a registry update — `UploadService` / `JobQueue` / `UploadState` are destination-agnostic. See [docs/domain/upload.md](docs/domain/upload.md) for the lifecycle, key-template syntax, and failure modes.

## Frontend Architecture

Uses the **Bulletproof React** pattern. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for details.

- **Per-feature encapsulation**: Place components, stores, and utilities under `features/` per functional domain (recording, live-topics, monitor, quality-summary, quality-timeline, recordings, recordings-table, settings).
- **New functionality goes in a feature**: When adding a new domain feature, create a feature directory under `features/` and follow the Bulletproof pattern. Stores and forms also live inside the feature.
- **Barrel exports**: Each feature's `index.ts` defines the public API. External code imports only via `@/features/xxx`.
- **No internal references**: Biome's `noRestrictedImports` makes direct references to `@/features/*/*` an error.
- **Placement rule**: Modules used by only one feature live inside that feature; modules shared across multiple features live in `hooks/`, `lib/`, or `stores/`.
- **Keep individual files small**: Small UI components inside a feature go in `features/xxx/ui/`. Once shared across multiple features, promote them to `components/ui/`.
- **API type generation**: orval auto-generates TanStack Query hooks + types from OpenAPI (`make generate`; run while the backend is up).
- **Import rule**: Types are imported directly from `@/api/generated/schemas`. Do not re-export types from `use-api.ts`. Use generated type names as-is (alias only on name collision).
- **Use orval-generated types**: API response/request types must use the orval-generated schemas (`@/api/generated/schemas`). Do not define types manually. After backend schema changes, regenerate with `make generate`.

## Testing

→ Details: the "Testing" section of [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)

- **Maintain 100% coverage** — verify with `make test-cov`.
- The test structure mirrors the `backend/app/` directory structure (`backend/tests/features/recording/test_service.py` → `backend/app/features/recording/service.py`).
- Untestable code (rclpy runtime, Docker-only, MCAP I/O) is excluded via `pragma: no cover` and not tested.
- Endpoint functions in `router.py` are HTTP glue code and are excluded with `pragma: no cover`. Pure logic is extracted out of the router and tested (e.g., `scanner.py`).
- Tests that only run inside Docker (rclpy-dependent) are auto-skipped with `pytest.importorskip("rclpy")`.
- Tests must not depend on filesystem permissions (chmod); use `unittest.mock.patch` instead (chmod fails as Docker root).

## Coding Style

- **Comments describe the code's responsibility and current constraints, not its history** (notes like "this used to be ...", "this was duplicated so we abstracted it", etc. belong in the commit message / PR description). See [docs/CODING_STYLE.md](docs/CODING_STYLE.md) for details.
- Python: Method order is `__init__` → public → private (newspaper style).
- Python: The order of public methods matches the order of the corresponding API endpoints.
- Python: `schemas.py` contains only API request/response schemas. Domain models with business logic belong in `models.py`.
- Python: pydantic response models **must not have default values** (use `field: int`, not `field: int = 0`). A default value removes the field from `required` in OpenAPI, causing orval to generate `field?: number` → the frontend ends up with a lot of `?? 0` fallbacks. Fields that can be null should be `field: int | None` (no default; required and nullable). See [docs/CODING_STYLE.md](docs/CODING_STYLE.md) for details.
- Frontend: Inside a route/component, hooks and variables are ordered by the following sections. Skip sections that don't apply. Section dividers are a single-line `// --- XX ---` comment (no separator lines).
  1. **Routing** — `useNavigate`, `useParams`
  2. **Server state** — TanStack Query (`useFiles`, `useConfig`, etc.) and values derived from them (`useMemo`)
  3. **Streaming / subscription** — SSE (`useTopicsStream`, `useJobsStream`, etc.)
  4. **Side effects** — `useEffect` (any required `useRef` setup goes in this section)
  5. **Event handlers** — Define here only handlers that are used in multiple places, are memoized with `useCallback`, or have a long body. Inline single-use, non-memoized, short handlers into the JSX.
  6. **Render-only state** — store selects used only in JSX (`leftOpen` / `isRecording`, etc.)
- Within a section, group items "just before their use site".
- If the ordering rules in CLAUDE.md need updating or a new section needs to be added, edit this section.
- **Frontend: Inline single-use short descriptive variables and event handlers into the JSX** (reduces the burden of following them via a name and puts the logic next to its trigger). When the same setter is called with different arguments based on a condition, use a ternary to "branch inside the argument". See [docs/CODING_STYLE.md](docs/CODING_STYLE.md#inlining-policy-typescript--react) for details and exceptions.
- **Frontend icons use `lucide-react`** (use `lucide-react` components instead of inline SVG or emoji; brand logos and other special SVGs are excluded).
- **Frontend font sizes are 13px or larger** (applies to CSS, inline styles, and Canvas drawing).
- **Do not use `any` in the frontend** — for complex library generic types, extract the concrete type via a custom hook + `ReturnType<typeof hook>`. Do not allow `any` via `biome-ignore`.

## Documentation

- **Be strict about DRY** — do not write the same information in multiple documents. Describe details in one place and link to it from elsewhere.
- **Update documentation when code changes** — when making changes that affect the Makefile, API, configuration, architecture, etc., always update the related documentation (CLAUDE.md, files under `docs/`).

## Reference

- [docs/](docs/) - Project documentation (architecture, API, quality analysis, setup, etc.)
- `.local/docs/` - Research material (MCAP, etc.)
- `.local/sample_data/` - Sample MCAP files (~5.4GB)
