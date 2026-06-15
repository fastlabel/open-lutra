# Upload to a Destination

> How recordings are shipped from the recording machine to a configured
> upload destination (S3-compatible and local-network filesystem today;
> GCS on the roadmap).
>
> Related: [Setup — S3 Upload](../SETUP.md#s3-upload-optional) | [Setup — Local-Network Upload](../SETUP.md#local-network-upload-optional) | [Architecture](../ARCHITECTURE.md)

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
- Generic over the destination — S3 (via boto3) and a local-network
  filesystem (via `shutil.copyfile` against a bind-mounted directory)
  today; further destinations (GCS) plug in via the `UploadDestination`
  protocol without touching the service / job queue layers.

What is **not** in scope (out by design, per [issue #6](https://github.com/fastlabel/open-lutra/issues/6)):

- Multi-destination uploads. Exactly one destination is active per
  machine.
- Auto-upload after recording stops. Upload is always user-initiated.
- Resumable retry beyond what boto3's `TransferManager` already does.
- Download / restore from the destination.

Out of scope for the initial drop but on the near-term roadmap (no
design baked in yet — both decisions sit with whoever picks them up):

- **Bulk upload from the recordings list page.** Mounted next to
  `<BulkDeleteButton />` in `recordings-table.tsx`; reads the selected
  set from `useRecordingsStore.checkedFolders`. The JobQueue is
  single-worker with per-folder dedup, so either implementation shape
  (N `POST /api/upload/start` calls from the frontend, or one new
  endpoint that enqueues `N` jobs server-side) ends up serialized the
  same way — pick whichever fits the rest of the UI's mutation
  patterns better.
- **Further destinations** (GCS, …). See "The destination abstraction"
  below for the extension recipe.

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
  local.py       LocalDestination (shutil.copyfile to a bind-mounted directory)
```

The job runner only sees:

```python
class UploadDestination(Protocol):
    name: str
    def configuration_error(self) -> str | None: ...
    def prepare_target(self, recording_name, recording_start_ns) -> tuple[str, str]: ...
    def upload(self, local_path, key, progress) -> UploadResult: ...
```

`prepare_target` returns `(destination_label, key)` — bucket + object
key for S3, mount-dir path + relative path for local. `configuration_error`
owns every check that must pass before an upload can be enqueued (env
vars set, key/path template parses, etc.); the service layer never names
destination-specific fields.

Adding a backend (e.g. GCS) is a small, well-bounded change:

1. **Implement the destination.** New module under `destinations/`
   (e.g. `destinations/gcs.py`) with a class that fulfils the
   `UploadDestination` Protocol. Set `name = "gcs"` on the class —
   it is read by diagnostics and by selection logic.
2. **Add settings.** Whatever env vars the backend needs (host /
   credentials / path prefix) go on `Settings` in
   `backend/app/settings.py`. Follow the existing pattern:
   `str | None = None` for optional fields, no defaults on values
   the operator must supply.
3. **Extend the destination selector.** Widen `UPLOAD_DESTINATION` on
   `Settings` (today `Literal["s3", "local"]`) to include the new
   value, and add a branch in `get_active_destination(settings)` in
   `destinations/registry.py`.
4. **Cover every precondition in `configuration_error()`.** Validate
   env vars, the path / key template (use
   `app.features.upload.key_template.validate_template` if you reuse
   the standard placeholders), and any other start-time checks. Avoid
   probing the network — `configuration_error()` runs on every
   `/api/upload/start` and on `/api/config`, so it must not block.
5. **Mirror the tests.** Drop a sibling test file under
   `backend/tests/features/upload/destinations/` named after the
   destination (e.g. `test_gcs.py`), following `test_s3.py` /
   `test_local.py` for the test-class layout (`TestConfigurationError`,
   `TestPrepareTarget`, `TestUpload`, plus any private-helper tests).
   100% coverage on the new module is expected — see
   `docs/DEVELOPMENT.md` for the coverage gate.
6. **Update operator-facing docs.** Add an env-var table for the new
   destination to `docs/SETUP.md` (mirror the S3 / Local-Network Upload
   sections) so the operator knows what to set.

The service layer, the job queue, the UI, and the persisted
`upload_state.json` are all destination-agnostic — `state.destination`
holds a bucket / mount-dir / host string and `state.key` holds the
object path within it.

## Key template

The destination key is computed at upload time by rendering the
destination's template (`S3_KEY_TEMPLATE` for S3,
`LOCAL_UPLOAD_PATH_TEMPLATE` for local) with these placeholders:

| Placeholder | Source | Example |
|---|---|---|
| `{recording_name}` | the recording folder name | `rec_20260525_120000` |
| `{yyyymmddhhmmss}` | recording start time, derived from `metadata.yaml`'s `starting_time.nanoseconds_since_epoch` (UTC) | `20260525120000` |

```env
S3_KEY_TEMPLATE=lutra-recordings/operation-files/{yyyymmddhhmmss}/{recording_name}.zip
LOCAL_UPLOAD_PATH_TEMPLATE=operation-files/{yyyymmddhhmmss}/{recording_name}.zip
```

`task_name` is **deliberately not a placeholder.** Task names are
user-editable and may contain spaces or other characters that would
require percent-encoding in an S3 key or filesystem-path quoting;
keeping them out of the key keeps the convention "the key is composed
of immutable identifiers only". `task_name` is still recorded in
`recording_meta.json` inside the zip, so it travels with the upload —
it just does not appear in the destination key.

`validate_template` rejects unknown placeholders and unbalanced braces
at start-time (so the operator sees the error in the UploadResponse
rather than discovering it after a long zip). Each destination calls
the validator from inside its own `configuration_error()`.

## Failure modes

Every failure is recorded on `upload_state.json` and surfaced through
`GET /api/upload` + the UploadBadge + the UploadButton's inline error
message. The sources of a `status="failed"` response are:

| Source | Where it is raised | What the user sees |
|---|---|---|
| `S3_BUCKET` / `S3_KEY_TEMPLATE` not set | `S3Destination.configuration_error()` (start-path early-reject) | "S3_BUCKET is not configured" (UI: red badge) |
| `LOCAL_UPLOAD_DIR` not set / missing / not writable | `LocalDestination.configuration_error()` (start-path early-reject) | "LOCAL_UPLOAD_DIR is not configured" / "LOCAL_UPLOAD_DIR does not exist: …" / "LOCAL_UPLOAD_DIR is not writable: …" |
| Invalid template syntax | `validate_template` via `configuration_error()` (start-path early-reject) | "Unknown placeholder: …" / "Unbalanced braces: …" |
| Recording missing `metadata.yaml` start time | `_run_upload` (job worker) | "Cannot determine recording start time from metadata.yaml: …" |
| Network / S3 SDK error | `S3Destination.upload()` raises through `_run_upload` | The boto3 error message verbatim (e.g. `EndpointConnectionError`, `NoSuchBucket`) |
| Local-filesystem error (mount unresponsive, disk full, permission denied) | `LocalDestination.upload()` raises through `_run_upload` | The OS error message verbatim (e.g. `OSError: No space left on device`, `PermissionError`) |

Start-path early-rejects do not enqueue a job and do not write
`upload_state.json` — the failure is only carried in the
`UploadResponse`. The runtime-side failures (the last three rows above)
always leave a `failed` state file behind, so a refresh still shows the
error and the user can hit "Retry upload" without losing context.

> `LocalDestination.configuration_error()` deliberately does not probe
> the share for network responsiveness — that check runs on every
> `/api/upload/start` and on `/api/config`, so blocking on a stuck NFS
> mount would freeze the UI. An unresponsive mount surfaces as an
> exception on the actual `shutil.copyfile` call instead.

## UI integration

| Where | Component | Behavior |
|---|---|---|
| Recording-detail header (`recordings_/$folder.tsx`) | `UploadButton` | Stateful label: `Upload` / `Uploading N%` / `Re-upload` / `Retry upload`. Click fires `POST /api/upload/start`. Inline error shown next to the button when `status="failed"`. |
| Recording-list row (`recording-list-item.tsx`) | `UploadBadge` | Inline icon: cloud-check (uploaded), spinner + percent (uploading), cloud-off (failed), empty slot (no state). Reads `FileEntry.upload_status` for persistence + the SSE job stream for live percent — no per-row HTTP. |

Both components return `null` when `useConfig().upload_enabled === false`,
so a machine with no destination configured renders no upload affordances
at all.

`upload_enabled` is true exactly when the active destination's
`configuration_error()` returns `None` — every precondition (env vars,
template parses, directory exists / is writable, etc.) lives inside
that method. That keeps the UI from showing a button that would always
immediately fail.

## Operator setup

See [Setup — S3 Upload](../SETUP.md#s3-upload-optional) for the S3
environment variables (env-var-auth vs. profile-auth, TransferConfig
overrides), [Setup — Local Testing with MinIO](../SETUP.md#local-testing-with-minio)
for spinning up the local MinIO sandbox, and
[Setup — Local-Network Upload](../SETUP.md#local-network-upload-optional)
for the NFS / SMB bind-mount recipe.
