from __future__ import annotations

from pathlib import Path

import pytest

from pytest_delta.delta import SCHEMA_VERSION, DeltaData, DeltaFileError, load_delta, save_delta


class TestDeltaData:
    def test_defaults(self) -> None:
        data = DeltaData()
        assert data.version == SCHEMA_VERSION
        assert data.file_hashes == {}
        assert data.forward_graph == {}
        assert data.reverse_graph == {}

    def test_to_dict(self) -> None:
        data = DeltaData(
            file_hashes={"a.py": "abc123"},
            forward_graph={"a.py": {"b.py", "c.py"}},
            reverse_graph={"b.py": {"a.py"}},
        )
        d = data.to_dict()
        assert d["version"] == SCHEMA_VERSION
        assert d["file_hashes"] == {"a.py": "abc123"}
        # Sets converted to sorted lists
        assert d["graph"]["forward"]["a.py"] == ["b.py", "c.py"]
        assert d["graph"]["reverse"]["b.py"] == ["a.py"]

    def test_roundtrip(self) -> None:
        original = DeltaData(
            file_hashes={"a.py": "hash1", "b.py": "hash2"},
            forward_graph={"a.py": {"b.py"}, "b.py": set()},
            reverse_graph={"b.py": {"a.py"}, "a.py": set()},
        )
        restored = DeltaData.from_dict(original.to_dict())
        assert restored.version == original.version
        assert restored.file_hashes == original.file_hashes
        assert restored.forward_graph == original.forward_graph
        assert restored.reverse_graph == original.reverse_graph

    def test_from_dict_newer_version_raises(self) -> None:
        with pytest.raises(DeltaFileError, match="newer than supported"):
            DeltaData.from_dict({"version": SCHEMA_VERSION + 1})

    def test_from_dict_missing_fields(self) -> None:
        data = DeltaData.from_dict({"version": 1})
        assert data.file_hashes == {}
        assert data.forward_graph == {}
        assert data.reverse_graph == {}


class TestLoadSave:
    def test_load_nonexistent_returns_none(self, tmp_path: Path) -> None:
        result = load_delta(tmp_path / "nonexistent.msgpack")
        assert result is None

    def test_save_and_load_roundtrip(self, tmp_path: Path) -> None:
        path = tmp_path / "delta.msgpack"
        original = DeltaData(
            file_hashes={"src/main.py": "abcdef1234567890", "tests/test_main.py": "1234567890abcdef"},
            forward_graph={"tests/test_main.py": {"src/main.py"}},
            reverse_graph={"src/main.py": {"tests/test_main.py"}},
        )
        save_delta(path, original)
        loaded = load_delta(path)
        assert loaded is not None
        assert loaded.file_hashes == original.file_hashes
        assert loaded.forward_graph == original.forward_graph
        assert loaded.reverse_graph == original.reverse_graph

    def test_load_corrupted_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.msgpack"
        path.write_bytes(b"not valid msgpack \x00\xff\xfe")
        with pytest.raises(DeltaFileError, match="Failed to load"):
            load_delta(path)

    def test_save_creates_parent_dirs(self, tmp_path: Path) -> None:
        path = tmp_path / "sub" / "dir" / "delta.msgpack"
        save_delta(path, DeltaData())
        assert path.exists()

    def test_file_is_binary(self, tmp_path: Path) -> None:
        path = tmp_path / "delta.msgpack"
        save_delta(path, DeltaData(file_hashes={"a.py": "hash"}))
        content = path.read_bytes()
        # msgpack is binary, should not be valid UTF-8 text of the dict
        assert b'"file_hashes"' not in content
