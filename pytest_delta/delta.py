"""Delta file management for pytest-delta."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import DeltaConfig

from .graph import DependencyGraph

# Check for msgpack availability
try:
    import msgpack

    MSGPACK_AVAILABLE = True
except ImportError:
    MSGPACK_AVAILABLE = False

# Delta file schema version
SCHEMA_VERSION = 1


class DeltaFileError(Exception):
    """Raised when there's an error with the delta file."""

    pass


@dataclass
class DeltaData:
    """Data stored in the delta file.

    Attributes:
        version: Schema version for forward compatibility.
        last_passed_commit: Git commit SHA when tests last passed.
        last_passed_time: Unix timestamp when tests last passed.
        graph: The dependency graph.
    """

    version: int = SCHEMA_VERSION
    last_passed_commit: str = ""
    last_passed_time: float = 0.0
    graph: DependencyGraph = field(default_factory=DependencyGraph)

    def to_dict(self) -> dict:
        """Serialize to a dictionary.

        Returns:
            A dictionary representation.
        """
        return {
            "v": self.version,
            "sha": self.last_passed_commit,
            "ts": self.last_passed_time,
            "graph": self.graph.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> DeltaData:
        """Deserialize from a dictionary.

        Args:
            data: A dictionary representation.

        Returns:
            A DeltaData instance.

        Raises:
            DeltaFileError: If the schema version is incompatible.
        """
        version = data.get("v", 0)
        if version > SCHEMA_VERSION:
            raise DeltaFileError(
                f"Delta file version {version} is newer than supported version {SCHEMA_VERSION}. "
                "Please update pytest-delta."
            )

        return cls(
            version=version,
            last_passed_commit=data.get("sha", ""),
            last_passed_time=data.get("ts", 0.0),
            graph=DependencyGraph.from_dict(data.get("graph", {})),
        )


def _check_msgpack() -> None:
    """Check that msgpack is available.

    Raises:
        DeltaFileError: If msgpack is not installed.
    """
    if not MSGPACK_AVAILABLE:
        raise DeltaFileError(
            "msgpack is required for pytest-delta but is not installed. "
            "Please install it with: pip install msgpack"
        )


def load_delta(delta_path: Path, config: DeltaConfig) -> DeltaData | None:
    """Load a delta file.

    Args:
        delta_path: Path to the delta file.
        config: The delta configuration.

    Returns:
        The loaded DeltaData, or None if the file doesn't exist.

    Raises:
        DeltaFileError: If msgpack is not available or the file is corrupted.
    """
    _check_msgpack()

    if not delta_path.exists():
        config.debug_print(f"Delta file not found: {delta_path}")
        return None

    try:
        with open(delta_path, "rb") as f:
            data = msgpack.unpack(f, raw=False)

        delta_data = DeltaData.from_dict(data)  # type: ignore
        config.debug_print(
            f"Loaded delta file: commit={delta_data.last_passed_commit[:12]}, "
            f"files={len(delta_data.graph.file_hashes)}"
        )
        return delta_data

    except (
        msgpack.UnpackException,
        msgpack.ExtraData,
        KeyError,
        TypeError,
        ValueError,
    ) as e:
        raise DeltaFileError(
            f"Failed to parse delta file {delta_path}: {e}. "
            "The file may be corrupted. Use --delta-rebuild to regenerate."
        ) from e


def save_delta(
    delta_path: Path,
    commit_sha: str,
    graph: DependencyGraph,
    config: DeltaConfig,
) -> None:
    """Save a delta file.

    Args:
        delta_path: Path to the delta file.
        commit_sha: The current git commit SHA.
        graph: The dependency graph.
        config: The delta configuration.

    Raises:
        DeltaFileError: If msgpack is not available or save fails.
    """
    _check_msgpack()

    delta_data = DeltaData(
        version=SCHEMA_VERSION,
        last_passed_commit=commit_sha,
        last_passed_time=time.time(),
        graph=graph,
    )

    try:
        # Ensure parent directory exists
        delta_path.parent.mkdir(parents=True, exist_ok=True)

        with open(delta_path, "wb") as f:
            msgpack.pack(delta_data.to_dict(), f, use_bin_type=True)

        config.debug_print(f"Saved delta file: {delta_path}")

    except (OSError, msgpack.PackException) as e:
        raise DeltaFileError(f"Failed to save delta file {delta_path}: {e}") from e
