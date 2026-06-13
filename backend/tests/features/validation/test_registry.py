"""Tests for the registry and load_custom_validators."""

import logging

import pytest

from app.features.validation import (
    RecordingValidator,
    ValidationContext,
    ValidationResult,
    register_validator,
)
from app.features.validation.registry import (
    clear_registry,
    get_custom_validators,
    load_custom_validators,
)


class _OkValidator(RecordingValidator):
    name = "ok_validator"

    def validate(self, ctx: ValidationContext) -> ValidationResult:
        return ValidationResult(status="pass", message="ok")


class TestRegisterValidator:
    """Tests for the @register_validator decorator."""

    def test_register_adds_to_registry(self) -> None:
        register_validator(_OkValidator)
        validators = get_custom_validators()
        assert len(validators) == 1
        assert validators[0].name == "ok_validator"

    def test_register_raises_when_name_missing(self) -> None:
        class _NoName(RecordingValidator):
            def validate(self, ctx: ValidationContext) -> ValidationResult:
                return ValidationResult(status="pass", message="x")

        with pytest.raises(ValueError, match="'name'"):
            register_validator(_NoName)

    def test_register_raises_when_name_empty(self) -> None:
        class _EmptyName(RecordingValidator):
            name = ""

            def validate(self, ctx: ValidationContext) -> ValidationResult:
                return ValidationResult(status="pass", message="x")

        with pytest.raises(ValueError, match="'name'"):
            register_validator(_EmptyName)

    def test_duplicate_name_logs_warning_but_keeps_both(self, caplog: pytest.LogCaptureFixture) -> None:
        register_validator(_OkValidator)

        class _OkDup(RecordingValidator):
            name = "ok_validator"

            def validate(self, ctx: ValidationContext) -> ValidationResult:
                return ValidationResult(status="pass", message="dup")

        with caplog.at_level(logging.WARNING):
            register_validator(_OkDup)

        assert any("already registered" in r.message for r in caplog.records)
        # Both stay registered; the UI can still distinguish via source_module.
        assert len(get_custom_validators()) == 2


class TestLoadCustomValidators:
    """Tests for load_custom_validators() discovery."""

    def test_load_empty_package(self) -> None:
        """An empty package registers nothing."""
        load_custom_validators("tests.features.validation.fixtures.empty_plugin")
        assert get_custom_validators() == []

    def test_load_good_plugin(self) -> None:
        """A well-formed module registers its validator."""
        load_custom_validators("tests.features.validation.fixtures.good_plugin")
        validators = get_custom_validators()
        assert len(validators) == 1
        assert validators[0].name == "sample_validator"

    def test_load_mixed_plugin_isolates_failures(self, caplog: pytest.LogCaptureFixture) -> None:
        """A failing module does not prevent others from loading."""
        with caplog.at_level(logging.WARNING):
            load_custom_validators("tests.features.validation.fixtures.mixed_plugin")

        validators = get_custom_validators()
        # bad_validator fails, good_validator succeeds.
        names = [v.name for v in validators]
        assert "mixed_good_validator" in names
        assert "intentional" in " ".join(r.message for r in caplog.records)

    def test_load_nonexistent_package_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING):
            load_custom_validators("nonexistent.package.does.not.exist")
        assert any("Failed to load" in r.message for r in caplog.records)
        assert get_custom_validators() == []

    def test_load_module_without_path_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """When the import target is a module (not a package) a warning is logged."""
        with caplog.at_level(logging.WARNING):
            # `sys` is a top-level module without __path__.
            load_custom_validators("sys")
        assert any("no __path__" in r.message for r in caplog.records)
        assert get_custom_validators() == []


class TestClearRegistry:
    """Tests for clear_registry()."""

    def test_clear_removes_all(self) -> None:
        register_validator(_OkValidator)
        assert len(get_custom_validators()) == 1
        clear_registry()
        assert get_custom_validators() == []
