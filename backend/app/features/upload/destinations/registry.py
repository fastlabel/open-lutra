"""Select the upload destination active in this deployment.

Today the only destination is S3 (which also covers MinIO / Cloudflare R2
/ LocalStack via ``AWS_ENDPOINT_URL``). When GCS or a local-server
destination lands, this module switches on a future ``UPLOAD_DESTINATION``
setting and returns the matching instance — callers receive whichever
destination is active and do not change.

Only one destination is active per machine; multi-destination uploads are
explicitly out of scope.
"""

from app.features.upload.destinations.base import UploadDestination
from app.features.upload.destinations.s3 import S3Destination
from app.settings import Settings


def get_active_destination(settings: Settings) -> UploadDestination:
    """Return the upload destination instance configured for this deployment."""
    return S3Destination(settings)
