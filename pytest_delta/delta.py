from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import msgpack

SCHEMA_VERSION = 1


class DeltaFileError(Exception):
    pass


@dataclass
class DeltaData:
    version: int = SCHEMA_VERSION
    file_hashes: dict[str, str] = field(default_factory=dict)
    forward_graph: dict[str, set[str]] = field(default_factory=dict)
    reverse_graph: dict[str, set[str]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "file_hashes": self.file_hashes,
            "graph": {
                "forward": {k: sorted(v) for k, v in self.forward_graph.items()},
                "reverse": {k: sorted(v) for k, v in self.reverse_graph.items()},
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> DeltaData:
        version = data.get("version", 0)
        if version > SCHEMA_VERSION:
            raise DeltaFileError(
                f"Delta file version {version} is newer than supported version {SCHEMA_VERSION}. "
                "Please update pytest-delta."
            )
        graph = data.get("graph", {})
        return cls(
            version=version,
            file_hashes=data.get("file_hashes", {}),
            forward_graph={k: set(v) for k, v in graph.get("forward", {}).items()},
            reverse_graph={k: set(v) for k, v in graph.get("reverse", {}).items()},
        )


def load_delta(path: Path) -> DeltaData | None:
    if not path.exists():
        return None
    try:
        with open(path, "rb") as f:
            data = msgpack.unpack(f, raw=False)
        return DeltaData.from_dict(data)
    except (msgpack.UnpackException, msgpack.ExtraData, TypeError, ValueError, KeyError) as e:
        raise DeltaFileError(f"Failed to load delta file: {e}") from e


def save_delta(path: Path, data: DeltaData) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            msgpack.pack(data.to_dict(), f, use_bin_type=True)
    except (OSError, msgpack.PackException) as e:
        raise DeltaFileError(f"Failed to save delta file: {e}") from e
