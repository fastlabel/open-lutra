# Changelog

All notable changes to OpenLUTRA are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
While the major version is `0`, minor releases may include breaking changes.

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

[0.1.0]: https://github.com/fastlabel/open-lutra/releases/tag/v0.1.0
