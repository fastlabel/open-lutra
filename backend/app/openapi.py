"""Export the OpenAPI schema without starting the server.

Usage (from `backend/`)::

    uv run python -m app.openapi > ../frontend/openapi.json

`make generate` uses this to feed orval, so regenerating the frontend API
types needs neither Docker nor a running backend.
"""

import json
import sys
from typing import TextIO

from app.main import create_app


def main(out: TextIO = sys.stdout) -> None:
    """Write the OpenAPI schema of the application as pretty-printed JSON."""
    json.dump(create_app().openapi(), out, indent=2)
    out.write("\n")


if __name__ == "__main__":
    main()
