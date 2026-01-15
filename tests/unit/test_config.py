"""Tests for the config module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from pytest_delta.config import DeltaConfig


class TestDeltaConfig:
    """Tests for DeltaConfig."""

    def test_default_values(self) -> None:
        """Test default configuration values."""
        config = DeltaConfig()

        assert config.enabled is False
        assert config.delta_file == Path(".delta.msgpack")
        assert config.debug is False
        assert config.pass_if_no_tests is False
        assert config.no_save is False
        assert config.ignore_patterns == []
        assert config.rebuild is False

    def test_from_pytest_config(self, tmp_path: Path) -> None:
        """Test creating config from pytest config."""
        mock_config = MagicMock()
        mock_config.rootpath = tmp_path
        mock_config.getoption = MagicMock(
            side_effect=lambda key, default=None: {
                "delta": True,
                "delta_file": None,
                "delta_debug": True,
                "delta_pass_if_no_tests": False,
                "delta_no_save": True,
                "delta_ignore": ["*.pyc", "tests/*"],
                "delta_rebuild": False,
            }.get(key, default)
        )

        config = DeltaConfig.from_pytest_config(mock_config)

        assert config.enabled is True
        assert config.delta_file == tmp_path / ".delta.msgpack"
        assert config.debug is True
        assert config.no_save is True
        assert config.ignore_patterns == ["*.pyc", "tests/*"]
        assert config.root_path == tmp_path

    def test_from_pytest_config_custom_delta_file(self, tmp_path: Path) -> None:
        """Test creating config with custom delta file path."""
        mock_config = MagicMock()
        mock_config.rootpath = tmp_path
        mock_config.getoption = MagicMock(
            side_effect=lambda key, default=None: {
                "delta": True,
                "delta_file": "custom/.delta",
                "delta_debug": False,
                "delta_pass_if_no_tests": False,
                "delta_no_save": False,
                "delta_ignore": [],
                "delta_rebuild": False,
            }.get(key, default)
        )

        config = DeltaConfig.from_pytest_config(mock_config)

        assert config.delta_file == tmp_path / "custom/.delta"

    def test_from_pytest_config_absolute_delta_file(self, tmp_path: Path) -> None:
        """Test creating config with absolute delta file path."""
        custom_path = tmp_path / "absolute" / ".delta"

        mock_config = MagicMock()
        mock_config.rootpath = tmp_path
        mock_config.getoption = MagicMock(
            side_effect=lambda key, default=None: {
                "delta": True,
                "delta_file": str(custom_path),
                "delta_debug": False,
                "delta_pass_if_no_tests": False,
                "delta_no_save": False,
                "delta_ignore": [],
                "delta_rebuild": False,
            }.get(key, default)
        )

        config = DeltaConfig.from_pytest_config(mock_config)

        assert config.delta_file == custom_path


class TestShouldIgnore:
    """Tests for should_ignore method."""

    def test_no_patterns_never_ignores(self) -> None:
        """Test that no patterns means nothing is ignored."""
        config = DeltaConfig(ignore_patterns=[])

        assert config.should_ignore("any/file.py") is False
        assert config.should_ignore("test.py") is False

    def test_exact_pattern_match(self) -> None:
        """Test exact pattern matching."""
        config = DeltaConfig(ignore_patterns=["ignored.py"])

        assert config.should_ignore("ignored.py") is True
        assert config.should_ignore("other.py") is False

    def test_wildcard_pattern(self) -> None:
        """Test wildcard pattern matching."""
        config = DeltaConfig(ignore_patterns=["*.pyc"])

        assert config.should_ignore("file.pyc") is True
        assert config.should_ignore("file.py") is False

    def test_directory_pattern(self) -> None:
        """Test directory pattern matching."""
        config = DeltaConfig(ignore_patterns=["tests/*"])

        assert config.should_ignore("tests/test_foo.py") is True
        assert config.should_ignore("src/main.py") is False

    def test_multiple_patterns(self) -> None:
        """Test multiple ignore patterns."""
        config = DeltaConfig(ignore_patterns=["*.pyc", "tests/*", "docs/*"])

        assert config.should_ignore("file.pyc") is True
        assert config.should_ignore("tests/test.py") is True
        assert config.should_ignore("docs/readme.md") is True
        assert config.should_ignore("src/main.py") is False

    def test_accepts_path_object(self) -> None:
        """Test that Path objects are accepted."""
        config = DeltaConfig(ignore_patterns=["*.pyc"])

        assert config.should_ignore(Path("file.pyc")) is True


class TestDebugPrint:
    """Tests for debug_print method."""

    def test_prints_when_debug_enabled(self, capsys) -> None:
        """Test that messages are printed when debug is enabled."""
        config = DeltaConfig(debug=True)

        config.debug_print("test message")

        captured = capsys.readouterr()
        assert "[pytest-delta] test message" in captured.out

    def test_no_output_when_debug_disabled(self, capsys) -> None:
        """Test that nothing is printed when debug is disabled."""
        config = DeltaConfig(debug=False)

        config.debug_print("test message")

        captured = capsys.readouterr()
        assert captured.out == ""
