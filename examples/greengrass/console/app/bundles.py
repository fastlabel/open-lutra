"""Device bundles written by provision.sh under provisioned/<thing>/.

The private key is the only secret in a bundle. Deleting a bundle removes just that file and records when, so
the bundle directories double as the record of which certificates were issued, for which thing, and when.
"""

import io
import json
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.jobs import EXAMPLE_ROOT

ROOT = EXAMPLE_ROOT / "provisioned"
SECRET = "private.pem.key"
METADATA = "metadata.json"


@dataclass
class Bundle:
    thing: str
    thing_group: str | None
    certificate_arn: str | None
    created_at: datetime | None
    downloaded_at: datetime | None
    deleted_at: datetime | None
    has_secret: bool

    @property
    def certificate_id(self) -> str | None:
        return self.certificate_arn.rsplit("/", 1)[-1] if self.certificate_arn else None


def _read_metadata(directory: Path) -> dict:
    path = directory / METADATA
    return json.loads(path.read_text()) if path.is_file() else {}


def _write_metadata(directory: Path, **updates: str) -> None:
    (directory / METADATA).write_text(json.dumps({**_read_metadata(directory), **updates}, indent=2) + "\n")


def _time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load(directory: Path) -> Bundle:
    metadata = _read_metadata(directory)
    return Bundle(
        thing=directory.name,
        thing_group=metadata.get("thing_group"),
        certificate_arn=metadata.get("certificate_arn"),
        created_at=_time(metadata.get("created_at")),
        downloaded_at=_time(metadata.get("downloaded_at")),
        deleted_at=_time(metadata.get("deleted_at")),
        has_secret=(directory / SECRET).is_file(),
    )


def all_bundles() -> list[Bundle]:
    """Every bundle issued from this machine, newest first."""
    if not ROOT.is_dir():
        return []
    bundles = [_load(p) for p in ROOT.iterdir() if p.is_dir()]
    return sorted(bundles, key=lambda b: b.created_at or datetime.min.replace(tzinfo=UTC), reverse=True)


def with_secret() -> list[Bundle]:
    return [b for b in all_bundles() if b.has_secret]


def get(thing: str) -> Bundle | None:
    directory = ROOT / thing
    return _load(directory) if directory.is_dir() else None


def _readme(bundle: Bundle) -> str:
    """device/bundle-README.md filled in for one device: the steps an operator follows on the edge PC."""
    text = (EXAMPLE_ROOT / "device" / "bundle-README.md").read_text()
    created = bundle.created_at.astimezone().strftime("%Y-%m-%d %H:%M") if bundle.created_at else "unknown"
    for key, value in {
        "thing": bundle.thing,
        "thing_group": bundle.thing_group or "unknown",
        "created_at": created,
    }.items():
        text = text.replace("{" + key + "}", value)
    return text


def download(thing: str) -> bytes:
    """The bundle plus setup.sh, cleanup.sh and a README, so the edge PC needs nothing else."""
    directory = ROOT / thing
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("README.md", _readme(_load(directory)))
        archive.write(EXAMPLE_ROOT / "device" / "setup.sh", "setup.sh")
        archive.write(EXAMPLE_ROOT / "device" / "cleanup.sh", "cleanup.sh")
        for path in sorted(directory.iterdir()):
            if path.name != METADATA:
                archive.write(path, f"{thing}/{path.name}")
    _write_metadata(directory, downloaded_at=_now())
    return buffer.getvalue()


def delete_secret(thing: str) -> None:
    directory = ROOT / thing
    (directory / SECRET).unlink()
    _write_metadata(directory, deleted_at=_now())
