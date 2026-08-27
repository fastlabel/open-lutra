"""Tests for the OpenAPI export entry point."""

import io
import json

from app.openapi import main


class TestMain:
    """Schema export."""

    def test_writes_pretty_json_with_api_paths(self) -> None:
        """The output is valid JSON, pretty-printed, and contains only the API routes."""
        out = io.StringIO()
        main(out)
        text = out.getvalue()

        schema = json.loads(text)
        assert text.startswith("{\n  ")
        assert text.endswith("}\n")
        assert "/api/recording/status" in schema["paths"]
        assert all(path.startswith("/api/") for path in schema["paths"])
