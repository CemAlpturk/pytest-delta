"""Configuration handling for pytest-delta."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest


@dataclass
class DeltaConfig:
    """Configuration for the delta plugin."""

    enabled: bool = False
    delta_file: Path = field(default_factory=lambda: Path(".delta.msgpack"))
    debug: bool = False
    pass_if_no_tests: bool = False
    no_save: bool = False
    ignore_patterns: list[str] = field(default_factory=list)
    rebuild: bool = False

    # Runtime state (not from CLI)
    root_path: Path = field(default_factory=Path.cwd)

    @classmethod
    def from_pytest_config(cls, config: pytest.Config) -> DeltaConfig:
        """Create a DeltaConfig from pytest config options."""
        root_path = Path(config.rootpath)

        delta_file_str = config.getoption("delta_file", None)
        if delta_file_str:
            delta_file = Path(delta_file_str)
            if not delta_file.is_absolute():
                delta_file = root_path / delta_file
        else:
            delta_file = root_path / ".delta.msgpack"

        return cls(
            enabled=config.getoption("delta", False),
            delta_file=delta_file,
            debug=config.getoption("delta_debug", False),
            pass_if_no_tests=config.getoption("delta_pass_if_no_tests", False),
            no_save=config.getoption("delta_no_save", False),
            ignore_patterns=config.getoption("delta_ignore", []) or [],
            rebuild=config.getoption("delta_rebuild", False),
            root_path=root_path,
        )

    def should_ignore(self, file_path: str | Path) -> bool:
        """Check if a file path matches any ignore pattern."""
        path_str = str(file_path)
        return any(
            fnmatch.fnmatch(path_str, pattern) for pattern in self.ignore_patterns
        )

    def debug_print(self, message: str) -> None:
        """Print a debug message if debug mode is enabled."""
        if self.debug:
            print(f"[pytest-delta] {message}")
