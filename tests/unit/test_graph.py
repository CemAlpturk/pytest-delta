from __future__ import annotations

from pathlib import Path

from pytest_delta.graph import (
    apply_conftest_rule,
    build_forward_graph,
    build_module_map,
    build_reverse_graph,
    compute_file_hash,
    discover_py_files,
    extract_imports,
    get_affected_files,
    resolve_import,
)


class TestComputeFileHash:
    def test_returns_16_char_hex(self, tmp_path: Path) -> None:
        f = tmp_path / "test.py"
        f.write_text("print('hello')")
        h = compute_file_hash(f)
        assert len(h) == 16
        assert all(c in "0123456789abcdef" for c in h)

    def test_same_content_same_hash(self, tmp_path: Path) -> None:
        f1 = tmp_path / "a.py"
        f2 = tmp_path / "b.py"
        f1.write_text("content")
        f2.write_text("content")
        assert compute_file_hash(f1) == compute_file_hash(f2)

    def test_different_content_different_hash(self, tmp_path: Path) -> None:
        f1 = tmp_path / "a.py"
        f2 = tmp_path / "b.py"
        f1.write_text("content_a")
        f2.write_text("content_b")
        assert compute_file_hash(f1) != compute_file_hash(f2)


class TestDiscoverPyFiles:
    def test_finds_py_files(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "b.py").write_text("")
        result = discover_py_files(tmp_path)
        assert "a.py" in result
        assert str(Path("sub") / "b.py") in result

    def test_skips_venv(self, tmp_path: Path) -> None:
        (tmp_path / ".venv").mkdir()
        (tmp_path / ".venv" / "lib.py").write_text("")
        (tmp_path / "real.py").write_text("")
        result = discover_py_files(tmp_path)
        assert "real.py" in result
        assert ".venv/lib.py" not in result

    def test_skips_hidden_dirs(self, tmp_path: Path) -> None:
        (tmp_path / ".hidden").mkdir()
        (tmp_path / ".hidden" / "mod.py").write_text("")
        result = discover_py_files(tmp_path)
        assert ".hidden/mod.py" not in result

    def test_skips_pycache(self, tmp_path: Path) -> None:
        (tmp_path / "__pycache__").mkdir()
        (tmp_path / "__pycache__" / "mod.cpython-312.pyc").write_text("")
        result = discover_py_files(tmp_path)
        assert len(result) == 0

    def test_ignores_non_py_files(self, tmp_path: Path) -> None:
        (tmp_path / "readme.md").write_text("")
        (tmp_path / "config.yaml").write_text("")
        (tmp_path / "actual.py").write_text("")
        result = discover_py_files(tmp_path)
        assert len(result) == 1
        assert "actual.py" in result


class TestExtractImports:
    def test_simple_import(self, tmp_path: Path) -> None:
        f = tmp_path / "mod.py"
        f.write_text("import os\nimport sys\n")
        result = extract_imports(f, "mod.py")
        assert "os" in result
        assert "sys" in result

    def test_from_import(self, tmp_path: Path) -> None:
        f = tmp_path / "mod.py"
        f.write_text("from os.path import join\nfrom collections import defaultdict\n")
        result = extract_imports(f, "mod.py")
        assert "os.path" in result
        assert "collections" in result

    def test_relative_import_level_1(self, tmp_path: Path) -> None:
        f = tmp_path / "mod.py"
        f.write_text("from .utils import helper\n")
        result = extract_imports(f, str(Path("pkg") / "mod.py"))
        assert "pkg.utils" in result

    def test_relative_import_level_2(self, tmp_path: Path) -> None:
        f = tmp_path / "mod.py"
        f.write_text("from ..utils import helper\n")
        result = extract_imports(f, str(Path("pkg") / "sub" / "mod.py"))
        assert "pkg.utils" in result

    def test_relative_import_from_init(self, tmp_path: Path) -> None:
        f = tmp_path / "__init__.py"
        f.write_text("from .core import main\n")
        result = extract_imports(f, str(Path("pkg") / "__init__.py"))
        assert "pkg.core" in result

    def test_relative_import_no_module(self, tmp_path: Path) -> None:
        f = tmp_path / "mod.py"
        f.write_text("from . import utils\n")
        result = extract_imports(f, str(Path("pkg") / "mod.py"))
        assert "pkg" in result

    def test_syntax_error_returns_empty(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.py"
        f.write_text("def broken(\n")
        result = extract_imports(f, "bad.py")
        assert result == set()

    def test_unicode_error_returns_empty(self, tmp_path: Path) -> None:
        f = tmp_path / "binary.py"
        f.write_bytes(b"\xff\xfe\x00\x01")
        result = extract_imports(f, "binary.py")
        assert result == set()


class TestBuildModuleMap:
    def test_regular_module(self) -> None:
        files = {"pkg/mod.py": Path("pkg/mod.py")}
        m = build_module_map(files)
        assert m["pkg.mod"] == "pkg/mod.py"

    def test_package_init(self) -> None:
        files = {"pkg/__init__.py": Path("pkg/__init__.py")}
        m = build_module_map(files)
        assert m["pkg"] == "pkg/__init__.py"

    def test_top_level_module(self) -> None:
        files = {"utils.py": Path("utils.py")}
        m = build_module_map(files)
        assert m["utils"] == "utils.py"

    def test_src_prefix_stripping(self) -> None:
        files = {"src/mylib/core.py": Path("src/mylib/core.py")}
        m = build_module_map(files)
        assert m["src.mylib.core"] == "src/mylib/core.py"
        assert m["mylib.core"] == "src/mylib/core.py"

    def test_nested_packages(self) -> None:
        files = {
            "pkg/__init__.py": Path("pkg/__init__.py"),
            "pkg/sub/__init__.py": Path("pkg/sub/__init__.py"),
            "pkg/sub/mod.py": Path("pkg/sub/mod.py"),
        }
        m = build_module_map(files)
        assert m["pkg"] == "pkg/__init__.py"
        assert m["pkg.sub"] == "pkg/sub/__init__.py"
        assert m["pkg.sub.mod"] == "pkg/sub/mod.py"


class TestResolveImport:
    def test_exact_match(self) -> None:
        module_map = {"pkg.mod": "pkg/mod.py"}
        assert resolve_import("pkg.mod", module_map) == "pkg/mod.py"

    def test_submodule_match(self) -> None:
        module_map = {"pkg.mod": "pkg/mod.py"}
        # from pkg.mod import something -> resolves to pkg.mod
        assert resolve_import("pkg.mod.something", module_map) == "pkg/mod.py"

    def test_package_match(self) -> None:
        module_map = {"pkg": "pkg/__init__.py"}
        assert resolve_import("pkg.submod", module_map) == "pkg/__init__.py"

    def test_external_returns_none(self) -> None:
        module_map = {"mylib": "mylib/__init__.py"}
        assert resolve_import("numpy", module_map) is None

    def test_empty_map(self) -> None:
        assert resolve_import("anything", {}) is None


class TestBuildForwardGraph:
    def test_simple_dependency(self, tmp_path: Path) -> None:
        (tmp_path / "utils.py").write_text("def add(a, b): return a + b\n")
        (tmp_path / "test_utils.py").write_text("from utils import add\n")
        py_files = discover_py_files(tmp_path)
        module_map = build_module_map(py_files)
        forward = build_forward_graph(py_files, module_map)
        assert "utils.py" in forward["test_utils.py"]

    def test_no_self_loops(self, tmp_path: Path) -> None:
        (tmp_path / "mod.py").write_text("import mod\n")
        py_files = discover_py_files(tmp_path)
        module_map = build_module_map(py_files)
        forward = build_forward_graph(py_files, module_map)
        assert "mod.py" not in forward["mod.py"]

    def test_includes_init_files(self, tmp_path: Path) -> None:
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "core.py").write_text("x = 1")
        (tmp_path / "main.py").write_text("from pkg.core import x\n")
        py_files = discover_py_files(tmp_path)
        module_map = build_module_map(py_files)
        forward = build_forward_graph(py_files, module_map)
        deps = forward["main.py"]
        assert str(Path("pkg") / "core.py") in deps
        assert str(Path("pkg") / "__init__.py") in deps


class TestBuildReverseGraph:
    def test_direct_reverse(self) -> None:
        forward = {"a.py": {"b.py"}, "b.py": set()}
        reverse = build_reverse_graph(forward)
        assert "a.py" in reverse["b.py"]

    def test_transitive_reverse(self) -> None:
        # a imports b, b imports c => reverse[c] should include both a and b
        forward = {"a.py": {"b.py"}, "b.py": {"c.py"}, "c.py": set()}
        reverse = build_reverse_graph(forward)
        assert reverse["c.py"] == {"a.py", "b.py"}

    def test_diamond_dependency(self) -> None:
        # a->b, a->c, b->d, c->d
        forward = {
            "a.py": {"b.py", "c.py"},
            "b.py": {"d.py"},
            "c.py": {"d.py"},
            "d.py": set(),
        }
        reverse = build_reverse_graph(forward)
        assert reverse["d.py"] == {"a.py", "b.py", "c.py"}

    def test_handles_cycles(self) -> None:
        forward = {"a.py": {"b.py"}, "b.py": {"a.py"}}
        reverse = build_reverse_graph(forward)
        assert "b.py" in reverse["a.py"]
        assert "a.py" in reverse["b.py"]


class TestGetAffectedFiles:
    def test_returns_changed_plus_dependents(self) -> None:
        reverse = {"lib.py": {"test_lib.py", "app.py"}, "test_lib.py": set()}
        affected = get_affected_files({"lib.py"}, reverse)
        assert affected == {"lib.py", "test_lib.py", "app.py"}

    def test_independent_file_not_affected(self) -> None:
        reverse = {"lib.py": {"test_lib.py"}, "other.py": set()}
        affected = get_affected_files({"lib.py"}, reverse)
        assert "other.py" not in affected

    def test_empty_changed(self) -> None:
        reverse = {"lib.py": {"test_lib.py"}}
        affected = get_affected_files(set(), reverse)
        assert affected == set()


class TestApplyConftestRule:
    def test_root_conftest_marks_all_tests(self) -> None:
        all_tests = {"tests/test_a.py", "tests/sub/test_b.py", "test_top.py"}
        result = apply_conftest_rule({"conftest.py"}, set(), all_tests)
        assert result == all_tests

    def test_subdir_conftest_marks_subdir_tests_only(self) -> None:
        all_tests = {"tests/test_a.py", "tests/sub/test_b.py", "other/test_c.py"}
        result = apply_conftest_rule(
            {str(Path("tests") / "conftest.py")},
            set(),
            all_tests,
        )
        assert str(Path("tests") / "test_a.py") in result or "tests/test_a.py" in result
        assert str(Path("tests") / "sub" / "test_b.py") in result or "tests/sub/test_b.py" in result
        assert "other/test_c.py" not in result

    def test_no_conftest_change_no_effect(self) -> None:
        all_tests = {"test_a.py", "test_b.py"}
        result = apply_conftest_rule({"src/utils.py"}, set(), all_tests)
        assert result == set()

    def test_preserves_existing_affected(self) -> None:
        existing = {"test_a.py"}
        result = apply_conftest_rule({"conftest.py"}, existing, {"test_a.py", "test_b.py"})
        assert "test_a.py" in result
        assert "test_b.py" in result
