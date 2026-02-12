from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from pytest_delta.config import DeltaConfig


def _make_mock_config(
    delta: bool = False,
    delta_file: str | None = None,
    delta_rebuild: bool = False,
    delta_no_save: bool = False,
    delta_debug: bool = False,
    rootpath: Path | None = None,
) -> MagicMock:
    config = MagicMock()
    config.rootpath = rootpath or Path("/project")

    def getoption(name: str, default: object = None) -> object:
        options = {
            "delta": delta,
            "delta_file": delta_file,
            "delta_rebuild": delta_rebuild,
            "delta_no_save": delta_no_save,
            "delta_debug": delta_debug,
        }
        return options.get(name, default)

    config.getoption = getoption
    return config


class TestDeltaConfigDefaults:
    def test_defaults(self) -> None:
        cfg = DeltaConfig()
        assert cfg.enabled is False
        assert cfg.delta_file == Path(".delta.msgpack")
        assert cfg.rebuild is False
        assert cfg.no_save is False
        assert cfg.debug is False

    def test_from_pytest_config_defaults(self) -> None:
        mock = _make_mock_config()
        cfg = DeltaConfig.from_pytest_config(mock)
        assert cfg.enabled is False
        assert cfg.delta_file == Path("/project/.delta.msgpack")
        assert cfg.rebuild is False
        assert cfg.no_save is False
        assert cfg.debug is False
        assert cfg.root_path == Path("/project")

    def test_from_pytest_config_enabled(self) -> None:
        mock = _make_mock_config(delta=True, delta_debug=True, delta_no_save=True)
        cfg = DeltaConfig.from_pytest_config(mock)
        assert cfg.enabled is True
        assert cfg.debug is True
        assert cfg.no_save is True

    def test_from_pytest_config_relative_delta_file(self) -> None:
        mock = _make_mock_config(delta_file="custom/path.msgpack")
        cfg = DeltaConfig.from_pytest_config(mock)
        assert cfg.delta_file == Path("/project/custom/path.msgpack")

    def test_from_pytest_config_absolute_delta_file(self) -> None:
        mock = _make_mock_config(delta_file="/absolute/path.msgpack")
        cfg = DeltaConfig.from_pytest_config(mock)
        assert cfg.delta_file == Path("/absolute/path.msgpack")


class TestDebugPrint:
    def test_debug_print_enabled(self, capsys: object) -> None:
        cfg = DeltaConfig(debug=True)
        cfg.debug_print("hello")
        import sys
        import io

        # Re-test with capsys properly
        cfg.debug_print("test message")

    def test_debug_print_disabled(self, capsys: object) -> None:
        cfg = DeltaConfig(debug=False)
        cfg.debug_print("should not print")

    def test_debug_print_format(self) -> None:
        import io
        import sys

        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            cfg = DeltaConfig(debug=True)
            cfg.debug_print("test msg")
        finally:
            sys.stdout = old_stdout
        assert captured.getvalue().strip() == "[pytest-delta] test msg"

    def test_debug_print_disabled_no_output(self) -> None:
        import io
        import sys

        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            cfg = DeltaConfig(debug=False)
            cfg.debug_print("should not appear")
        finally:
            sys.stdout = old_stdout
        assert captured.getvalue() == ""
