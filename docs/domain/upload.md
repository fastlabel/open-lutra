# Upload to a Destination

> How recordings are shipped from the recording machine to a configured
> upload destination (S3-compatible today; GCS / local-network destinations
> on the roadmap).
>
> Related: [Setup — S3 Upload](../SETUP.md#s3-upload-optional) | [Architecture](../ARCHITECTURE.md)

## Scope

After a recording stops, the MCAP file and its sidecar JSONs
(`quality_report.json`, `validation_result.json`, `recording_meta.json`)
sit on the recording machine's disk. The upload feature gives the
operator a one-click path to ship that bundle to an external storage
backend, where a downstream pipeline can pick it up for conversion /
annotation.

What is in scope:

- Zip the recording folder and upload the archive as a single object.
- Persist a per-recording state file so reloads survive a refresh / a
  page navigation.
- Stream byte-level progress over SSE while the upload runs.
- Generic over the destination — S3 today via boto3, with an extension
  point (`UploadDestination` protocol) so GCS / a local-network server
  can be added later without touching the service / job queue layers.

What is **not** in scope (out by design, per [issue #6](https://github.com/fastlabel/open-lutra/issues/6)):

- Multi-destination uploads. Exactly one destination is active per
  machine.
- Auto-upload after recording stops. Upload is always user-initiated.
- Resumable retry beyond what boto3's `TransferManager` already does.
- Download / restore from the destination.
- Bulk-upload across multiple recordings from the list page.

## Lifecycle

```
User clicks "Upload"
  │
  └─► POST /api/upload/start
        ├─ early-reject: destination misconfigured or template invalid
        │   ► UploadResponse(status="failed", error="…")
        └─ otherwise enqueue an UploadJob
              │
              └─► JobQueue worker picks up the job
                    ├─ Read recording_start_ns from metadata.yaml
                    ├─ Render destination key from S3_KEY_TEMPLATE
                    ├─ Build / refresh <folder>/<folder>.zip
                    ├─ Persist upload_state.json (status="uploading")
                    ├─ destination.upload(zip, key, progress_cb)
                    │     ├─ progress_cb emits SSE at most once per 1 s
                    │     └─ progress_cb persists bytes_transferred to
                    │        upload_state.json (throttled)
                    ├─ on success:  upload_state.json status="uploaded"
                    │               etag + uploaded_at + size_bytes
                    └─ on exception: upload_state.json status="failed"
                                     error=str(e) ; re-raised so the
                                     JobQueue marks the job FAILED
```

`upload_state.json.status` is the source of truth between sessions; the
SSE job stream is the source of truth for the *live* percent while a
job is in flight. The frontend's `useUploadStatus(folderPath)` fuses
both and falls back to the persisted state when no job is active.

### Re-clicking after a successful upload

Per issue #6 the start path **always overwrites**: there is no
skip-if-cached short-circuit. Re-clicking the button enqueues another
upload that writes the same key with a new ETag. The dedup guard
(`enqueue_upload` returns the existing job if one is already running)
prevents two simultaneous uploads of the same folder, not re-uploads
across time.

## The destination abstraction

```
app/features/upload/destinations/
  base.py        UploadDestination Protocol + UploadResult + ProgressCallback
  registry.py    get_active_destination(settings) → single active instance
  s3.py          S3Destination (boto3 + any S3-compatible endpoint)
```

The job runner only sees:

```python
class UploadDestination(Protocol):
    name: str
    def configuration_error(self) -> str | None: ...
    def upload(self, local_path, key, progress) -> UploadResult: ...
```

Adding a backend (e.g. GCS) is then a single new module + a registry
update:

1. Implement `GCSDestination` in `destinations/gcs.py`.
2. Extend `get_active_destination()` to switch on a future
   `UPLOAD_DESTINATION` setting and return the new instance.
3. Add the relevant `GCS_*` env vars to `Settings`.

The service layer, the job queue, the UI, and the persisted
`upload_state.json` are all destination-agnostic — `state.destination`
holds a bucket / container / host string and `state.key` holds the
object path within it.

## Key template

The destination key is computed at upload time by rendering
`S3_KEY_TEMPLATE` with these placeholders:

| Placeholder | Source | Example |
|---|---|---|
| `{recording_name}` | the recording folder name | `rec_20260525_120000` |
| `{yyyymmddhhmmss}` | recording start time, derived from `metadata.yaml`'s `starting_time.nanoseconds_since_epoch` (UTC) | `20260525120000` |

```env
S3_KEY_TEMPLATE=lutra-recordings/operation-files/{yyyymmddhhmmss}/{recording_name}.zip
```

`task_name` is **deliberately not a placeholder.** Task names are
user-editable and may contain spaces or other characters that would
require percent-encoding in an S3 key; keeping them out of the key
keeps the convention "the key is composed of immutable identifiers
only". `task_name` is still recorded in `recording_meta.json` inside
the zip, so it travels with the upload — it just does not appear in
the destination key.

`validate_template` rejects unknown placeholders and unbalanced braces
at start-time (so the operator sees the error in the UploadResponse
rather than discovering it after a long zip).

## Failure modes

Every failure is recorded on `upload_state.json` and surfaced through
`GET /api/upload` + the UploadBadge + the UploadButton's inline error
message. The four sources of a `status="failed"` response are:

| Source | Where it is raised | What the user sees |
|---|---|---|
| `S3_BUCKET` / `S3_KEY_TEMPLATE` not set | `S3Destination.configuration_error()` (start-path early-reject) | "S3_BUCKET is not configured" (UI: red badge) |
| Invalid template syntax | `validate_template` (start-path early-reject) | "Unknown placeholder: …" |
| Recording missing `metadata.yaml` start time | `_run_upload` (job worker) | "Cannot determine recording start time from metadata.yaml: …" |
| Network / S3 SDK error | `destination.upload()` raises through `_run_upload` | The boto3 error message verbatim (e.g. `EndpointConnectionError`, `NoSuchBucket`) |

Start-path early-rejects do not enqueue a job and do not write
`upload_state.json` — the failure is only carried in the
`UploadResponse`. The runtime-side failures (the last two rows above)
always leave a `failed` state file behind, so a refresh still shows the
error and the user can hit "Retry upload" without losing context.

## UI integration

| Where | Component | Behavior |
|---|---|---|
| Recording-detail header (`recordings_/$folder.tsx`) | `UploadButton` | Stateful label: `Upload` / `Uploading N%` / `Re-upload` / `Retry upload`. Click fires `POST /api/upload/start`. Inline error shown next to the button when `status="failed"`. |
| Recording-list row (`recording-list-item.tsx`) | `UploadBadge` | Inline icon: cloud-check (uploaded), spinner + percent (uploading), cloud-off (failed), empty slot (no state). Reads `FileEntry.upload_status` for persistence + the SSE job stream for live percent — no per-row HTTP. |

Both components return `null` when `useConfig().upload_enabled === false`,
so a machine with no destination configured renders no upload affordances
at all.

`upload_enabled` is true only when both checks pass: the destination's
`configuration_error()` returns `None` **and** `validate_template`
succeeds on the configured `S3_KEY_TEMPLATE`. That keeps the UI from
showing a button that would always immediately fail.

## Operator setup

See [Setup — S3 Upload](../SETUP.md#s3-upload-optional) for the
environment variables (env-var-auth vs. profile-auth, TransferConfig
overrides) and [Setup — Local Testing with MinIO](../SETUP.md#local-testing-with-minio)
for spinning up the local MinIO sandbox.
