# Custom Validators

> How to add a custom validation rule that runs against every recording.
>
> Related: [Quality analysis](quality_analysis.md) | [Architecture](../ARCHITECTURE.md)

## When to write one

OpenLUTRA ships with a small set of **builtin validators** (currently
`required_topics_present`, `total_duration_sec`) that cover the most common
shape checks for an ML teaching recording. When you need something
project-specific — "the right arm must publish at least 1000 messages",
"the gripper topic must not stay in the open state for more than 80% of
the recording", "the head camera's average frame size must exceed 50 KB",
"joint 0 must not drift more than 0.01 rad over the recording" — add a
**custom validator**. The validator receives the full `QualityReport`
plus the MCAP file path, so checks that need raw frames are supported
in addition to checks over the aggregated metrics.

Builtin validators live in `backend/app/features/validation/builtins/` and are
considered part of the OSS surface. Custom validators live alongside in
`backend/app/features/validation/custom/` and are intended for downstream forks
or per-deployment rules that do not need to be upstreamed.

## How validators run

```
Recording stop
   └─► Quality analysis job (quality_report.json)
         └─► Validation job
               ├─ Load quality_report.json + recording_meta.json
               ├─ Locate the MCAP file in the recording folder
               ├─ Build a ValidationContext (report + paths + meta)
               ├─ Run every builtin validator (active_set.py)
               ├─ Run every custom validator (registry)
               ├─ Catch unexpected exceptions → status="error"
               └─► Persist validation_result.json
```

Two things follow from this pipeline:

1. **Validators receive a `ValidationContext`**. The context bundles the
   already-computed `QualityReport`, the MCAP file path, the recording
   directory, and the parsed `recording_meta.json`. Light-weight
   validators read only `ctx.report`; validators that need raw frames
   open the MCAP via `ctx.mcap_path`.
2. **Validators run after every recording, automatically**. The same job
   queue that drives quality analysis also enqueues a validation job on
   completion. There is no separate trigger to wire up.

The result of every run is appended to `validation_result.json` in the
recording folder and exposed through `GET /api/validation` (used by the
detail page) and `FileEntry.validation_overall_status` (used by the row
badge in the recordings list).

## Writing a validator

### 1. Create a `.py` file under `backend/app/features/validation/custom/`

Pick any filename — the loader walks the directory and imports every
non-underscore-prefixed module.

### 2. Subclass `RecordingValidator` and decorate with `@register_validator`

```python
# backend/app/features/validation/custom/right_arm_message_count.py
from typing import ClassVar

from app.features.validation import (
    RecordingValidator,
    ValidationContext,
    ValidationResult,
    register_validator,
)


@register_validator
class RightArmMessageCount(RecordingValidator):
    """Right-arm topic must publish at least 1000 messages."""

    name: ClassVar[str] = "right_arm_message_count"

    def validate(self, ctx: ValidationContext) -> ValidationResult:
        right_arm = next(
            (t for t in ctx.report.topics if t.name == "/mcap/slave_arm_right"),
            None,
        )
        if right_arm is None:
            return ValidationResult(
                status="fail",
                message="Right-arm topic was not recorded",
            )
        if right_arm.message_count < 1000:
            return ValidationResult(
                status="warn",
                message=(
                    f"Right-arm has only {right_arm.message_count} messages "
                    "(expected ≥ 1000)"
                ),
                details={"message_count": right_arm.message_count},
            )
        return ValidationResult(status="pass", message="OK")
```

### Reading MCAP frames

When a check needs more than the per-topic aggregates in `QualityReport`
— e.g. inspecting individual joint positions, image headers, or message
payloads — open the MCAP file with `MCAPReader` via `ctx.mcap_path`:

```python
# backend/app/features/validation/custom/joint_zero_drift.py
from typing import ClassVar

from app.features.validation import (
    RecordingValidator,
    ValidationContext,
    ValidationResult,
    register_validator,
)
from app.infra.mcap import MCAPReader, extract_joint_positions


@register_validator
class JointZeroDrift(RecordingValidator):
    """Right-arm joint 0 must end within ±0.01 rad of where it started."""

    name: ClassVar[str] = "joint_zero_drift"

    def validate(self, ctx: ValidationContext) -> ValidationResult:
        if ctx.mcap_path is None:
            return ValidationResult(status="fail", message="MCAP file not found")

        first: float | None = None
        last: float | None = None
        with MCAPReader(ctx.mcap_path) as reader:
            for msg in reader.iter_messages(topics=["/mcap/slave_arm_right"]):
                positions = extract_joint_positions(msg.decoded)
                if not positions:
                    continue
                if first is None:
                    first = positions[0]
                last = positions[0]

        if first is None or last is None:
            return ValidationResult(status="fail", message="No joint frames")

        drift = abs(last - first)
        if drift > 0.01:
            return ValidationResult(
                status="warn",
                message=f"Joint 0 drifted {drift:.4f} rad",
                details={"drift_rad": drift},
            )
        return ValidationResult(status="pass", message=f"Drift {drift:.4f} rad")
```

### 3. Restart the app

```bash
make down && make up
```

The startup hook in `backend/app/main.py` calls `load_custom_validators()`,
which imports every module under the `custom/` package and runs the
`@register_validator` decorators. The next recording (or the next time
`POST /api/validation/analyze` is called) will include your validator.

## API surface

### `RecordingValidator`

```python
class RecordingValidator(ABC):
    name: ClassVar[str]

    @abstractmethod
    def validate(self, ctx: ValidationContext) -> ValidationResult: ...
```

- `name` is the stable identifier shown in the UI and stored in
  `validation_result.json`. It must be unique across all builtin and
  custom validators in the running app — a duplicate triggers a
  WARNING log on startup but does not crash.
- `validate(ctx)` is called once per recording. See `ValidationContext`
  below for what the context exposes.

### `ValidationContext`

```python
@dataclass(frozen=True)
class ValidationContext:
    report: QualityReport
    recording_dir: Path
    mcap_path: Path | None
    recording_meta: RecordingMeta | None
```

| Field | Description |
|-------|-------------|
| `report` | Full `QualityReport` (`backend/app/features/analysis/models.py`). Per-topic name, msg_type, message_count, measured Hz, loss events, size stats |
| `recording_dir` | The recording folder. Use it to read sibling artifacts when needed |
| `mcap_path` | Path to the recording's `.mcap` file. `None` if the file was deleted before validation ran. Open with `MCAPReader` from `app.infra.mcap` |
| `recording_meta` | Parsed `recording_meta.json` (`task_name`, `recording_config_name`, `tags`). `None` for older recordings without the file |

### `ValidationResult`

```python
class ValidationResult(BaseModel):
    status: Literal["pass", "warn", "fail", "error"]
    message: str
    details: dict[str, object] | None = None
```

| status | When to return it |
|--------|-------------------|
| `pass` | The check succeeded |
| `warn` | The check found an issue but the recording is still usable |
| `fail` | The check found a clear, blocking issue |
| `error` | **Do not return this manually.** The runner sets it when `validate()` raises an exception |

#### `details`

`details` is an optional, free-form, JSON-serializable dict used to
record the structured evidence behind the result. There is no fixed
schema — each validator picks its own keys.

**Where it goes.** The runner serializes the result via
`model_dump(mode="json")` and writes it to `validation_result.json` in
the recording folder (`backend/app/features/validation/cache.py`). The same
object is returned to the frontend through `GET /api/validation` as
`ValidationResultItem.details` (orval type:
`{ [key: string]: unknown } | null`).

**Where it does *not* go (yet).** The recording detail page's
Validation summary
(`frontend/src/features/validation/validation-summary.tsx`) only renders
`validator_name`, the `custom` source badge, and `message`. **`details`
is not currently displayed in any UI.** Anything a user must see has to
be in `message` as well; treat `details` as machine-readable evidence
for logs, notebooks, and future UI extensions.

**Conventions.**

- Leave `details=None` (the default) on `status="pass"`.
- On `warn` / `fail`, include the offending value *and* the threshold
  it was compared against, so the result is self-describing without
  re-reading the validator source.
- Values must be JSON-serializable (numbers, strings, bools, lists,
  nested dicts). Pydantic will reject anything else when the result is
  written to disk.
- Do not stuff raw frames or large payloads in here — the file is read
  in full on every recordings-list scan.

**Builtin examples.**

```python
# required_topics_present.py (fail)
details={
    "missing_topics": ["/cam/front"],
    "required_topics": ["/cam/front", "/cam/wrist", "/joint_states"],
}

# total_duration_sec.py (fail, too short)
details={"duration_sec": 4.2, "min_sec": 5.0}

# total_duration_sec.py (fail, too long)
details={"duration_sec": 312.7, "max_sec": 300.0}
```

## Constraints

- **No params mechanism for custom validators.** Hard-code your
  thresholds inside the class. If you need runtime configurability,
  promote the validator to a builtin: add it under
  `backend/app/features/validation/builtins/` and wire its parameters through
  `active_set.py` (this is how `RequiredTopicsPresent` and
  `TotalDurationSec` are configured today).
- **Restart required.** There is no hot reload. Adding, editing, or
  removing a custom validator file requires `make down && make up`.
- **Docker rebuild for fresh files.** Because `backend/app/` is copied into
  the image, *adding a new file* (or renaming one) needs
  `make build && make up`. Editing an existing file works without a
  rebuild as long as the dev container mounts `backend/app/` (the default
  `docker-compose.yml` setup).
- **Exceptions are caught.** If `validate()` raises, the runner converts
  the failure into `status="error"` with a message like
  `"Validator execution error: ValueError: ..."`. The app itself does
  not crash and other validators still run.
- **Reading the MCAP is allowed; everything else is not.** The runner is
  single-worker and synchronous, so any blocking call stalls every
  recording's validation pipeline. Opening `ctx.mcap_path` with
  `MCAPReader` is supported and reasonably fast (chunk-indexed reads),
  but do not hit the network, write files, or read unrelated paths.
  Prefer `ctx.report` first — every numeric aggregate is already there
  and free.

## Testing your validator

The codebase requires 100% backend coverage. Mirror the directory
structure under `tests/`:

```
backend/app/features/validation/custom/right_arm_message_count.py
tests/features/validation/custom/test_right_arm_message_count.py
```

A typical test builds a minimal `ValidationContext` and asserts the
result. Use the `make_ctx()` / `make_topic()` helpers in
`tests/features/validation/conftest.py` for the cheapest fixture.

```python
from tests.features.validation.conftest import make_ctx, make_topic

from app.features.validation.custom.right_arm_message_count import (
    RightArmMessageCount,
)


def test_pass_when_message_count_above_threshold():
    ctx = make_ctx(
        topics=[make_topic("/mcap/slave_arm_right", msg_count=2000)],
    )
    result = RightArmMessageCount().validate(ctx)
    assert result.status == "pass"


def test_warn_when_message_count_low():
    ctx = make_ctx(
        topics=[make_topic("/mcap/slave_arm_right", msg_count=500)],
    )
    result = RightArmMessageCount().validate(ctx)
    assert result.status == "warn"
    assert result.details == {"message_count": 500}
```

For an MCAP-touching validator, pass `mcap_path=<path-to-fixture.mcap>`
to `make_ctx`; the validator opens it through `ctx.mcap_path` exactly
as it does in production.

Run the whole suite with `make test-backend`. The registry is module-level
state, so import order matters: prefer importing the validator class
directly in tests rather than relying on `load_custom_validators()`.

## Where the result shows up

| Surface | Source |
|---------|--------|
| Recording detail page — Validation summary | `GET /api/validation?path=...` (per-validator rows + overall pill) |
| Recordings list — row badge | `FileEntry.validation_overall_status` (loaded from `validation_result.json` during the directory scan) |
| StatusBar — running pill | `/api/jobs/stream` SSE event with `type=validation` |

Re-running `POST /api/validation/analyze?path=<folder>` overwrites
`validation_result.json` in place. Existing reports remain valid even
after you add or remove validators — the next run picks up whatever set
is currently registered.
