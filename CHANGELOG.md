# Changelog

All notable changes to OpenLUTRA are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
While the major version is `0`, minor releases may include breaking changes.

## [0.2.0] - 2026-06-19

This release adds two major capabilities — uploading recordings to an external
storage destination and exporting them to the LeRobot dataset format — alongside
validation and configuration improvements.

> **Beta release.** APIs, data formats, configuration, and the web UI may
> change without notice until v1.0.0. Docker images are not published at this
> stage; the project is distributed as source.

### Added

- Upload a recording's archive to a storage destination — Amazon S3 (or any
  S3-compatible endpoint such as MinIO / Cloudflare R2) or a local-network
  filesystem directory — one at a time or in bulk from the recordings list. The
  destination is pluggable and selected per machine via `UPLOAD_DESTINATION`;
  the feature stays disabled until configured. See
  [docs/domain/upload.md](docs/domain/upload.md) and the
  [S3](docs/SETUP.md#s3-upload-optional) and
  [local-network](docs/SETUP.md#local-network-upload-optional) setup guides.
- Export selected recordings to the
  [LeRobot v3.0](https://huggingface.co/docs/lerobot/en/lerobot-dataset-v3)
  dataset format (parquet + per-camera H.264 MP4) and download the result as a
  zip from the browser. Topic mapping is declared in the active recording
  config; see the `lerobot_export` section in
  [config/simulator.yaml](config/simulator.yaml).
- Built-in validator parameters can be configured from the robot YAML config.
  See [docs/domain/custom_validators.md](docs/domain/custom_validators.md).
- Validation result details are shown as a formatted, collapsible JSON
  accordion on the recording detail page.

### Changed

- `ROBOT_CONFIG` and `OUTPUT_DIR` are now required in `.env`; the backend fails
  fast when they are unset. See [docs/SETUP.md](docs/SETUP.md).
- Task-name validation errors are surfaced inline in the recording header editor.
- Polished the recording page layout (relocated the Stop toggle, made the
  monitor pane minimizable, surfaced Hz in the narrow sidebar).
- Bumped backend and frontend dependencies.

### Fixed

- Removed an unreadable hover tooltip from the monitor LOSS RATE chart.

## [0.1.0] - 2026-05-28

Initial public release of OpenLUTRA — a ROS2 data-recording system for robot
teaching and teleoperation workflows.

> **Beta release.** APIs, data formats, configuration, and the web UI may
> change without notice until v1.0.0. Docker images are not published at this
> stage; the project is distributed as source.

### Added

- One-click recording from the web UI, persisted as MCAP files.
- Live per-topic monitoring (Hz, miss rate, gap detection) over Server-Sent
  Events.
- Automatic post-recording quality analysis with per-topic loss detection and
  continuity scoring.
- Pluggable per-recording validators with a `@register_validator` extension
  point. See [docs/domain/custom_validators.md](docs/domain/custom_validators.md).
- On-demand MCAP → MP4 preview for recorded camera topics.
- Recordings browser with search, filter, per-topic timeline heatmap, and
  video / joint previews.
- YAML-based recording configuration switchable via the `RECORDING_CONFIG`
  environment variable.
- Docker Compose-based dev environment with a built-in simulator (`make up`)
  and a host-network production profile (`make prod-up`).
- Reference snippets in [`examples/`](./examples/), including how to plug in
  custom ROS2 message packages.

See [README.md](./README.md) and [docs/](./docs/) for architecture, setup,
and development guides.

### Licensing

- Repository root: [Apache License 2.0](./LICENSE).
- `/examples`: [BSD Zero Clause License (0BSD)](./examples/LICENSE).
- Third-party attributions are listed in [NOTICE](./NOTICE).
- Trademark policy: [TRADEMARKS.md](./TRADEMARKS.md).
- Security reporting: [SECURITY.md](./SECURITY.md).

### Project status

- External pull requests are not accepted at this stage; issues are welcome.
  See [CONTRIBUTING.md](./CONTRIBUTING.md).
- During the `0.y.z` phase, only the latest `main` is eligible for security
  fixes.

[0.2.0]: https://github.com/fastlabel/open-lutra/releases/tag/v0.2.0
[0.1.0]: https://github.com/fastlabel/open-lutra/releases/tag/v0.1.0
