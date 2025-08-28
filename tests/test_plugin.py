"""Test suite for pytest-delta plugin functionality."""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

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
                "version": "0.1.0",
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
    
    @patch("pytest_delta.delta_manager.Repo")
    def test_update_metadata_parent_git_search(self, mock_repo):
        """Test that update_metadata uses search_parent_directories=True."""
        with tempfile.TemporaryDirectory() as temp_dir:
            delta_file = Path(temp_dir) / ".delta.json"
            manager = DeltaManager(delta_file)
            
            # Mock successful repo with commit
            mock_repo_instance = Mock()
            mock_repo_instance.head.commit.hexsha = "abc123"
            mock_repo.return_value = mock_repo_instance
            
            root_dir = Path(temp_dir)
            manager.update_metadata(root_dir)
            
            # Verify that Repo was called with search_parent_directories=True
            mock_repo.assert_called_once_with(root_dir, search_parent_directories=True)


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


class TestDeltaPlugin:
    """Test cases for DeltaPlugin main functionality."""

    @patch("pytest_delta.plugin.Repo")
    def test_plugin_initialization(self, mock_repo):
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

    @patch("pytest_delta.plugin.Repo")
    def test_delta_file_path_construction(self, mock_repo):
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

    @patch("pytest_delta.plugin.Repo")
    def test_no_git_repo_fallback(self, mock_repo):
        """Test fallback when not in a Git repository."""
        from git.exc import InvalidGitRepositoryError

        mock_repo.side_effect = InvalidGitRepositoryError("Not a git repo")

        config = Mock()
        config.getoption.side_effect = lambda opt: {
            "--delta-filename": ".delta",
            "--delta-dir": ".",
            "--delta-force": False,
        }.get(opt, False)

        plugin = DeltaPlugin(config)
        plugin._analyze_changes()

        assert plugin.should_run_all is True

    @patch("pytest_delta.plugin.Repo")
    def test_non_root_git_repo_detection(self, mock_repo):
        """Test that git repository is detected even when .git is in parent directory."""
        from git import Repo
        
        # Mock successful Repo creation to simulate finding git repo in parent
        mock_repo_instance = Mock()
        mock_repo.return_value = mock_repo_instance
        
        config = Mock()
        config.getoption.side_effect = lambda opt: {
            "--delta-filename": ".delta",
            "--delta-dir": ".",
            "--delta-force": False,
        }.get(opt, False)

        plugin = DeltaPlugin(config)
        plugin._analyze_changes()
        
        # Verify that Repo was called with search_parent_directories=True
        mock_repo.assert_called_with(plugin.root_dir, search_parent_directories=True)
        
        # Should not run all tests if git repo is found (but delta file doesn't exist)
        # In this case should_run_all will be True because delta file doesn't exist
        # but the important thing is that no InvalidGitRepositoryError was raised
        assert plugin.should_run_all is True  # Due to missing delta file, not git error

    def test_path_matching(self):
        """Test path matching between test and source files."""
        config = Mock()
        config.getoption.side_effect = lambda opt: {
            "--delta-filename": ".delta",
            "--delta-dir": ".",
            "--delta-force": False,
        }.get(opt, False)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            plugin = DeltaPlugin(config)
            plugin.root_dir = temp_path

            # Create test paths
            test_file = temp_path / "tests" / "test_module.py"
            source_file = temp_path / "src" / "module.py"

            assert plugin._paths_match(test_file, source_file) is True

            # Test non-matching paths
            other_file = temp_path / "src" / "other.py"
            assert plugin._paths_match(test_file, other_file) is False


def test_pytest_integration():
    """Integration test to ensure the plugin can be loaded by pytest."""
    # This test ensures that the plugin entry point is working
    from pytest_delta import plugin

    assert hasattr(plugin, "pytest_addoption")
    assert hasattr(plugin, "pytest_configure")
    assert hasattr(plugin, "DeltaPlugin")
