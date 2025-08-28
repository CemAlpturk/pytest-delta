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
            delta_file = Path(temp_dir) / ".delta"
            manager = DeltaManager(delta_file)
            
            metadata = {
                "last_commit": "abc123",
                "last_successful_run": True,
                "version": "0.1.0"
            }
            
            manager.save_metadata(metadata)
            loaded_metadata = manager.load_metadata()
            
            assert loaded_metadata == metadata
    
    def test_load_nonexistent_file(self):
        """Test loading metadata from non-existent file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            delta_file = Path(temp_dir) / "nonexistent.delta"
            manager = DeltaManager(delta_file)
            
            result = manager.load_metadata()
            assert result is None
    
    def test_load_invalid_json(self):
        """Test loading metadata from invalid JSON file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            delta_file = Path(temp_dir) / ".delta"
            
            # Create invalid JSON file
            with open(delta_file, 'w') as f:
                f.write("invalid json content")
            
            manager = DeltaManager(delta_file)
            
            with pytest.raises(ValueError, match="Failed to load delta metadata"):
                manager.load_metadata()


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
                module_c: set()
            }
            
            analyzer = DependencyAnalyzer(temp_path)
            
            # Change module_c, should affect module_b and module_a
            changed_files = {module_c}
            affected = analyzer.find_affected_files(changed_files, dependency_graph)
            
            assert affected == {module_a, module_b, module_c}


class TestDeltaPlugin:
    """Test cases for DeltaPlugin main functionality."""
    
    @patch('pytest_delta.plugin.Repo')
    def test_plugin_initialization(self, mock_repo):
        """Test plugin initialization."""
        config = Mock()
        config.getoption.side_effect = lambda opt: {
            "--delta-file": ".delta",
            "--delta-force": False
        }.get(opt, False)
        
        plugin = DeltaPlugin(config)
        
        assert plugin.delta_file.name == ".delta"
        assert plugin.force_regenerate is False
        assert not plugin.should_run_all
    
    @patch('pytest_delta.plugin.Repo')
    def test_no_git_repo_fallback(self, mock_repo):
        """Test fallback when not in a Git repository."""
        mock_repo.side_effect = Exception("Not a git repo")
        
        config = Mock()
        config.getoption.side_effect = lambda opt: {
            "--delta-file": ".delta",
            "--delta-force": False
        }.get(opt, False)
        
        plugin = DeltaPlugin(config)
        plugin._analyze_changes()
        
        assert plugin.should_run_all is True
    
    def test_path_matching(self):
        """Test path matching between test and source files."""
        config = Mock()
        config.getoption.side_effect = lambda opt: {
            "--delta-file": ".delta",
            "--delta-force": False
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
    
    assert hasattr(plugin, 'pytest_addoption')
    assert hasattr(plugin, 'pytest_configure')
    assert hasattr(plugin, 'DeltaPlugin')
