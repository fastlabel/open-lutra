# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A ROS2-based robot data recording system. Records ROS2 topics from ROS2-compatible robots and outputs them in MCAP format. Targets robot teaching and teleoperation workflows.

## Development Commands

```bash
make up        # Start the dev environment (with simulator; Frontend: :5173, Backend: :8000)
make lint      # Lint (backend: ruff + mypy / frontend: tsc + biome)
make test-cov  # Test + coverage (backend: pytest / frontend: vitest)
make format    # Format (backend: ruff / frontend: biome)
make generate  # Regenerate API types (exports OpenAPI + runs orval; no running backend needed)
```

Run `make help` for the full target list (per-side variants such as `lint-backend`, the MinIO sandbox, production targets, ...).

## Architecture

A **hybrid architecture** is used: recording via `subprocess` (`ros2 bag record`, memory-isolated), monitoring via a lightweight `rclpy` node (keeps only the latest message per topic), and quality analysis via the `mcap` Python library (accurate post-hoc metrics). → Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

## Key Technical Decisions

- **Recording runs via subprocess**: `ros2 bag record -s mcap` runs in a separate process. No buffering on the Python side (for memory safety).
- **Output format is MCAP**: Explicitly specified via the `-s mcap` option (not the default sqlite3).
- **Recording configuration is YAML**: Topics, expected Hz, ROS_DOMAIN_ID, validators, etc. are managed via YAML files in the `config/` directory. Switched via the `RECORDING_CONFIG` environment variable.
- **Docker required**: Both development and production run via Docker Compose.
- **Timestamps prefer header.stamp**: MCAP quality analysis, MP4 generation, and live quality (when `stamp_quality: true`) prefer `header.stamp`. This eliminates DDS delivery jitter for accurate quality evaluation. For message types without `header`, falls back to `log_time` (`backend/app/shared/stamp.py`).
- **Loss detection is IQR-based**: Instead of a fixed multiplier, uses a statistical threshold (`Q3 + 1.5×IQR`) to detect per-frame losses. Recorded as `LossEvent` (severity=minor/major) and used for per-topic status determination.
- **Image/Joint detection is automatic**: Determined by message structure, not by hard-coded message type names, so vendor-specific or user-defined message types work. See [examples/custom_ros2_messages/](examples/custom_ros2_messages/) for the detection rules and how to plug in custom message packages.
- **Video preview is MCAP → MP4 conversion**: When the Preview on the recording detail page is opened, per-camera MP4s are generated from the MCAP and persisted in the recording directory. Frames are piped to ffmpeg one at a time to keep memory usage constant.
- **Feature boundaries follow the "recording lifecycle"**: `recordings` (directory operations) / `analysis` (quality and timeline; persistent findings) / `media` (MP4 / Joint data generation for preview) / `validation` (per-recording rule checks) / `upload` (zip + ship to an `UploadDestination`) / `lerobot_export` (MCAP → LeRobot dataset) are managed as independent features.
- **LeRobot export is a self-implemented v3.0 writer**: Converts selected recordings (one recording = one episode) into a LeRobot v3.0 dataset without depending on the `lerobot`/torch package. The topic mapping is declared in the active recording config's `lerobot_export:` section, and output goes to the reserved `<output_dir>/_lerobot_exports/` directory. See [docs/domain/lerobot_export.md](docs/domain/lerobot_export.md).
- **MCAP I/O is consolidated in `backend/app/infra/mcap/`**: Centralizes `make_reader` + `DecoderFactory` initialization, header.stamp-preferred timestamp normalization, and image/Joint structure detection. All consumers in analysis / media read MCAP through this layer.
- **Validation takes a ValidationContext as input**: After a recording stops, quality → validation runs automatically as a chain in JobQueue, and results are saved to `validation_result.json`. Builtins live in `backend/app/features/validation/builtins/`; user-defined validators go in `custom/` and are applied on restart. See [docs/domain/custom_validators.md](docs/domain/custom_validators.md).
- **Upload destinations are pluggable behind a Protocol**: `UploadDestination` (`backend/app/features/upload/destinations/`) abstracts the storage backend; `UPLOAD_DESTINATION` selects the active one (S3-compatible / local filesystem today), and when unset the upload feature is disabled. See [docs/domain/upload.md](docs/domain/upload.md).
- **Pre-registered recording metadata is master-defined**: Fields are declared in the active recording config's `metadata_fields:` section, filled by operators in the recording bar, and written into each recording's `recording_meta.json` under `metadata` — **always stored as strings**, validated only in the UI. See [docs/domain/metadata.md](docs/domain/metadata.md).

## Frontend Architecture

Uses the **Bulletproof React** pattern. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for details.

- **Per-feature encapsulation**: Place components, stores, and utilities under `features/` per functional domain (see `frontend/src/features/` for the current list).
- **New functionality goes in a feature**: When adding a new domain feature, create a feature directory under `features/` and follow the Bulletproof pattern. Stores and forms also live inside the feature.
- **Barrel exports**: Each feature's `index.ts` defines the public API. External code imports only via `@/features/xxx`.
- **No internal references**: Biome's `noRestrictedImports` makes direct references to `@/features/*/*` an error.
- **Placement rule**: Modules used by only one feature live inside that feature; modules shared across multiple features live in `hooks/`, `lib/`, or `stores/`.
- **Keep individual files small**: Small UI components inside a feature go in `features/xxx/ui/`. Once shared across multiple features, promote them to `components/ui/`.
- **API types are orval-generated**: Never define API request/response types manually — import them directly from `@/api/generated/schemas` (no re-export from `use-api.ts`; use generated names as-is, alias only on name collision). After backend schema changes, run `make generate` (CI fails if the committed `frontend/openapi.json` drifts from the code). See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the generation pipeline.

## Testing

→ Details (test structure, `pragma: no cover` policy, environment constraints): the "Testing" section of [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md#testing)

- **Maintain 100% coverage** — verify with `make test-cov`. Tests run on the host (no Docker or rclpy needed).

## Coding Style

- **Comments describe the code's responsibility and current constraints, not its history** (notes like "this used to be ...", "this was duplicated so we abstracted it", etc. belong in the commit message / PR description). See [docs/CODING_STYLE.md](docs/CODING_STYLE.md) for details.
- Python: Method order is `__init__` → public → private (newspaper style).
- Python: The order of public methods matches the order of the corresponding API endpoints.
- Python: `schemas.py` contains only API request/response schemas. Domain models with business logic belong in `models.py`.
- Python: pydantic response models **must not have default values**; nullable fields are `field: int | None` (no default; required and nullable). See [docs/CODING_STYLE.md](docs/CODING_STYLE.md#python) for the OpenAPI/orval rationale.
- Frontend: Inside a route/component, order hooks and variables by the standard sections (Routing → Server state → Streaming / subscription → Side effects → Event handlers → Render-only state) with single-line `// --- XX ---` dividers. See [docs/CODING_STYLE.md](docs/CODING_STYLE.md#hook--variable-ordering-in-routes-and-components) for the section definitions — update them there.
- **Frontend: Inline single-use short descriptive variables and event handlers into the JSX**, and use a ternary to "branch inside the argument" when only the argument differs. See [docs/CODING_STYLE.md](docs/CODING_STYLE.md#inlining-policy-typescript--react) for details and exceptions.
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
