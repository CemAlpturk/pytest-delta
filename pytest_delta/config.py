from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest


@dataclass
class DeltaConfig:
    enabled: bool = False
    delta_file: Path = field(default_factory=lambda: Path(".delta.msgpack"))
    rebuild: bool = False
    no_save: bool = False
    debug: bool = False
    root_path: Path = field(default_factory=Path.cwd)

    @classmethod
    def from_pytest_config(cls, config: pytest.Config) -> DeltaConfig:
        root_path = config.rootpath
        enabled = config.getoption("delta", default=False)
        delta_file_opt = config.getoption("delta_file", default=None)

        if delta_file_opt is not None:
            delta_file = Path(delta_file_opt)
            if not delta_file.is_absolute():
                delta_file = root_path / delta_file
        else:
            delta_file = root_path / ".delta.msgpack"

        return cls(
            enabled=enabled,
            delta_file=delta_file,
            rebuild=config.getoption("delta_rebuild", default=False),
            no_save=config.getoption("delta_no_save", default=False),
            debug=config.getoption("delta_debug", default=False),
            root_path=root_path,
        )

    def debug_print(self, msg: str) -> None:
        if self.debug:
            print(f"[pytest-delta] {msg}")
