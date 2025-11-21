"""Test suite for pytest-delta plugin functionality."""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from git import Repo

from pytest_delta.delta_manager import DeltaManager
from pytest_delta.dependency_analyzer import DependencyAnalyzer
from pytest_delta.plugin import DeltaPlugin


class TestDeltaManager:
    """Test cases for DeltaManager."""

    def test_save_and_load_metadata(self):
        """Test saving and loading metadata."""
        with tempfile.TemporaryDirectory() as temp_dir:
            delta_file = Path(temp_dir) / ".delta.json"
            manager = DeltaManager(delta_file)

            metadata = {
                "last_commit": "abc123",
                "last_successful_run": True,
                "version": "1.2.3",
            }

            manager.save_metadata(metadata)
            loaded_metadata = manager.load_metadata()

            assert loaded_metadata == metadata

    def test_load_nonexistent_file(self):
        """Test loading metadata from non-existent file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            delta_file = Path(temp_dir) / "nonexistent.delta.json"
            manager = DeltaManager(delta_file)

            result = manager.load_metadata()
            assert result is None

    def test_load_invalid_json(self):
        """Test loading metadata from invalid JSON file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            delta_file = Path(temp_dir) / ".delta.json"

            # Create invalid JSON file
            with open(delta_file, "w") as f:
                f.write("invalid json content")

            manager = DeltaManager(delta_file)

            with pytest.raises(ValueError, match="Failed to load delta metadata"):
                manager.load_metadata()

    def test_detect_project_version_from_pyproject_toml_poetry(self):
        """Test version detection from pyproject.toml with Poetry format."""
        with tempfile.TemporaryDirectory() as temp_dir:
            delta_file = Path(temp_dir) / ".delta.json"
            manager = DeltaManager(delta_file)

            # Create pyproject.toml with Poetry-style version
            pyproject_path = Path(temp_dir) / "pyproject.toml"
            with open(pyproject_path, "w") as f:
                f.write('[tool.poetry]\nname = "test-project"\nversion = "1.2.3"')

            root_dir = Path(temp_dir)
            version = manager._detect_project_version(root_dir)

            assert version == "1.2.3"

    def test_detect_project_version_from_pyproject_toml_pep621(self):
        """Test version detection from pyproject.toml with PEP 621 format."""
        with tempfile.TemporaryDirectory() as temp_dir:
            delta_file = Path(temp_dir) / ".delta.json"
            manager = DeltaManager(delta_file)

            # Create pyproject.toml with PEP 621-style version
            pyproject_path = Path(temp_dir) / "pyproject.toml"
            with open(pyproject_path, "w") as f:
                f.write('[project]\nname = "test-project"\nversion = "2.3.4"')

            root_dir = Path(temp_dir)
            version = manager._detect_project_version(root_dir)

            assert version == "2.3.4"

    def test_detect_project_version_from_init_py_src(self):
        """Test version detection from __init__.py in src directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            delta_file = Path(temp_dir) / ".delta.json"
            manager = DeltaManager(delta_file)

            # Create src/mypackage/__init__.py with __version__
            src_dir = Path(temp_dir) / "src"
            package_dir = src_dir / "mypackage"
            package_dir.mkdir(parents=True)

            init_path = package_dir / "__init__.py"
            with open(init_path, "w") as f:
                f.write('"""My package."""\n__version__ = "3.4.5"\n')

            root_dir = Path(temp_dir)
            version = manager._detect_project_version(root_dir)

            assert version == "3.4.5"

    def test_detect_project_version_from_init_py_root(self):
        """Test version detection from __init__.py in root directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            delta_file = Path(temp_dir) / ".delta.json"
            manager = DeltaManager(delta_file)

            # Create mypackage/__init__.py with __version__
            package_dir = Path(temp_dir) / "mypackage"
            package_dir.mkdir()

            init_path = package_dir / "__init__.py"
            with open(init_path, "w") as f:
                f.write('__version__ = "4.5.6"\n')

            root_dir = Path(temp_dir)
            version = manager._detect_project_version(root_dir)

            assert version == "4.5.6"

    def test_detect_project_version_poetry_takes_priority(self):
        """Test that pyproject.toml poetry version takes priority over __init__.py."""
        with tempfile.TemporaryDirectory() as temp_dir:
            delta_file = Path(temp_dir) / ".delta.json"
            manager = DeltaManager(delta_file)

            # Create pyproject.toml with Poetry-style version
            pyproject_path = Path(temp_dir) / "pyproject.toml"
            with open(pyproject_path, "w") as f:
                f.write('[tool.poetry]\nname = "test-project"\nversion = "1.0.0"')

            # Create package with different version
            package_dir = Path(temp_dir) / "mypackage"
            package_dir.mkdir()
            init_path = package_dir / "__init__.py"
            with open(init_path, "w") as f:
                f.write('__version__ = "2.0.0"\n')

            root_dir = Path(temp_dir)
            version = manager._detect_project_version(root_dir)

            # Should prefer pyproject.toml
            assert version == "1.0.0"

    def test_detect_project_version_no_version_found(self):
        """Test version detection returns None when no version found."""
        with tempfile.TemporaryDirectory() as temp_dir:
            delta_file = Path(temp_dir) / ".delta.json"
            manager = DeltaManager(delta_file)

            root_dir = Path(temp_dir)
            version = manager._detect_project_version(root_dir)

            assert version is None

    def test_detect_project_version_malformed_pyproject_toml(self):
        """Test version detection continues to __init__.py when pyproject.toml is malformed."""
        with tempfile.TemporaryDirectory() as temp_dir:
            delta_file = Path(temp_dir) / ".delta.json"
            manager = DeltaManager(delta_file)

            # Create malformed pyproject.toml
            pyproject_path = Path(temp_dir) / "pyproject.toml"
            with open(pyproject_path, "w") as f:
                f.write("invalid toml content [")

            # Create package with version
            package_dir = Path(temp_dir) / "mypackage"
            package_dir.mkdir()
            init_path = package_dir / "__init__.py"
            with open(init_path, "w") as f:
                f.write('__version__ = "1.2.3"\n')

            root_dir = Path(temp_dir)
            version = manager._detect_project_version(root_dir)

            # Should fall back to __init__.py
            assert version == "1.2.3"

    @patch("pytest_delta.delta_manager.GitHelper")
    def test_update_metadata_uses_detected_version(self, mock_git_helper):
        """Test that update_metadata uses detected project version."""
        with tempfile.TemporaryDirectory() as temp_dir:
            delta_file = Path(temp_dir) / ".delta.json"
            manager = DeltaManager(delta_file)

            # Create pyproject.toml with version
            pyproject_path = Path(temp_dir) / "pyproject.toml"
            with open(pyproject_path, "w") as f:
                f.write('[tool.poetry]\nname = "test-project"\nversion = "1.2.3"')

            # Mock successful git helper with commit
            mock_git_instance = Mock()
            mock_git_instance.get_current_commit.return_value = "abc123"
            mock_git_helper.return_value = mock_git_instance

            root_dir = Path(temp_dir).resolve()
            manager.update_metadata(root_dir)

            # Load the saved metadata
            metadata = manager.load_metadata()

            # Verify the detected version was used
            assert metadata["version"] == "1.2.3"
            assert metadata["last_commit"] == "abc123"
            assert metadata["last_successful_run"] is True

    @patch("pytest_delta.delta_manager.GitHelper")
    def test_update_metadata_parent_git_search(self, mock_git_helper):
        """Test that update_metadata uses search_parent_directories=True."""
        with tempfile.TemporaryDirectory() as temp_dir:
            delta_file = Path(temp_dir) / ".delta.json"
            manager = DeltaManager(delta_file)

            # Mock successful git helper with commit
            mock_git_instance = Mock()
            mock_git_instance.get_current_commit.return_value = "abc123"
            mock_git_helper.return_value = mock_git_instance

            root_dir = Path(temp_dir).resolve()
            manager.update_metadata(root_dir)

            # Verify that GitHelper was called with search_parent_directories=True
            mock_git_helper.assert_called_once_with(root_dir, search_parent_directories=True)

    def test_hybrid_format_save(self):
        """Test that metadata is saved in hybrid JSON format for minimal Git diffs."""
        with tempfile.TemporaryDirectory() as temp_dir:
            delta_file = Path(temp_dir) / ".delta.json"
            manager = DeltaManager(delta_file)

            # Create metadata with both simple fields and large dicts
            metadata = {
                "last_commit": "abc123def456",
                "last_successful_run": True,
                "version": "1.0.0",
                "dependency_graph": {
                    "src/a.py": ["src/b.py", "src/c.py"],
                    "src/b.py": ["src/c.py"],
                    "src/c.py": [],
                },
                "file_hashes": {
                    "src/a.py": "hash1",
                    "src/b.py": "hash2",
                    "src/c.py": "hash3",
                },
            }

            manager.save_metadata(metadata)

            # Read the file content
            with open(delta_file, "r", encoding="utf-8") as f:
                content = f.read()

            # Verify format characteristics
            lines = content.split("\n")

            # Should have few lines (compact format)
            assert len([line for line in lines if line.strip()]) <= 8, (
                "File should be compact with ~7-8 lines"
            )

            # Simple fields should be on separate lines (readable)
            assert any('"last_commit":' in line for line in lines)
            assert any('"last_successful_run":' in line for line in lines)
            assert any('"version":' in line for line in lines)

            # Large dicts should be on single lines (compact)
            dep_graph_line = [line for line in lines if '"dependency_graph"' in line]
            assert len(dep_graph_line) == 1, "dependency_graph should be on one line"
            assert "src/a.py" in dep_graph_line[0], "dependency_graph should be compact JSON"

            file_hashes_line = [line for line in lines if '"file_hashes"' in line]
            assert len(file_hashes_line) == 1, "file_hashes should be on one line"

            # Should be valid JSON
            import json

            loaded = json.loads(content)
            assert loaded == metadata, "Loaded data should match original"

    def test_hybrid_format_backward_compatibility(self):
        """Test that old pretty-printed JSON format can still be loaded."""
        import json

        with tempfile.TemporaryDirectory() as temp_dir:
            delta_file = Path(temp_dir) / ".delta.json"

            # Create old-style pretty-printed JSON
            old_metadata = {
                "last_commit": "old123",
                "last_successful_run": False,
                "version": "0.3.0",
                "dependency_graph": {
                    "src/old.py": ["src/dep.py"],
                },
                "file_hashes": {
                    "src/old.py": "oldhash",
                },
            }

            # Save in old format (pretty-printed)
            with open(delta_file, "w", encoding="utf-8") as f:
                json.dump(old_metadata, f, indent=2, sort_keys=True)

            # Load with DeltaManager (should work)
            manager = DeltaManager(delta_file)
            loaded = manager.load_metadata()

            assert loaded == old_metadata, "Should load old format correctly"

            # Now save it back (will use new format)
            manager.save_metadata(old_metadata)

            # Verify it still loads correctly
            loaded_again = manager.load_metadata()
            assert loaded_again == old_metadata, "Should work after re-save"


class TestDependencyAnalyzer:
    """Test cases for DependencyAnalyzer."""

    def test_find_python_files(self):
        """Test finding Python files in project structure."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create test structure
            src_dir = temp_path / "src"
            src_dir.mkdir()
            (src_dir / "module1.py").touch()
            (src_dir / "module2.py").touch()

            tests_dir = temp_path / "tests"
            tests_dir.mkdir()
            (tests_dir / "test_module1.py").touch()

            analyzer = DependencyAnalyzer(temp_path)
            python_files = analyzer._find_python_files()

            assert len(python_files) == 3
            file_names = {f.name for f in python_files}
            assert file_names == {"module1.py", "module2.py", "test_module1.py"}

    def test_find_source_files_excludes_test_files(self):
        """Test finding source files excludes test files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create test structure
            src_dir = temp_path / "src"
            src_dir.mkdir()
            (src_dir / "module1.py").touch()
            (src_dir / "module2.py").touch()

            tests_dir = temp_path / "tests"
            tests_dir.mkdir()
            (tests_dir / "test_module1.py").touch()

            analyzer = DependencyAnalyzer(temp_path)
            source_files = analyzer._find_source_files()

            assert len(source_files) == 2
            file_names = {f.name for f in source_files}
            assert file_names == {"module1.py", "module2.py"}

    def test_find_test_files(self):
        """Test finding test files only."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir).resolve()

            # Create test structure
            src_dir = temp_path / "src"
            src_dir.mkdir()
            (src_dir / "module1.py").touch()
            (src_dir / "module2.py").touch()

            tests_dir = temp_path / "tests"
            tests_dir.mkdir()
            (tests_dir / "test_module1.py").touch()
            (tests_dir / "__init__.py").touch()

            analyzer = DependencyAnalyzer(temp_path)
            test_files = analyzer._find_test_files()

            assert len(test_files) == 2
            file_names = {f.name for f in test_files}
            assert file_names == {"test_module1.py", "__init__.py"}

    def test_build_dependency_graph_includes_test_files(self):
        """Test that dependency graph includes both source and test files with their dependencies."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir).resolve()

            # Create test structure
            src_dir = temp_path / "src"
            src_dir.mkdir()

            module_a = src_dir / "module_a.py"
            module_b = src_dir / "module_b.py"
            module_a.write_text("import src.module_b\n")
            module_b.write_text("# Empty module\n")

            tests_dir = temp_path / "tests"
            tests_dir.mkdir()
            test_file = tests_dir / "test_module_a.py"
            test_file.write_text("import src.module_a\n")

            analyzer = DependencyAnalyzer(temp_path)
            dependency_graph = analyzer.build_dependency_graph()

            # Both source and test files should be in the graph
            graph_file_names = {f.name for f in dependency_graph.keys()}
            assert graph_file_names == {
                "module_a.py",
                "module_b.py",
                "test_module_a.py",
            }

            # Test file should be in the dependency graph
            assert test_file.resolve() in dependency_graph

            # Test file should have dependency on module_a
            test_dependencies = dependency_graph[test_file.resolve()]
            assert module_a.resolve() in test_dependencies

    def test_test_filtering_uses_import_dependencies(self):
        """Test that test filtering now uses actual import dependencies instead of just name heuristics."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir).resolve()

            # Create realistic project structure demonstrating the issue
            src_dir = temp_path / "src"
            src_dir.mkdir()
            tests_dir = temp_path / "tests"
            tests_dir.mkdir()

            # Source files
            utils_py = src_dir / "utils.py"
            utils_py.write_text("def add(a, b): return a + b")

            calculator_py = src_dir / "calculator.py"
            calculator_py.write_text(
                "from .utils import add\nclass Calculator:\n    def calc(self, a, b):\n        return add(a, b)"
            )

            # Test files - mix of naming conventions
            test_utils_py = tests_dir / "test_utils.py"  # Follows naming convention
            test_utils_py.write_text(
                "from src.utils import add\ndef test_add(): assert add(1,2) == 3"
            )

            # This test file doesn't follow naming conventions but imports both utils and calculator
            integration_test_py = tests_dir / "integration_test.py"
            integration_test_py.write_text(
                "from src.calculator import Calculator\nfrom src.utils import add\ndef test_integration(): pass"
            )

            analyzer = DependencyAnalyzer(temp_path)
            dependency_graph = analyzer.build_dependency_graph()

            # Simulate a change to utils.py (the base module)
            changed_files = {utils_py}
            affected_files = analyzer.find_affected_files(changed_files, dependency_graph)

            # All files that import utils.py should be affected
            expected_affected = {
                utils_py,  # The changed file itself
                calculator_py,  # Imports utils
                test_utils_py,  # Imports utils
                integration_test_py,  # Imports both utils and calculator
            }

            assert affected_files == expected_affected, (
                f"Expected {[f.relative_to(temp_path) for f in expected_affected]} "
                f"but got {[f.relative_to(temp_path) for f in affected_files]}"
            )

    def test_is_test_file_detection(self):
        """Test test file detection logic."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            analyzer = DependencyAnalyzer(temp_path)

            # Test various file patterns
            test_cases = [
                ("tests/test_module.py", True),
                ("tests/__init__.py", True),
                ("src/test_helper.py", True),  # Starts with test_
                ("src/helper_test.py", True),  # Ends with _test.py
                ("src/module.py", False),
                ("other/module.py", False),
            ]

            for file_path_str, expected in test_cases:
                file_path = temp_path / file_path_str
                is_test = analyzer._is_test_file(file_path, file_path_str)
                assert is_test == expected, (
                    f"Failed for {file_path_str}: expected {expected}, got {is_test}"
                )

    def test_extract_dependencies_simple_import(self):
        """Test extracting dependencies from simple imports."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create test files
            module_a = temp_path / "module_a.py"
            module_b = temp_path / "module_b.py"

            module_a.write_text("import module_b\n")
            module_b.write_text("# Empty module\n")

            analyzer = DependencyAnalyzer(temp_path)
            all_files = {module_a, module_b}

            deps = analyzer._extract_dependencies(module_a, all_files)

            assert module_b in deps

    def test_extract_dependencies_relative_import(self):
        """Test extracting dependencies from relative imports."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir).resolve()

            # Create test files as described in the issue
            module_a = temp_path / "a.py"
            module_b = temp_path / "b.py"

            module_a.write_text("def some_fn(x):\n    return x + 1\n")
            module_b.write_text(
                "from .a import some_fn\n\ndef other_fn(x):\n    return some_fn(x) + 2\n"
            )

            analyzer = DependencyAnalyzer(temp_path)
            all_files = {module_a, module_b}

            # b.py should depend on a.py
            deps = analyzer._extract_dependencies(module_b, all_files)
            assert module_a in deps, f"Expected a.py to be a dependency of b.py, but got: {deps}"

            # Test the full dependency graph
            dependency_graph = analyzer.build_dependency_graph()
            assert module_b in dependency_graph, "b.py should be in dependency graph"
            assert module_a in dependency_graph[module_b], (
                f"a.py should be a dependency of b.py in graph, but got: {dependency_graph[module_b]}"
            )

    def test_find_affected_files(self):
        """Test finding affected files based on changes."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create test files
            module_a = temp_path / "module_a.py"
            module_b = temp_path / "module_b.py"
            module_c = temp_path / "module_c.py"

            module_a.touch()
            module_b.touch()
            module_c.touch()

            # Create dependency graph: A -> B -> C
            dependency_graph = {
                module_a: {module_b},
                module_b: {module_c},
                module_c: set(),
            }

            analyzer = DependencyAnalyzer(temp_path)

            # Change module_c, should affect module_b and module_a
            changed_files = {module_c}
            affected = analyzer.find_affected_files(changed_files, dependency_graph)

            assert affected == {module_a, module_b, module_c}

    def test_ignore_patterns(self):
        """Test ignoring files based on patterns."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create test structure
            src_dir = temp_path / "src"
            src_dir.mkdir()
            (src_dir / "module1.py").touch()
            (src_dir / "module2.py").touch()
            (src_dir / "generated.py").touch()

            vendor_dir = temp_path / "vendor"
            vendor_dir.mkdir()
            (vendor_dir / "external.py").touch()

            tests_dir = temp_path / "tests"
            tests_dir.mkdir()
            (tests_dir / "test_module1.py").touch()

            # Test with ignore patterns
            ignore_patterns = ["*generated*", "vendor/*", "*/test_*"]
            analyzer = DependencyAnalyzer(temp_path, ignore_patterns=ignore_patterns)
            python_files = analyzer._find_python_files()

            # Should only find module1.py and module2.py (ignoring generated.py, vendor/external.py, and test files)
            file_names = {f.name for f in python_files}
            assert file_names == {"module1.py", "module2.py"}

    def test_ignore_patterns_empty(self):
        """Test that no patterns means no ignoring."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create test structure
            src_dir = temp_path / "src"
            src_dir.mkdir()
            (src_dir / "module1.py").touch()
            (src_dir / "generated.py").touch()

            # Test with no ignore patterns
            analyzer = DependencyAnalyzer(temp_path, ignore_patterns=[])
            python_files = analyzer._find_python_files()

            # Should find both files
            file_names = {f.name for f in python_files}
            assert file_names == {"module1.py", "generated.py"}

    def test_resolve_import_handles_empty_names(self):
        """Test that _resolve_import_to_file handles empty or invalid import names gracefully."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create test structure
            src_dir = temp_path / "src"
            src_dir.mkdir()
            (src_dir / "module1.py").touch()

            analyzer = DependencyAnalyzer(temp_path)
            all_files = {src_dir / "module1.py"}

            # Test cases that previously caused "PosixPath('.') has an empty name" error
            test_cases = [
                "",  # Empty string
                ".",  # Just a dot (relative import marker)
                "..",  # Two dots
                "...",  # Three dots
                "    ",  # Whitespace only
                ".module",  # Leading dot
                "module.",  # Trailing dot
            ]

            for import_name in test_cases:
                # Should return None without raising an error
                result = analyzer._resolve_import_to_file(import_name, all_files)
                assert result is None, (
                    f"Expected None for invalid import name {repr(import_name)}, got {result}"
                )


class TestDeltaPlugin:
    """Test cases for DeltaPlugin main functionality."""

    @patch("pytest_delta.plugin.GitHelper")
    def test_plugin_initialization(self, mock_git_helper):
        """Test plugin initialization."""
        config = Mock()
        config.getoption.side_effect = lambda opt: {
            "--delta-filename": ".delta",
            "--delta-dir": ".",
            "--delta-force": False,
        }.get(opt, False)

        plugin = DeltaPlugin(config)

        assert plugin.delta_file.name == ".delta.json"
        assert plugin.force_regenerate is False
        assert not plugin.should_run_all

    @patch("pytest_delta.plugin.GitHelper")
    def test_delta_file_path_construction(self, mock_git_helper):
        """Test delta file path construction from filename and directory."""
        config = Mock()
        config.getoption.side_effect = lambda opt: {
            "--delta-filename": "my-delta",
            "--delta-dir": "/custom/dir",
            "--delta-force": False,
        }.get(opt, False)

        plugin = DeltaPlugin(config)

        # Should automatically add .json extension
        assert plugin.delta_file == Path("/custom/dir/my-delta.json")

        # Test with filename already having .json extension
        config.getoption.side_effect = lambda opt: {
            "--delta-filename": "my-delta.json",
            "--delta-dir": "/custom/dir",
            "--delta-force": False,
        }.get(opt, False)

        plugin2 = DeltaPlugin(config)
        assert plugin2.delta_file == Path("/custom/dir/my-delta.json")

    @patch("pytest_delta.plugin.GitHelper")
    def test_no_git_repo_fallback(self, mock_git_helper):
        """Test fallback when not in a Git repository."""
        from pytest_delta.git_helper import NotAGitRepositoryError

        mock_git_helper.side_effect = NotAGitRepositoryError("Not a git repo")

        config = Mock()
        config.getoption.side_effect = lambda opt: {
            "--delta-filename": ".delta",
            "--delta-dir": ".",
            "--delta-force": False,
        }.get(opt, False)

        plugin = DeltaPlugin(config)
        plugin._analyze_changes()

        assert plugin.should_run_all is True

    @patch("pytest_delta.plugin.GitHelper")
    def test_non_root_git_repo_detection(self, mock_git_helper):
        """Test that git repository is detected even when .git is in parent directory."""

        # Mock successful GitHelper creation to simulate finding git repo in parent
        mock_git_instance = Mock()
        mock_git_helper.return_value = mock_git_instance

        config = Mock()
        config.getoption.side_effect = lambda opt: {
            "--delta-filename": ".delta",
            "--delta-dir": ".",
            "--delta-force": False,
        }.get(opt, False)

        plugin = DeltaPlugin(config)
        plugin._analyze_changes()

        # Verify that GitHelper was called with search_parent_directories=True
        mock_git_helper.assert_called_with(plugin.root_dir, search_parent_directories=True)

        # Should not run all tests if git repo is found (but delta file doesn't exist)
        # In this case should_run_all will be True because delta file doesn't exist
        # but the important thing is that no NotAGitRepositoryError was raised
        assert plugin.should_run_all is True  # Due to missing delta file, not git error

    def test_separate_test_and_source_file_changes(self):
        """Test that test file changes and source file changes are handled separately."""
        config = Mock()
        config.getoption.side_effect = lambda opt: {
            "--delta-filename": ".delta",
            "--delta-dir": ".",
            "--delta-force": False,
            "--delta-ignore": [],
        }.get(opt, [])

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir).resolve()

            # Create test structure
            src_dir = temp_path / "src"
            src_dir.mkdir()
            module_a = src_dir / "module_a.py"
            module_b = src_dir / "module_b.py"
            module_a.write_text("import src.module_b\n")
            module_b.write_text("# Empty module\n")

            tests_dir = temp_path / "tests"
            tests_dir.mkdir()
            test_a = tests_dir / "test_module_a.py"
            test_a.write_text("from src.module_a import *\n")

            plugin = DeltaPlugin(config)
            plugin.root_dir = temp_path
            # Update the analyzer's root_dir to match
            plugin.dependency_analyzer.root_dir = temp_path

            # Simulate changes to both source and test files
            changed_files = {module_a.resolve(), test_a.resolve()}

            # Get file classifications using the analyzer instance from plugin
            source_files = plugin.dependency_analyzer._find_source_files()
            test_files = plugin.dependency_analyzer._find_test_files()

            changed_source_files = {f for f in changed_files if f in source_files}
            changed_test_files = {f for f in changed_files if f in test_files}

            # Verify classifications
            assert module_a.resolve() in changed_source_files
            assert test_a.resolve() in changed_test_files
            assert test_a.resolve() not in changed_source_files
            assert module_a.resolve() not in changed_test_files

            # Build dependency graph should include both source and test files
            dependency_graph = plugin.dependency_analyzer.build_dependency_graph()
            assert module_a.resolve() in dependency_graph
            assert module_b.resolve() in dependency_graph
            assert test_a.resolve() in dependency_graph

    def test_filter_affected_tests_handles_direct_test_changes(self):
        """Test that directly changed test files are selected for testing."""
        config = Mock()
        config.getoption.side_effect = lambda opt: {
            "--delta-filename": ".delta",
            "--delta-dir": ".",
            "--delta-force": False,
            "--delta-ignore": [],
        }.get(opt, [])

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir).resolve()

            # Create test structure
            tests_dir = temp_path / "tests"
            tests_dir.mkdir()
            test_a = tests_dir / "test_module_a.py"
            test_b = tests_dir / "test_module_b.py"
            test_a.touch()
            test_b.touch()

            plugin = DeltaPlugin(config)
            plugin.root_dir = temp_path
            # Update the analyzer's root_dir to match
            plugin.dependency_analyzer.root_dir = temp_path

            # Simulate that test_a was changed directly
            plugin.changed_test_files = {test_a}
            plugin.affected_files = set()  # No source file changes

            # Mock test items
            test_item_a = Mock()
            test_item_a.fspath = str(test_a)

            test_item_b = Mock()
            test_item_b.fspath = str(test_b)

            items = [test_item_a, test_item_b]

            # Filter affected tests
            affected_tests = plugin._filter_affected_tests(items)

            # Only test_a should be selected (it was directly changed)
            assert len(affected_tests) == 1
            assert affected_tests[0] == test_item_a

    def test_debug_flag_initialization(self):
        """Test that debug flag is properly initialized."""
        config = Mock()
        config.getoption.side_effect = lambda opt: {
            "--delta-filename": ".delta",
            "--delta-dir": ".",
            "--delta-force": False,
            "--delta-debug": True,
            "--delta-ignore": [],
        }.get(opt, [])

        plugin = DeltaPlugin(config)
        assert plugin.debug is True

        # Test debug disabled
        config.getoption.side_effect = lambda opt: {
            "--delta-filename": ".delta",
            "--delta-dir": ".",
            "--delta-force": False,
            "--delta-debug": False,
            "--delta-ignore": [],
        }.get(opt, [])

        plugin2 = DeltaPlugin(config)
        assert plugin2.debug is False

    @patch("builtins.print")
    def test_debug_print_method(self, mock_print):
        """Test that _print_debug method works correctly."""
        config = Mock()
        config.getoption.side_effect = lambda opt: {
            "--delta-filename": ".delta",
            "--delta-dir": ".",
            "--delta-force": False,
            "--delta-debug": True,
            "--delta-ignore": [],
        }.get(opt, [])

        plugin = DeltaPlugin(config)
        plugin._print_debug("test debug message")

        mock_print.assert_called_with("[pytest-delta] DEBUG: test debug message")

        # Test debug disabled - should not print
        config.getoption.side_effect = lambda opt: {
            "--delta-filename": ".delta",
            "--delta-dir": ".",
            "--delta-force": False,
            "--delta-debug": False,
            "--delta-ignore": [],
        }.get(opt, [])

        plugin2 = DeltaPlugin(config)
        mock_print.reset_mock()
        plugin2._print_debug("should not print")

        mock_print.assert_not_called()

    @patch("builtins.print")
    def test_affected_files_output_respects_debug_flag(self, mock_print):
        """Test that affected files output is only shown when debug is enabled."""
        # Test with debug enabled - affected files should be printed
        config = Mock()
        config.getoption.side_effect = lambda opt: {
            "--delta-filename": ".delta",
            "--delta-dir": ".",
            "--delta-force": False,
            "--delta-debug": True,
            "--delta-ignore": [],
            "--delta-source-dirs": [],
            "--delta-test-dirs": [],
        }.get(opt, [])

        plugin = DeltaPlugin(config)
        # Use absolute paths relative to the root directory
        plugin.affected_files = {
            plugin.root_dir / "src/module.py",
            plugin.root_dir / "tests/test_module.py",
        }

        # Mock the _print_debug method to track calls
        with patch.object(plugin, "_print_debug") as mock_debug:
            # Simulate the affected files output logic
            if plugin.affected_files:
                affected_files_str = ", ".join(
                    str(f.relative_to(plugin.root_dir)) for f in sorted(plugin.affected_files)
                )
                plugin._print_debug(f"Affected files: {affected_files_str}")

        # Verify _print_debug was called with affected files
        mock_debug.assert_called_with("Affected files: src/module.py, tests/test_module.py")

        # Test with debug disabled - affected files should NOT be printed
        config.getoption.side_effect = lambda opt: {
            "--delta-filename": ".delta",
            "--delta-dir": ".",
            "--delta-force": False,
            "--delta-debug": False,
            "--delta-ignore": [],
            "--delta-source-dirs": [],
            "--delta-test-dirs": [],
        }.get(opt, [])

        plugin2 = DeltaPlugin(config)
        plugin2.affected_files = {
            plugin2.root_dir / "src/module.py",
            plugin2.root_dir / "tests/test_module.py",
        }

        # Mock the _print_debug method to track calls
        with patch.object(plugin2, "_print_debug") as mock_debug2:
            # Simulate the affected files output logic
            if plugin2.affected_files:
                affected_files_str = ", ".join(
                    str(f.relative_to(plugin2.root_dir)) for f in sorted(plugin2.affected_files)
                )
                plugin2._print_debug(f"Affected files: {affected_files_str}")

        # Verify _print_debug was called but actual print should be suppressed
        mock_debug2.assert_called_with("Affected files: src/module.py, tests/test_module.py")

        # Also verify that the actual print behavior works correctly
        mock_print.reset_mock()
        plugin2._print_debug("test message")
        mock_print.assert_not_called()  # Should not print when debug is disabled

    def test_directory_debug_info_collection(self):
        """Test that directory debug information is collected correctly."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create test structure
            src_dir = temp_path / "src"
            src_dir.mkdir()
            (src_dir / "module1.py").write_text("# test")
            (src_dir / "module2.py").write_text("# test")

            tests_dir = temp_path / "tests"
            tests_dir.mkdir()
            (tests_dir / "test_module1.py").write_text("# test")

            # Create analyzer with ignore patterns
            analyzer = DependencyAnalyzer(
                temp_path,
                ignore_patterns=["test_*"],
                source_dirs=[".", "src", "nonexistent"],
                test_dirs=["tests", "missing"],
            )

            # Trigger file finding to populate debug info
            analyzer._find_python_files()

            # Get debug info
            debug_info = analyzer.get_debug_info()

            # Validate debug info structure
            assert "configured_source_dirs" in debug_info
            assert "configured_test_dirs" in debug_info
            assert "searched_dirs" in debug_info
            assert "skipped_dirs" in debug_info
            assert "directory_file_counts" in debug_info
            assert "ignored_files" in debug_info

            # Validate configured directories
            assert debug_info["configured_source_dirs"] == [".", "src", "nonexistent"]
            assert debug_info["configured_test_dirs"] == ["tests", "missing"]

            # Validate searched vs skipped directories
            assert "src" in debug_info["searched_dirs"]
            assert "tests" in debug_info["searched_dirs"]
            assert "nonexistent" in debug_info["skipped_dirs"]
            assert "missing" in debug_info["skipped_dirs"]

            # Validate file counts
            assert debug_info["directory_file_counts"]["src"] == 2
            assert debug_info["directory_file_counts"]["tests"] == 1

            # Validate ignored files
            assert "tests/test_module1.py" in debug_info["ignored_files"]

    @patch("builtins.print")
    def test_directory_debug_print_output(self, mock_print):
        """Test that directory debug information is printed correctly."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create test structure
            src_dir = temp_path / "src"
            src_dir.mkdir()
            (src_dir / "module1.py").write_text("# test")

            analyzer = DependencyAnalyzer(
                temp_path,
                ignore_patterns=["*.backup"],
                source_dirs=["src"],
                test_dirs=["tests"],
            )

            # Trigger file finding
            analyzer._find_python_files()

            # Print debug info
            analyzer.print_directory_debug_info(lambda msg: print(msg))

            # Verify print was called with expected content
            printed_output = "\n".join(call.args[0] for call in mock_print.call_args_list)

            assert "=== Directory Search Debug Information ===" in printed_output
            assert "Configured source directories: ['src']" in printed_output
            assert "Configured test directories: ['tests']" in printed_output
            assert "User ignore patterns: ['*.backup']" in printed_output
            assert "Files found per directory:" in printed_output

    def test_debug_flag_registers_plugin(self):
        """Test that debug flag alone registers the plugin."""
        from pytest_delta.plugin import pytest_configure

        config = Mock()
        config.getoption.side_effect = lambda opt: {
            "--delta": False,
            "--delta-vis": False,
            "--delta-debug": True,
            "--delta-filename": ".delta",
            "--delta-dir": ".",
            "--delta-force": False,
            "--delta-ignore": [],
            "--delta-source-dirs": [],
            "--delta-test-dirs": [],
        }.get(opt, [])

        config.pluginmanager = Mock()

        pytest_configure(config)

        # Plugin should be registered when debug flag is used
        config.pluginmanager.register.assert_called_once()


def test_pytest_integration():
    """Integration test to ensure the plugin can be loaded by pytest."""
    # This test ensures that the plugin entry point is working
    from pytest_delta import plugin

    assert hasattr(plugin, "pytest_addoption")
    assert hasattr(plugin, "pytest_configure")
    assert hasattr(plugin, "DeltaPlugin")


class TestDeltaPassIfNoTests:
    """Test cases for --delta-pass-if-no-tests functionality."""

    def _create_mock_config(self, **overrides):
        """Helper to create mock config with default values."""
        defaults = {
            "--delta-filename": ".delta",
            "--delta-dir": ".",
            "--delta-force": False,
            "--delta-ignore": [],
            "--delta-vis": False,
            "--delta-debug": False,
            "--delta-pass-if-no-tests": False,
            "--delta-source-dirs": [],
            "--delta-test-dirs": [],
        }
        defaults.update(overrides)

        config = Mock()
        config.getoption.side_effect = lambda opt: defaults.get(opt, False)
        return config

    @patch("pytest_delta.plugin.GitHelper")
    def test_pass_if_no_tests_option_initialization(self, mock_git_helper):
        """Test that --delta-pass-if-no-tests option is properly initialized."""
        config = self._create_mock_config(**{"--delta-pass-if-no-tests": True})
        plugin = DeltaPlugin(config)
        assert plugin.pass_if_no_tests is True

    @patch("pytest_delta.plugin.GitHelper")
    def test_pass_if_no_tests_default_false(self, mock_git_helper):
        """Test that --delta-pass-if-no-tests defaults to False."""
        config = self._create_mock_config()
        plugin = DeltaPlugin(config)
        assert plugin.pass_if_no_tests is False

    @patch("pytest_delta.plugin.GitHelper")
    def test_no_tests_due_to_delta_tracking(self, mock_git_helper):
        """Test that no_tests_due_to_delta is set correctly when items are cleared."""
        # Mock git repository
        mock_git_instance = Mock()
        mock_git_helper.return_value = mock_git_instance

        config = self._create_mock_config(
            **{
                "--delta": True,
                "--delta-pass-if-no-tests": True,
            }
        )

        plugin = DeltaPlugin(config)

        # Mock the delta file and metadata loading using a different approach
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch.object(
                plugin.delta_manager,
                "load_metadata",
                return_value={"last_commit": "abc123"},
            ),
            patch.object(plugin, "_get_changed_files", return_value=set()),
        ):
            # Create mock test items
            mock_items = [Mock(), Mock()]

            # Call the method that should clear items
            plugin.pytest_collection_modifyitems(config, mock_items)

            # Verify that items were cleared and flag was set
            assert len(mock_items) == 0
            assert plugin.no_tests_due_to_delta is True

    def test_session_finish_exit_code_override(self):
        """Test that pytest_sessionfinish overrides exit code when appropriate."""
        config = self._create_mock_config(**{"--delta-pass-if-no-tests": True})

        plugin = DeltaPlugin(config)
        plugin.pass_if_no_tests = True
        plugin.no_tests_due_to_delta = True

        # Mock session object
        session = Mock()
        session.testscollected = 0
        session.exitstatus = 5  # This will be modified

        # Call pytest_sessionfinish
        plugin.pytest_sessionfinish(session, exitstatus=pytest.ExitCode.NO_TESTS_COLLECTED)

        # Verify exit code was overridden
        assert session.exitstatus == pytest.ExitCode.OK

    def test_session_finish_no_override_when_flag_disabled(self):
        """Test that pytest_sessionfinish doesn't override when flag is disabled."""
        config = self._create_mock_config(**{"--delta-pass-if-no-tests": False})

        plugin = DeltaPlugin(config)
        plugin.pass_if_no_tests = False
        plugin.no_tests_due_to_delta = True

        # Mock session object
        session = Mock()
        session.testscollected = 0
        session.exitstatus = 5  # Should remain unchanged

        # Call pytest_sessionfinish
        plugin.pytest_sessionfinish(session, exitstatus=pytest.ExitCode.NO_TESTS_COLLECTED)

        # Verify exit code was NOT overridden
        assert session.exitstatus == pytest.ExitCode.NO_TESTS_COLLECTED

    def test_session_finish_no_override_when_not_due_to_delta(self):
        """Test that pytest_sessionfinish doesn't override when no tests isn't due to delta."""
        config = self._create_mock_config(**{"--delta-pass-if-no-tests": True})

        plugin = DeltaPlugin(config)
        plugin.pass_if_no_tests = True
        plugin.no_tests_due_to_delta = False  # Not due to delta analysis

        # Mock session object
        session = Mock()
        session.testscollected = 0
        session.exitstatus = 5  # Should remain unchanged

        # Call pytest_sessionfinish
        plugin.pytest_sessionfinish(session, exitstatus=pytest.ExitCode.NO_TESTS_COLLECTED)

        # Verify exit code was NOT overridden
        assert session.exitstatus == pytest.ExitCode.NO_TESTS_COLLECTED

    def test_session_finish_no_override_when_tests_were_collected(self):
        """Test that pytest_sessionfinish doesn't override when tests were actually collected."""
        config = self._create_mock_config(**{"--delta-pass-if-no-tests": True})

        plugin = DeltaPlugin(config)
        plugin.pass_if_no_tests = True
        plugin.no_tests_due_to_delta = True

        # Mock session object with tests collected
        session = Mock()
        session.testscollected = 5  # Tests were collected
        session.exitstatus = 5

        # Call pytest_sessionfinish
        plugin.pytest_sessionfinish(session, exitstatus=pytest.ExitCode.NO_TESTS_COLLECTED)

        # Verify exit code was NOT overridden
        assert session.exitstatus == pytest.ExitCode.NO_TESTS_COLLECTED

    def test_session_finish_no_override_wrong_exit_code(self):
        """Test that pytest_sessionfinish doesn't override for different exit codes."""
        config = self._create_mock_config(**{"--delta-pass-if-no-tests": True})

        plugin = DeltaPlugin(config)
        plugin.pass_if_no_tests = True
        plugin.no_tests_due_to_delta = True

        # Mock session object
        session = Mock()
        session.testscollected = 0
        session.exitstatus = 1  # Different exit code (tests failed)

        # Call pytest_sessionfinish
        plugin.pytest_sessionfinish(session, exitstatus=pytest.ExitCode.TESTS_FAILED)

        # Verify exit code was NOT overridden
        assert session.exitstatus == pytest.ExitCode.TESTS_FAILED

    @patch("builtins.print")
    def test_session_finish_prints_info_message(self, mock_print):
        """Test that success message is printed when exit code is overridden."""
        config = self._create_mock_config(**{"--delta-pass-if-no-tests": True})

        plugin = DeltaPlugin(config)
        plugin.pass_if_no_tests = True
        plugin.no_tests_due_to_delta = True

        # Mock session object
        session = Mock()
        session.testscollected = 0
        session.exitstatus = 5

        # Call pytest_sessionfinish
        plugin.pytest_sessionfinish(session, exitstatus=pytest.ExitCode.NO_TESTS_COLLECTED)

        # Verify success message was printed
        printed_messages = [call.args[0] for call in mock_print.call_args_list]
        success_message_printed = any(
            "No tests were required due to no changes - exiting with success code 0" in msg
            for msg in printed_messages
        )
        assert success_message_printed


class TestDependencyVisualizer:
    """Test cases for DependencyVisualizer."""

    def test_generate_dot_format(self):
        """Test generating DOT format representation."""
        from pytest_delta.visualizer import DependencyVisualizer

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create test files
            file_a = temp_path / "module_a.py"
            file_b = temp_path / "module_b.py"
            file_c = temp_path / "module_c.py"

            # Create dependency graph: A -> B, B -> C
            dependency_graph = {
                file_a: {file_b},
                file_b: {file_c},
                file_c: set(),
            }

            visualizer = DependencyVisualizer(temp_path)
            dot_content = visualizer.generate_dot_format(dependency_graph)

            # Verify DOT format structure
            assert "digraph dependencies {" in dot_content
            assert "node_" in dot_content
            assert "->" in dot_content
            assert "}" in dot_content
            assert "module_a.py" in dot_content
            assert "module_b.py" in dot_content
            assert "module_c.py" in dot_content

    def test_generate_text_summary(self):
        """Test generating text summary."""
        from pytest_delta.visualizer import DependencyVisualizer

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create test files
            file_a = temp_path / "module_a.py"
            file_b = temp_path / "module_b.py"

            # Create dependency graph
            dependency_graph = {
                file_a: {file_b},
                file_b: set(),
            }

            visualizer = DependencyVisualizer(temp_path)
            summary = visualizer.generate_text_summary(dependency_graph)

            # Verify text summary structure
            assert "Dependency Graph Summary" in summary
            assert "Total files: 2" in summary
            assert "Total dependencies: 1" in summary
            assert "module_a.py" in summary
            assert "module_b.py" in summary

    def test_save_visualization(self):
        """Test saving visualization files."""
        from pytest_delta.visualizer import DependencyVisualizer

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create test files
            file_a = temp_path / "module_a.py"

            # Create simple dependency graph
            dependency_graph = {
                file_a: set(),
            }

            visualizer = DependencyVisualizer(temp_path)

            # Test DOT format save
            dot_file = visualizer.save_visualization(dependency_graph, format="dot")
            assert dot_file.exists()
            assert dot_file.suffix == ".dot"

            # Test text format save
            txt_file = visualizer.save_visualization(dependency_graph, format="txt")
            assert txt_file.exists()
            assert txt_file.suffix == ".txt"

    def test_generate_console_output(self):
        """Test generating console output."""
        from pytest_delta.visualizer import DependencyVisualizer

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create test files
            file_a = temp_path / "module_a.py"

            # Create dependency graph
            dependency_graph = {
                file_a: set(),
            }

            visualizer = DependencyVisualizer(temp_path)
            console_output = visualizer.generate_console_output(dependency_graph)

            # Verify console output structure
            assert "📊 Dependency Graph Visualization" in console_output
            assert "Files: 1" in console_output
            assert "Dependencies: 0" in console_output


class TestDeltaNoSave:
    """Test cases for --delta-no-save functionality."""

    def test_no_save_option_initialization(self):
        """Test that --delta-no-save option is properly initialized."""
        config = Mock()
        config.getoption.side_effect = lambda opt: {
            "--delta-filename": ".delta",
            "--delta-dir": ".",
            "--delta-force": False,
            "--delta-ignore": [],
            "--delta-vis": False,
            "--delta-debug": False,
            "--delta-pass-if-no-tests": False,
            "--delta-no-save": True,
            "--delta-source-dirs": [],
            "--delta-test-dirs": [],
        }.get(opt, [])

        plugin = DeltaPlugin(config)
        assert plugin.no_save is True

        # Test default behavior (no_save should be False by default)
        config.getoption.side_effect = lambda opt: {
            "--delta-filename": ".delta",
            "--delta-dir": ".",
            "--delta-force": False,
            "--delta-ignore": [],
            "--delta-vis": False,
            "--delta-debug": False,
            "--delta-pass-if-no-tests": False,
            "--delta-no-save": False,
            "--delta-source-dirs": [],
            "--delta-test-dirs": [],
        }.get(opt, [])

        plugin2 = DeltaPlugin(config)
        assert plugin2.no_save is False

    @patch("pytest_delta.plugin.GitHelper")
    @patch("builtins.print")
    def test_session_finish_no_save_enabled(self, mock_print, mock_repo):
        """Test that delta metadata is not updated when --delta-no-save is enabled."""
        config = Mock()
        config.getoption.side_effect = lambda opt: {
            "--delta-filename": ".delta",
            "--delta-dir": ".",
            "--delta-force": False,
            "--delta-ignore": [],
            "--delta-vis": False,
            "--delta-debug": False,
            "--delta-pass-if-no-tests": False,
            "--delta-no-save": True,
            "--delta-source-dirs": [],
            "--delta-test-dirs": [],
        }.get(opt, [])

        plugin = DeltaPlugin(config)
        plugin.delta_manager = Mock()

        session = Mock()
        session.testscollected = 1

        # Call pytest_sessionfinish with successful exit status
        plugin.pytest_sessionfinish(session, exitstatus=0)

        # Verify that update_metadata was not called
        plugin.delta_manager.update_metadata.assert_not_called()

        # Verify the correct message was printed
        mock_print.assert_any_call(
            "[pytest-delta] Delta metadata update skipped (--delta-no-save enabled)"
        )

    @patch("pytest_delta.plugin.GitHelper")
    @patch("builtins.print")
    def test_session_finish_no_save_disabled(self, mock_print, mock_repo):
        """Test that delta metadata is updated when --delta-no-save is disabled."""
        config = Mock()
        config.getoption.side_effect = lambda opt: {
            "--delta-filename": ".delta",
            "--delta-dir": ".",
            "--delta-force": False,
            "--delta-ignore": [],
            "--delta-vis": False,
            "--delta-debug": False,
            "--delta-pass-if-no-tests": False,
            "--delta-no-save": False,
            "--delta-source-dirs": [],
            "--delta-test-dirs": [],
        }.get(opt, [])

        plugin = DeltaPlugin(config)
        plugin.delta_manager = Mock()

        session = Mock()
        session.testscollected = 1

        # Call pytest_sessionfinish with successful exit status
        plugin.pytest_sessionfinish(session, exitstatus=0)

        # Verify that update_metadata was called
        plugin.delta_manager.update_metadata.assert_called_once()

        # Verify the correct message was printed
        mock_print.assert_any_call("[pytest-delta] Delta metadata updated successfully")

    @patch("pytest_delta.plugin.GitHelper")
    @patch("builtins.print")
    def test_session_finish_no_save_with_failed_tests(self, mock_print, mock_repo):
        """Test that no update occurs when tests fail, regardless of --delta-no-save setting."""
        config = Mock()
        config.getoption.side_effect = lambda opt: {
            "--delta-filename": ".delta",
            "--delta-dir": ".",
            "--delta-force": False,
            "--delta-ignore": [],
            "--delta-vis": False,
            "--delta-debug": False,
            "--delta-pass-if-no-tests": False,
            "--delta-no-save": True,
            "--delta-source-dirs": [],
            "--delta-test-dirs": [],
        }.get(opt, [])

        plugin = DeltaPlugin(config)
        plugin.delta_manager = Mock()

        session = Mock()
        session.testscollected = 1

        # Call pytest_sessionfinish with failed exit status
        plugin.pytest_sessionfinish(session, exitstatus=1)

        # Verify that update_metadata was not called (because tests failed)
        plugin.delta_manager.update_metadata.assert_not_called()

        # No delta-related messages should be printed for failed tests
        delta_calls = [
            call
            for call in mock_print.call_args_list
            if call[0] and "[pytest-delta]" in str(call[0][0])
        ]
        assert len(delta_calls) == 0


class TestDeltaPluginVisualization:
    """Test cases for DeltaPlugin visualization functionality."""

    @patch("pytest_delta.plugin.GitHelper")
    def test_visualization_option_enabled(self, mock_git_helper):
        """Test plugin initialization with visualization enabled."""
        config = Mock()
        config.getoption.side_effect = lambda opt: {
            "--delta-filename": ".delta",
            "--delta-dir": ".",
            "--delta-force": False,
            "--delta-ignore": [],
            "--delta-vis": True,
        }.get(opt, False)

        plugin = DeltaPlugin(config)
        assert plugin.enable_visualization is True

    @patch("pytest_delta.plugin.GitHelper")
    def test_visualization_option_disabled(self, mock_git_helper):
        """Test plugin initialization with visualization disabled."""
        config = Mock()
        config.getoption.side_effect = lambda opt: {
            "--delta-filename": ".delta",
            "--delta-dir": ".",
            "--delta-force": False,
            "--delta-ignore": [],
            "--delta-vis": False,
        }.get(opt, False)

        plugin = DeltaPlugin(config)
        assert plugin.enable_visualization is False


class TestConfigurableDirectories:
    """Test cases for configurable source and test directories."""

    def test_default_directories(self):
        """Test default directories when no configuration provided."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            analyzer = DependencyAnalyzer(temp_path)

            # Default should include both root and src for source dirs
            assert analyzer.source_dirs == [".", "src"]
            # Default should be tests for test dirs
            assert analyzer.test_dirs == ["tests"]

    def test_custom_source_directories(self):
        """Test custom source directories configuration."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create custom directory structure
            lib_dir = temp_path / "lib"
            lib_dir.mkdir()
            (lib_dir / "module1.py").touch()

            app_dir = temp_path / "app"
            app_dir.mkdir()
            (app_dir / "module2.py").touch()

            # Create analyzer with custom source dirs
            analyzer = DependencyAnalyzer(temp_path, source_dirs=["lib", "app"])
            source_files = analyzer._find_source_files()

            assert len(source_files) == 2
            file_names = {f.name for f in source_files}
            assert file_names == {"module1.py", "module2.py"}

    def test_custom_test_directories(self):
        """Test custom test directories configuration."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir).resolve()

            # Create custom test structure
            unit_tests_dir = temp_path / "unit_tests"
            unit_tests_dir.mkdir()
            (unit_tests_dir / "test_unit.py").touch()

            integration_tests_dir = temp_path / "integration_tests"
            integration_tests_dir.mkdir()
            (integration_tests_dir / "test_integration.py").touch()

            # Create analyzer with custom test dirs
            analyzer = DependencyAnalyzer(temp_path, test_dirs=["unit_tests", "integration_tests"])
            test_files = analyzer._find_test_files()

            assert len(test_files) == 2
            file_names = {f.name for f in test_files}
            assert file_names == {"test_unit.py", "test_integration.py"}

    def test_plugin_configurable_directories(self):
        """Test plugin with configurable directories."""
        config = Mock()
        config.getoption.side_effect = lambda opt: {
            "--delta-filename": ".delta",
            "--delta-dir": ".",
            "--delta-force": False,
            "--delta-ignore": [],
            "--delta-source-dirs": ["lib", "src"],
            "--delta-test-dirs": ["unit_tests", "integration_tests"],
        }.get(opt, [])

        plugin = DeltaPlugin(config)

        # Check that plugin passes configured dirs to analyzer
        assert plugin.source_dirs == ["lib", "src"]
        assert plugin.test_dirs == ["unit_tests", "integration_tests"]
        assert plugin.dependency_analyzer.source_dirs == ["lib", "src"]
        assert plugin.dependency_analyzer.test_dirs == [
            "unit_tests",
            "integration_tests",
        ]

    def test_plugin_default_directories_when_empty(self):
        """Test plugin uses defaults when empty lists provided."""
        config = Mock()
        config.getoption.side_effect = lambda opt: {
            "--delta-filename": ".delta",
            "--delta-dir": ".",
            "--delta-force": False,
            "--delta-ignore": [],
            "--delta-source-dirs": [],  # Empty list should trigger default
            "--delta-test-dirs": [],  # Empty list should trigger default
        }.get(opt, [])

        plugin = DeltaPlugin(config)

        # Should use defaults when empty lists provided
        assert plugin.source_dirs == [".", "src"]
        assert plugin.test_dirs == ["tests"]

    def test_is_test_file_with_custom_test_dirs(self):
        """Test test file detection with custom test directories."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir).resolve()

            analyzer = DependencyAnalyzer(temp_path, test_dirs=["specs", "unit_tests"])

            # Test files in custom test directories
            test_cases = [
                ("specs/user_spec.py", True),
                ("unit_tests/test_helper.py", True),
                (
                    "tests/test_something.py",
                    True,
                ),  # Still test file due to test_ prefix
                ("src/test_helper.py", True),  # Starts with test_
                ("src/helper_test.py", True),  # Ends with _test.py
                ("src/module.py", False),
                ("other/regular.py", False),
            ]

            for file_path_str, expected in test_cases:
                file_path = temp_path / file_path_str
                is_test = analyzer._is_test_file(file_path, file_path_str)
                assert is_test == expected, (
                    f"Failed for {file_path_str}: expected {expected}, got {is_test}"
                )


class TestUnstagedChangesBugFix:
    """Test cases for the unstaged changes bug fix (issue #25)."""

    def test_resolve_import_to_file_avoids_suffix_false_positives(self):
        """Test that import resolution avoids false positive suffix matches."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create a structure where suffix matching could cause false positives
            src_dir = temp_path / "src"
            tests_dir = temp_path / "tests"
            src_dir.mkdir()
            tests_dir.mkdir()

            # Create source file
            calculator_file = src_dir / "calculator.py"
            calculator_file.write_text("def add(x, y): return x + y")

            # Create test file with similar name that could match incorrectly
            test_calculator_file = tests_dir / "test_calculator.py"
            test_calculator_file.write_text("from calculator import add")

            analyzer = DependencyAnalyzer(temp_path, source_dirs=["src"], test_dirs=["tests"])

            all_files = {calculator_file, test_calculator_file}

            # Test that "calculator" resolves to the correct file, not the test file
            result = analyzer._resolve_import_to_file("calculator", all_files)

            # Should resolve to src/calculator.py, NOT tests/test_calculator.py
            assert result == calculator_file
            assert result != test_calculator_file

    def test_unstaged_changes_with_dependencies(self):
        """Test that unstaged changes to source files correctly affect dependent test files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir).resolve()

            # Initialize git repository
            repo = Repo.init(temp_path)
            repo.config_writer().set_value("user", "name", "Test User").release()
            repo.config_writer().set_value("user", "email", "test@example.com").release()

            # Create project structure
            src_dir = temp_path / "src"
            tests_dir = temp_path / "tests"
            src_dir.mkdir()
            tests_dir.mkdir()

            # Create source file
            calculator_file = src_dir / "calculator.py"
            calculator_file.write_text("def add(x, y):\n    return x + y\n")

            # Create test file that imports from source file
            test_calculator_file = tests_dir / "test_calculator.py"
            test_calculator_file.write_text(
                """
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from calculator import add

def test_add():
    assert add(2, 3) == 5
"""
            )

            # Commit initial version
            repo.index.add([str(calculator_file), str(test_calculator_file)])
            repo.index.commit("Initial commit")

            # Make unstaged change to source file
            calculator_file.write_text("def add(x, y):\n    return x + y + 1\n")

            analyzer = DependencyAnalyzer(temp_path, source_dirs=[".", "src"], test_dirs=["tests"])

            # Build dependency graph
            dependency_graph = analyzer.build_dependency_graph()

            # Test file should depend on source file
            assert test_calculator_file in dependency_graph
            assert calculator_file in dependency_graph[test_calculator_file]

            # When source file changes, test file should be affected
            changed_files = {calculator_file}
            affected_files = analyzer.find_affected_files(changed_files, dependency_graph)

            # Both source and test files should be affected
            assert calculator_file in affected_files
            assert test_calculator_file in affected_files
