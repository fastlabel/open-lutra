# LeRobot Export

Converts selected recordings into a [LeRobot v3.0](https://huggingface.co/docs/lerobot/en/lerobot-dataset-v3) dataset (`backend/app/features/lerobot_export/`).

## Design

- **Self-implemented v3.0 writer**: parquet via `pyarrow`/`pandas` + per-camera H.264 MP4 via ffmpeg, **without** depending on the heavyweight `lerobot`/torch package.
- **One recording = one episode**: selecting N recordings yields an N-episode dataset.

## Mapping configuration

The topic → `observation.*` / `action` / image mapping is declared in the active recording config's `lerobot_export:` section (`config/<recording>.yaml`, selected via `RECORDING_CONFIG`) — not in a separate file — so a recording's config and its export layout stay together. Every option is documented inline in the `lerobot_export` section of [config/simulator.yaml](../../config/simulator.yaml).

Each source declares its value explicitly via a dot-separated `field` path plus a `type`:

| `type` | Meaning | Extra keys |
|---|---|---|
| `list` | Numeric sequence | `indices` required |
| `number` | Scalar wrapped as a 1-element array | — |
| `struct` | Named-field object like `geometry_msgs/Point` | `keys` required |

There is no implicit auto-detection of message structure, so the YAML fully records the conversion that was applied and stays reproducible (`backend/app/features/lerobot_export/extract.py:extract_field_data`).

## Validation before export

Each selected recording's `metadata.yaml` is validated against the mapping; recordings missing a mapped topic are rejected before the job starts.

## Execution and output

- The export runs as a `JobType.LEROBOT_EXPORT` job on the JobQueue.
- Output goes to `<output_dir>/_lerobot_exports/<name>/`. The `recordings` scanner skips the reserved `_lerobot_exports` directory, so exports never appear as recordings.

## Download

A completed export can be pulled to the browser as a single zip via `GET /api/lerobot/exports/<name>/download`, surfaced as a Download button in the export dialog's completion view. The dataset tree is zipped on demand with `ZIP_STORED`, since its contents — H.264 MP4 + parquet — are already compressed.
