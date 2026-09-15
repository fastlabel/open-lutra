# Custom validators (template directory)

Drop a `.py` file in this directory to add a project-specific validation
rule that runs against every recording. The app picks it up on startup
(see [docs/domain/custom_validators.md](../../../../../docs/domain/custom_validators.md) for the full reference: lifecycle, constraints,
testing, output surfaces).

## Minimal template

```python
# backend/app/features/validation/custom/my_check.py
from typing import ClassVar

from app.features.validation import (
    RecordingValidator,
    ValidationContext,
    ValidationResult,
    register_validator,
)


@register_validator
class MyCheck(RecordingValidator):
    name: ClassVar[str] = "my_check"

    def validate(self, ctx: ValidationContext) -> ValidationResult:
        # Inspect ctx.report (topic counts, frequencies, loss events, ...).
        # ctx.mcap_path / ctx.recording_meta are also available.
        # Return one of: pass / warn / fail.
        # "error" is set by the runner if this method raises.
        return ValidationResult(status="pass", message="OK")
```

After adding a new file, restart the app (`make down && make up`). For
the full how-to — including how to read raw MCAP frames via
`ctx.mcap_path`, the Docker rebuild rules, and the test layout — read
[docs/domain/custom_validators.md](../../../../../docs/domain/custom_validators.md).
