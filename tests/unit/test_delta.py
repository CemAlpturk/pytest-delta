"""Tests for the delta module."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from pytest_delta.delta import (
    SCHEMA_VERSION,
    DeltaData,
    DeltaFileError,
    load_delta,
    save_delta,
)
from pytest_delta.graph import DependencyGraph


class TestDeltaData:
    """Tests for DeltaData."""

    def test_default_values(self) -> None:
        """Test default values."""
        data = DeltaData()
        assert data.version == SCHEMA_VERSION
        assert data.last_passed_commit == ""
        assert data.last_passed_time == 0.0
        assert isinstance(data.graph, DependencyGraph)

    def test_to_dict(self) -> None:
        """Test serialization to dict."""
        data = DeltaData(
            version=1,
            last_passed_commit="abc123",
            last_passed_time=1234567890.0,
        )
        result = data.to_dict()

        assert result["v"] == 1
        assert result["sha"] == "abc123"
        assert result["ts"] == 1234567890.0
        assert "graph" in result

    def test_from_dict(self) -> None:
        """Test deserialization from dict."""
        data_dict = {
            "v": 1,
            "sha": "abc123",
            "ts": 1234567890.0,
            "graph": {"forward": {}, "reverse": {}, "hashes": {}},
        }
        data = DeltaData.from_dict(data_dict)

        assert data.version == 1
        assert data.last_passed_commit == "abc123"
        assert data.last_passed_time == 1234567890.0

    def test_from_dict_newer_version_raises_error(self) -> None:
        """Test that newer versions raise an error."""
        data_dict = {
            "v": SCHEMA_VERSION + 1,
            "sha": "abc123",
            "ts": 1234567890.0,
        }
        with pytest.raises(DeltaFileError, match="newer than supported"):
            DeltaData.from_dict(data_dict)

    def test_round_trip(self) -> None:
        """Test that to_dict and from_dict are inverses."""
        original = DeltaData(
            version=1,
            last_passed_commit="abc123def456",
            last_passed_time=time.time(),
        )
        original.graph.file_hashes["test.py"] = "hash123"

        data_dict = original.to_dict()
        restored = DeltaData.from_dict(data_dict)

        assert original.version == restored.version
        assert original.last_passed_commit == restored.last_passed_commit
        assert original.last_passed_time == restored.last_passed_time
        assert original.graph.file_hashes == restored.graph.file_hashes


class TestSaveAndLoadDelta:
    """Tests for save_delta and load_delta."""

    def test_save_and_load(self, tmp_path: Path) -> None:
        """Test saving and loading a delta file."""
        delta_path = tmp_path / ".delta.msgpack"

        config = MagicMock()
        config.debug_print = MagicMock()

        graph = DependencyGraph()
        graph.file_hashes["test.py"] = "abc123"
        graph.forward_graph["test.py"] = {"utils.py"}

        save_delta(delta_path, "commit123abc", graph, config)

        assert delta_path.exists()

        loaded = load_delta(delta_path, config)
        assert loaded is not None
        assert loaded.last_passed_commit == "commit123abc"
        assert loaded.graph.file_hashes == {"test.py": "abc123"}
        assert loaded.graph.forward_graph["test.py"] == {"utils.py"}

    def test_load_nonexistent_returns_none(self, tmp_path: Path) -> None:
        """Test that loading a nonexistent file returns None."""
        delta_path = tmp_path / "nonexistent.msgpack"

        config = MagicMock()
        config.debug_print = MagicMock()

        result = load_delta(delta_path, config)
        assert result is None

    def test_load_corrupted_file_raises_error(self, tmp_path: Path) -> None:
        """Test that loading a corrupted file raises an error."""
        delta_path = tmp_path / ".delta.msgpack"
        delta_path.write_bytes(b"not valid msgpack data!!!")

        config = MagicMock()
        config.debug_print = MagicMock()

        with pytest.raises(DeltaFileError, match="Failed to parse"):
            load_delta(delta_path, config)

    def test_save_creates_parent_directories(self, tmp_path: Path) -> None:
        """Test that save creates parent directories."""
        delta_path = tmp_path / "subdir" / "another" / ".delta.msgpack"

        config = MagicMock()
        config.debug_print = MagicMock()

        graph = DependencyGraph()
        save_delta(delta_path, "commit123", graph, config)

        assert delta_path.exists()

    def test_delta_file_is_binary(self, tmp_path: Path) -> None:
        """Test that the delta file is binary (not readable as text)."""
        delta_path = tmp_path / ".delta.msgpack"

        config = MagicMock()
        config.debug_print = MagicMock()

        graph = DependencyGraph()
        graph.file_hashes["test.py"] = "abc123"

        save_delta(delta_path, "commit123", graph, config)

        content = delta_path.read_bytes()
        # Should not be valid JSON or plain text
        with pytest.raises(UnicodeDecodeError):
            content.decode("ascii")

    def test_timestamp_is_set(self, tmp_path: Path) -> None:
        """Test that timestamp is set when saving."""
        delta_path = tmp_path / ".delta.msgpack"

        config = MagicMock()
        config.debug_print = MagicMock()

        before = time.time()
        save_delta(delta_path, "commit123", DependencyGraph(), config)
        after = time.time()

        loaded = load_delta(delta_path, config)
        assert loaded is not None
        assert before <= loaded.last_passed_time <= after
