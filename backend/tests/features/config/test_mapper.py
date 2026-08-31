"""Tests for the config mapper (master metadata fields -> API responses)."""

from pathlib import Path

from app.features.config.mapper import to_metadata_field_responses, to_storage_info
from app.settings import MetadataField, MetadataFieldOption


class TestToMetadataFieldResponses:
    """Tests for to_metadata_field_responses."""

    def test_empty(self) -> None:
        """No fields map to an empty list."""
        assert to_metadata_field_responses([]) == []

    def test_label_falls_back_to_value(self) -> None:
        """An option without a label uses its value as the display label."""
        fields = [
            MetadataField(
                key="target_object",
                label="Target Object",
                options=[
                    MetadataFieldOption(value="box", label="Box"),
                    MetadataFieldOption(value="cup"),  # no label
                ],
            )
        ]

        result = to_metadata_field_responses(fields)

        assert len(result) == 1
        assert result[0].key == "target_object"
        assert result[0].label == "Target Object"
        assert result[0].options[0].value == "box"
        assert result[0].options[0].label == "Box"
        # Missing label falls back to the value.
        assert result[0].options[1].value == "cup"
        assert result[0].options[1].label == "cup"

    def test_defaults_and_passthrough_of_type_pattern_placeholder(self) -> None:
        """type defaults to 'select'; explicit type / pattern / placeholder pass through."""
        fields = [
            MetadataField(key="target_object", label="Target Object"),  # defaults
            MetadataField(
                key="operator_id",
                label="Operator ID",
                type="number",
                pattern="^[0-9]+$",
                placeholder="e.g. 007",
            ),
        ]

        result = to_metadata_field_responses(fields)

        assert result[0].type == "select"
        assert result[0].pattern is None
        assert result[0].placeholder is None
        assert result[1].type == "number"
        assert result[1].pattern == "^[0-9]+$"
        assert result[1].placeholder == "e.g. 007"


class TestToStorageInfo:
    """Tests for to_storage_info."""

    def test_maps_the_free_space(self) -> None:
        result = to_storage_info(Path("/data/output"), 550)

        assert result.path == "/data/output"
        assert result.free_bytes == 550

    def test_uninspectable_volume_keeps_the_path(self) -> None:
        """A volume that cannot be read reports a null count, not a missing path."""
        result = to_storage_info(Path("/data/output"), None)

        assert result.path == "/data/output"
        assert result.free_bytes is None
