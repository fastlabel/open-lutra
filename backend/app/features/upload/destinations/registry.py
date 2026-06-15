"""Select the upload destination active in this deployment.

Switches on ``UPLOAD_DESTINATION``:

* ``"s3"`` (default) — :class:`S3Destination`. Also covers MinIO /
  Cloudflare R2 / LocalStack via ``AWS_ENDPOINT_URL``.
* ``"local"`` — :class:`LocalDestination`. Targets a directory mounted
  into the backend container (typically an NFS / SMB share).

Only one destination is active per machine; multi-destination uploads are
explicitly out of scope.
"""

from app.features.upload.destinations.base import UploadDestination
from app.features.upload.destinations.local import LocalDestination
from app.features.upload.destinations.s3 import S3Destination
from app.settings import Settings


def get_active_destination(settings: Settings) -> UploadDestination:
    """Return the upload destination instance configured for this deployment."""
    if settings.upload_destination == "local":
        return LocalDestination(settings)
    return S3Destination(settings)
