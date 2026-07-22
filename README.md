<!-- TBD: project logo / hero banner image -->

# OpenLUTRA

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](./LICENSE)
[![Version](https://img.shields.io/badge/version-0.2.0-orange.svg)](#release-status)
[![Status: Beta](https://img.shields.io/badge/status-beta-yellow.svg)](#release-status)
[![CI](https://github.com/fastlabel/open-lutra/actions/workflows/ci.yml/badge.svg)](https://github.com/fastlabel/open-lutra/actions/workflows/ci.yml)

**A ROS2 data-recording system for robot teaching — record topics from ROS2-compatible robots and persist them as MCAP, all driven from a web UI.**

> **Release status — pre-1.0 (v0.2.0, beta).** APIs, data formats, and the CLI/UI may change without notice. Pin a specific version for any production use.

[Quickstart](#quickstart) · [Documentation](#documentation) · [Issues](https://github.com/fastlabel/open-lutra/issues) · [Security](./SECURITY.md)

<!-- TBD: hero screenshot or short demo GIF (recording page in action) -->

---

## Overview

OpenLUTRA records ROS2 topics from ROS2-compatible robots and persists them as MCAP files, with a web UI for starting/stopping recordings, monitoring live topic quality, and reviewing recorded data. It targets robot teaching and teleoperation workflows where reliable, observable data collection matters.

```
Robot  ──ROS2 Topics──▶  FastAPI
  /robot_slave/states (100Hz)     ├── subprocess: ros2 bag record → MCAP
  /robot_master/cmd (100Hz)       ├── rclpy: frequency monitor + gap detection
  /*_depth_cam/.../compressed     └── SSE: real-time stream → Web UI
```

A hybrid architecture is used:

| Function | Technology | Reason |
|---|---|---|
| Recording | `subprocess` (`ros2 bag record`) | Memory isolation; safe for long sessions |
| Monitoring | `rclpy` (lightweight) | Real-time alerts; keeps only the latest N messages |
| Quality analysis | `mcap` Python library | Accurate post-hoc metrics |

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for details.

## Features

- **One-click recording** from a web UI — start/stop `ros2 bag record -s mcap` without touching a terminal.
- **Live topic monitoring** — per-topic Hz, miss rate, and gap detection over SSE.
- **MCAP-first storage** — explicit `-s mcap` (not the default sqlite3); no Python-side buffering for memory safety.
- **Automatic quality analysis** — IQR-based loss detection (`Q3 + 1.5×IQR`), per-topic status, persistent quality reports.
- **Recording browser** — search, filter, and inspect recordings; per-topic timeline heatmap, loss events, and video/joint previews.
- **MCAP → MP4 preview** — per-camera MP4s generated on demand from MCAP, streamed frame-by-frame through ffmpeg.
- **Pluggable validation** — built-in validators plus a `@register_validator` extension point for custom per-recording rules. See [docs/domain/custom_validators.md](docs/domain/custom_validators.md).
- **Recording config as YAML** — topics, expected Hz, validators, pre-registered metadata fields, and `ROS_DOMAIN_ID` switched via the `RECORDING_CONFIG` environment variable.

<!-- TBD: short feature screenshots (recording page, recordings list, MCAP detail view) -->

## Quickstart

### Development (with simulator)

```bash
make setup   # one-time: install dependencies + copy .env
make up      # start dev environment (simulator + backend + frontend)
```

| Service     | URL                              |
|-------------|----------------------------------|
| Frontend    | http://localhost:5173            |
| Backend API | http://localhost:8000            |
| API docs    | http://localhost:8000/docs       |

### Production (Ubuntu + real robot)

```bash
cp .env.example .env   # set ROS_DOMAIN_ID to match your robot
make prod-up           # production start (network_mode: host)
```

See [docs/SETUP.md](docs/SETUP.md) for prerequisites, environment variables, and deployment notes.

### Common make targets

| Command          | Description                              |
|------------------|------------------------------------------|
| `make up`        | Start dev environment (with simulator)   |
| `make down`      | Stop                                     |
| `make build`     | Build Docker images                      |
| `make prod-up`   | Production start (host network)          |
| `make prod-down` | Production stop                          |

See the [Makefile](./Makefile) for the full list (lint, test, format, generate, etc.).

## Demo

<img width="1512" height="824" alt="Recording page" src="https://github.com/user-attachments/assets/be6df6f6-38f3-4ee6-b05c-8e6051abdc0e" />
<img width="1512" height="825" alt="Recording data detail page" src="https://github.com/user-attachments/assets/271795fa-7e7a-4d48-8968-d2bc8c012bdd" />

 See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full data flow.

### Task name

Set the task name (for example `pick-and-place`) from the inline editor in the header. The task name becomes the prefix of the recording directory (`{task}_{timestamp}`). If left unset, the recording directory is the timestamp alone.

### Pre-registered metadata

Attach fixed attributes — operator ID, target object, and so on — to each recording by choosing them once from the **Metadata** panel in the recording bar. Like the task name, the selection sticks across recordings until changed. The available fields are defined in the recording config's `metadata_fields:` section. See [docs/domain/metadata.md](docs/domain/metadata.md).

### Recording workflow

1. **Select topics** — check the topics you want to record in the left panel (ROS2 topics are auto-discovered).
2. **Start recording** — press the record button.
3. **Monitor live** — watch per-topic Hz and miss% in the left panel; the bottom Missing Rate graph shows the time series.
4. **Stop recording** — press the record button again. Quality analysis runs automatically.
5. **Review** — open the recordings page or the MCAP detail page to inspect per-topic metrics (loss rate, continuity score).

## Documentation

| Document | Contents |
|---|---|
| [docs/TECH_STACK.md](docs/TECH_STACK.md) | Tech stack (versions, tooling) |
| [docs/STRUCTURE.md](docs/STRUCTURE.md) | Directory layout (backend / frontend / tests) |
| [docs/SETUP.md](docs/SETUP.md) | Setup guide (prerequisites, dev, prod, env vars) |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Architecture (system, data flow, Docker) |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | Development guide (style, branching, tests) |
| [docs/domain/](docs/domain/index.md) | Domain notes (ROS2, MCAP, LeRobot, quality analysis) |
| [examples/](examples/) | Reference snippets (e.g. plugging in custom ROS2 message types) |

## Release status

OpenLUTRA is currently **v0.2.0 (beta)** and follows the [SemVer](https://semver.org/) `0.y.z` convention: minor versions may include breaking changes until v1.0.0. Only the latest `main` is eligible for security fixes (see [SECURITY.md](./SECURITY.md)).

Docker images are **not** published at this stage; the project is distributed as source.

## Roadmap

Nothing on this list is committed — these are directions we are currently exploring.

- **Richer validation and quality analysis** — expand the set of built-in validators and quality metrics, and surface more actionable diagnostics in the UI.
- **Recording labeling** — attach labels, tags, and review status to recordings to organize datasets for downstream training.
- **Seamless storage integrations** — first-class support for shipping recorded files to various storage backends (object stores, dataset platforms, etc.).
- **etc.** — feedback via [issues](https://github.com/fastlabel/open-lutra/issues) is welcome.

## Support

- File an issue at <https://github.com/fastlabel/open-lutra/issues>. Bug reports, feature requests, and questions are welcome in English or Japanese.
- For security reports, see [SECURITY.md](./SECURITY.md) — please do not open a public issue.

## Contributing

External pull requests are **not accepted at this stage**. Issues are welcome — see [CONTRIBUTING.md](./CONTRIBUTING.md).

<!-- TBD: add CODE_OF_CONDUCT.md (e.g. Contributor Covenant) and link here before opening external contributions. -->
<!-- TBD: add GOVERNANCE.md describing the maintainer / decision-making model before opening external contributions. -->

## License

- Repository root: [Apache License 2.0](./LICENSE)
- `/examples` directory: [BSD Zero Clause License (0BSD)](./examples/LICENSE)

See [NOTICE](./NOTICE) for required attributions, including third-party components redistributed under their original licenses.

## Trademarks

See [TRADEMARKS.md](./TRADEMARKS.md) for the policy on use of the "OpenLUTRA" and "FastLabel" names and logos.

## Acknowledgments

OpenLUTRA builds on the work of many upstream projects, including [ROS2](https://docs.ros.org/), the [MCAP](https://mcap.dev/) format, [FastAPI](https://fastapi.tiangolo.com/), and [React](https://react.dev/).

---

Maintained by [FastLabel, Inc.](https://fastlabel.ai)
