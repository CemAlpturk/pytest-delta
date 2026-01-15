"""Tests for the graph module."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent
from unittest.mock import MagicMock

import pytest

from pytest_delta.graph import (
    DependencyGraph,
    compute_file_hash,
    extract_imports,
)


class TestComputeFileHash:
    """Tests for compute_file_hash."""

    def test_returns_16_char_hash(self, tmp_path: Path) -> None:
        """Test that hash is 16 characters."""
        file = tmp_path / "test.py"
        file.write_text("print('hello')")

        result = compute_file_hash(file)
        assert len(result) == 16
        assert all(c in "0123456789abcdef" for c in result)

    def test_same_content_same_hash(self, tmp_path: Path) -> None:
        """Test that same content produces same hash."""
        file1 = tmp_path / "test1.py"
        file2 = tmp_path / "test2.py"
        file1.write_text("print('hello')")
        file2.write_text("print('hello')")

        assert compute_file_hash(file1) == compute_file_hash(file2)

    def test_different_content_different_hash(self, tmp_path: Path) -> None:
        """Test that different content produces different hash."""
        file1 = tmp_path / "test1.py"
        file2 = tmp_path / "test2.py"
        file1.write_text("print('hello')")
        file2.write_text("print('world')")

        assert compute_file_hash(file1) != compute_file_hash(file2)


class TestExtractImports:
    """Tests for extract_imports."""

    def test_extracts_import_statement(self, tmp_path: Path) -> None:
        """Test extracting simple import statements."""
        file = tmp_path / "test.py"
        file.write_text("import os\nimport sys")

        imports = extract_imports(file)
        assert imports == {"os", "sys"}

    def test_extracts_from_import(self, tmp_path: Path) -> None:
        """Test extracting from ... import statements."""
        file = tmp_path / "test.py"
        file.write_text("from pathlib import Path\nfrom collections import defaultdict")

        imports = extract_imports(file)
        assert imports == {"pathlib", "collections"}

    def test_extracts_dotted_import(self, tmp_path: Path) -> None:
        """Test extracting dotted module imports."""
        file = tmp_path / "test.py"
        file.write_text("import os.path\nfrom urllib.parse import urlparse")

        imports = extract_imports(file)
        assert imports == {"os.path", "urllib.parse"}

    def test_handles_syntax_error(self, tmp_path: Path) -> None:
        """Test that syntax errors return empty set."""
        file = tmp_path / "test.py"
        file.write_text("this is not valid python {{{")

        imports = extract_imports(file)
        assert imports == set()

    def test_handles_unicode_error(self, tmp_path: Path) -> None:
        """Test that unicode errors return empty set."""
        file = tmp_path / "test.py"
        file.write_bytes(b"\xff\xfe invalid unicode")

        imports = extract_imports(file)
        assert imports == set()

    def test_extracts_multiple_from_same_module(self, tmp_path: Path) -> None:
        """Test extracting multiple imports from same module."""
        file = tmp_path / "test.py"
        file.write_text(
            dedent("""
            from os import path
            from os import getcwd
            import os
        """)
        )

        imports = extract_imports(file)
        assert imports == {"os"}

    def test_ignores_relative_imports_without_module(self, tmp_path: Path) -> None:
        """Test that relative imports without module are ignored."""
        file = tmp_path / "test.py"
        file.write_text("from . import something")

        imports = extract_imports(file)
        assert imports == set()


class TestDependencyGraph:
    """Tests for DependencyGraph."""

    def test_empty_graph(self) -> None:
        """Test creating an empty graph."""
        graph = DependencyGraph()
        assert graph.forward_graph == {}
        assert graph.reverse_graph == {}
        assert graph.file_hashes == {}

    def test_build_simple_graph(self, tmp_path: Path) -> None:
        """Test building a simple dependency graph."""
        # Create a simple project structure
        (tmp_path / "main.py").write_text("from utils import helper")
        (tmp_path / "utils.py").write_text("def helper(): pass")

        config = MagicMock()
        config.should_ignore = MagicMock(return_value=False)
        config.debug_print = MagicMock()

        graph = DependencyGraph()
        graph.build(tmp_path, config)

        assert "main.py" in graph.forward_graph
        assert "utils.py" in graph.forward_graph
        assert graph.forward_graph["main.py"] == {"utils.py"}
        assert graph.forward_graph["utils.py"] == set()

    def test_reverse_graph_computed(self, tmp_path: Path) -> None:
        """Test that reverse graph is computed correctly."""
        (tmp_path / "a.py").write_text("from b import something")
        (tmp_path / "b.py").write_text("from c import something")
        (tmp_path / "c.py").write_text("x = 1")

        config = MagicMock()
        config.should_ignore = MagicMock(return_value=False)
        config.debug_print = MagicMock()

        graph = DependencyGraph()
        graph.build(tmp_path, config)

        # c.py is depended on by b.py and transitively by a.py
        assert "a.py" in graph.reverse_graph["c.py"]
        assert "b.py" in graph.reverse_graph["c.py"]

        # b.py is depended on by a.py
        assert "a.py" in graph.reverse_graph["b.py"]

    def test_get_affected_files(self, tmp_path: Path) -> None:
        """Test getting affected files."""
        (tmp_path / "a.py").write_text("from b import x")
        (tmp_path / "b.py").write_text("from c import y")
        (tmp_path / "c.py").write_text("y = 1")
        (tmp_path / "d.py").write_text("z = 2")  # Independent

        config = MagicMock()
        config.should_ignore = MagicMock(return_value=False)
        config.debug_print = MagicMock()

        graph = DependencyGraph()
        graph.build(tmp_path, config)

        # If c.py changes, a.py and b.py should be affected
        affected = graph.get_affected_files({"c.py"})
        assert affected == {"c.py", "b.py", "a.py"}

        # d.py is independent
        affected = graph.get_affected_files({"d.py"})
        assert affected == {"d.py"}

    def test_ignores_venv_directory(self, tmp_path: Path) -> None:
        """Test that venv directories are ignored."""
        (tmp_path / "main.py").write_text("x = 1")
        venv = tmp_path / "venv" / "lib"
        venv.mkdir(parents=True)
        (venv / "package.py").write_text("y = 2")

        config = MagicMock()
        config.should_ignore = MagicMock(return_value=False)
        config.debug_print = MagicMock()

        graph = DependencyGraph()
        graph.build(tmp_path, config)

        assert "main.py" in graph.file_hashes
        assert "venv/lib/package.py" not in graph.file_hashes

    def test_respects_ignore_patterns(self, tmp_path: Path) -> None:
        """Test that ignore patterns are respected."""
        (tmp_path / "main.py").write_text("x = 1")
        (tmp_path / "ignored.py").write_text("y = 2")

        config = MagicMock()
        config.should_ignore = lambda p: "ignored" in p
        config.debug_print = MagicMock()

        graph = DependencyGraph()
        graph.build(tmp_path, config)

        assert "main.py" in graph.file_hashes
        assert "ignored.py" not in graph.file_hashes

    def test_to_dict_and_from_dict(self, tmp_path: Path) -> None:
        """Test serialization and deserialization."""
        (tmp_path / "a.py").write_text("from b import x")
        (tmp_path / "b.py").write_text("x = 1")

        config = MagicMock()
        config.should_ignore = MagicMock(return_value=False)
        config.debug_print = MagicMock()

        graph1 = DependencyGraph()
        graph1.build(tmp_path, config)

        # Serialize and deserialize
        data = graph1.to_dict()
        graph2 = DependencyGraph.from_dict(data)

        assert graph1.forward_graph == graph2.forward_graph
        assert graph1.reverse_graph == graph2.reverse_graph
        assert graph1.file_hashes == graph2.file_hashes

    def test_incremental_build(self, tmp_path: Path) -> None:
        """Test that incremental builds only process changed files."""
        (tmp_path / "a.py").write_text("x = 1")
        (tmp_path / "b.py").write_text("y = 2")

        config = MagicMock()
        config.should_ignore = MagicMock(return_value=False)
        config.debug_print = MagicMock()

        # Initial build
        graph = DependencyGraph()
        graph.build(tmp_path, config)

        original_hash_a = graph.file_hashes["a.py"]
        original_hash_b = graph.file_hashes["b.py"]

        # Modify only b.py
        (tmp_path / "b.py").write_text("y = 3")

        # Rebuild incrementally
        graph.build(tmp_path, config)

        # a.py hash should be unchanged
        assert graph.file_hashes["a.py"] == original_hash_a
        # b.py hash should be changed
        assert graph.file_hashes["b.py"] != original_hash_b

    def test_handles_deleted_files(self, tmp_path: Path) -> None:
        """Test that deleted files are removed from the graph."""
        (tmp_path / "a.py").write_text("x = 1")
        (tmp_path / "b.py").write_text("y = 2")

        config = MagicMock()
        config.should_ignore = MagicMock(return_value=False)
        config.debug_print = MagicMock()

        graph = DependencyGraph()
        graph.build(tmp_path, config)

        assert "a.py" in graph.file_hashes
        assert "b.py" in graph.file_hashes

        # Delete b.py
        (tmp_path / "b.py").unlink()

        # Rebuild
        graph.build(tmp_path, config)

        assert "a.py" in graph.file_hashes
        assert "b.py" not in graph.file_hashes
