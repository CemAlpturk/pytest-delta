"""
pytest-delta plugin for running only tests impacted by code changes.

This plugin creates a directional dependency graph based on imports and selects
only the tests that are potentially affected by the changed files.
"""

from pathlib import Path
from typing import List, Set

import pytest
from git import Repo
from git.exc import GitCommandError, InvalidGitRepositoryError

from .dependency_analyzer import DependencyAnalyzer
from .delta_manager import DeltaManager


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add command line options for pytest-delta."""
    group = parser.getgroup("delta", "pytest-delta options")
    group.addoption(
        "--delta",
        action="store_true",
        default=False,
        help="Run only tests impacted by code changes since last successful run",
    )
    group.addoption(
        "--delta-filename",
        action="store",
        default=".delta",
        help="Filename for the delta metadata file (default: .delta, .json extension added automatically)",
    )
    group.addoption(
        "--delta-dir",
        action="store",
        default=".",
        help="Directory to store the delta metadata file (default: current directory)",
    )
    group.addoption(
        "--delta-force",
        action="store_true",
        default=False,
        help="Force regeneration of the delta file and run all tests",
    )
    group.addoption(
        "--delta-ignore",
        action="append",
        default=[],
        help="Ignore file patterns during dependency analysis (can be used multiple times)",
    )


def pytest_configure(config: pytest.Config) -> None:
    """Configure the plugin if --delta flag is used."""
    if config.getoption("--delta"):
        config.pluginmanager.register(DeltaPlugin(config), "delta-plugin")


class DeltaPlugin:
    """Main plugin class for pytest-delta functionality."""

    def __init__(self, config: pytest.Config):
        self.config = config
        # Construct delta file path from filename and directory
        delta_filename = config.getoption("--delta-filename")
        delta_dir = config.getoption("--delta-dir")

        # Ensure filename has .json extension
        if not delta_filename.endswith(".json"):
            delta_filename += ".json"

        self.delta_file = Path(delta_dir) / delta_filename
        self.force_regenerate = config.getoption("--delta-force")
        self.ignore_patterns = config.getoption("--delta-ignore")
        self.root_dir = Path.cwd()
        self.delta_manager = DeltaManager(self.delta_file)
        self.dependency_analyzer = DependencyAnalyzer(
            self.root_dir, ignore_patterns=self.ignore_patterns
        )
        self.affected_files: Set[Path] = set()
        self.should_run_all = False

    def pytest_collection_modifyitems(
        self, config: pytest.Config, items: List[pytest.Item]
    ) -> None:
        """Modify the collected test items to only include affected tests."""
        try:
            # Try to determine which files are affected
            self._analyze_changes()

            if self.should_run_all:
                # Run all tests and regenerate delta file
                self._print_info("Running all tests (regenerating delta file)")
                return

            if not self.affected_files:
                # No changes detected, skip all tests
                self._print_info("No changes detected, skipping all tests")
                items.clear()
                return

            # Filter tests based on affected files
            original_count = len(items)
            items[:] = self._filter_affected_tests(items)
            filtered_count = len(items)

            self._print_info(
                f"Selected {filtered_count}/{original_count} tests based on code changes"
            )

            if filtered_count > 0:
                affected_files_str = ", ".join(
                    str(f.relative_to(self.root_dir))
                    for f in sorted(self.affected_files)
                )
                self._print_info(f"Affected files: {affected_files_str}")

        except Exception as e:
            self._print_warning(f"Error in delta analysis: {e}")
            self._print_warning("Running all tests as fallback")
            self.should_run_all = True

    def pytest_sessionfinish(self, session: pytest.Session, exitstatus: int) -> None:
        """Update delta metadata after test session completion."""
        if exitstatus == 0:  # Tests passed successfully
            try:
                self.delta_manager.update_metadata(self.root_dir)
                self._print_info("Delta metadata updated successfully")
            except Exception as e:
                self._print_warning(f"Failed to update delta metadata: {e}")

    def _analyze_changes(self) -> None:
        """Analyze what files have changed and determine affected files."""
        try:
            repo = Repo(self.root_dir)
        except InvalidGitRepositoryError:
            self._print_warning("Not a Git repository, running all tests")
            self.should_run_all = True
            return

        if self.force_regenerate or not self.delta_file.exists():
            self._print_info("Delta file not found or force regeneration requested")
            self.should_run_all = True
            return

        try:
            # Load previous metadata
            metadata = self.delta_manager.load_metadata()
            if not metadata or "last_commit" not in metadata:
                self._print_warning("Invalid delta metadata, running all tests")
                self.should_run_all = True
                return

            last_commit = metadata["last_commit"]

            # Get changed files since last commit
            try:
                changed_files = self._get_changed_files(repo, last_commit)
            except GitCommandError as e:
                self._print_warning(f"Git error: {e}")
                self._print_warning("Running all tests")
                self.should_run_all = True
                return

            if not changed_files:
                # No changes detected
                return

            # Build dependency graph and find affected files
            dependency_graph = self.dependency_analyzer.build_dependency_graph()
            self.affected_files = self.dependency_analyzer.find_affected_files(
                changed_files, dependency_graph
            )

        except Exception as e:
            self._print_warning(f"Error analyzing changes: {e}")
            self.should_run_all = True

    def _get_changed_files(self, repo: Repo, last_commit: str) -> Set[Path]:
        """Get list of files changed since the last commit."""
        changed_files = set()

        try:
            # Get committed changes
            diff = repo.commit(last_commit).diff("HEAD")
            for item in diff:
                if item.a_path:
                    file_path = self.root_dir / item.a_path
                    if file_path.suffix == ".py":
                        changed_files.add(file_path)
                if item.b_path:
                    file_path = self.root_dir / item.b_path
                    if file_path.suffix == ".py":
                        changed_files.add(file_path)
        except GitCommandError:
            # Last commit might not exist, compare with HEAD
            pass

        # Get uncommitted changes (staged and unstaged)
        try:
            # Staged changes
            diff_staged = repo.index.diff("HEAD")
            for item in diff_staged:
                if item.a_path:
                    file_path = self.root_dir / item.a_path
                    if file_path.suffix == ".py":
                        changed_files.add(file_path)
                if item.b_path:
                    file_path = self.root_dir / item.b_path
                    if file_path.suffix == ".py":
                        changed_files.add(file_path)

            # Unstaged changes
            diff_unstaged = repo.index.diff(None)
            for item in diff_unstaged:
                if item.a_path:
                    file_path = self.root_dir / item.a_path
                    if file_path.suffix == ".py":
                        changed_files.add(file_path)
                if item.b_path:
                    file_path = self.root_dir / item.b_path
                    if file_path.suffix == ".py":
                        changed_files.add(file_path)
        except GitCommandError:
            pass

        return changed_files

    def _filter_affected_tests(self, items: List[pytest.Item]) -> List[pytest.Item]:
        """Filter test items to only include those affected by changes."""
        affected_tests = []

        for item in items:
            test_file = Path(item.fspath)

            # Check if the test file itself is affected
            if test_file in self.affected_files:
                affected_tests.append(item)
                continue

            # Check if the test file tests any affected source files
            if self._test_covers_affected_files(test_file):
                affected_tests.append(item)

        return affected_tests

    def _test_covers_affected_files(self, test_file: Path) -> bool:
        """Check if a test file covers any of the affected source files."""
        # Simple heuristic: match test file path with source file path
        # test_something.py -> something.py
        # tests/test_module.py -> src/module.py or module.py

        test_name = test_file.name
        if test_name.startswith("test_"):
            source_name = test_name[5:]  # Remove 'test_' prefix
        else:
            return False

        # Look for corresponding source files in affected files
        for affected_file in self.affected_files:
            if affected_file.name == source_name:
                return True
            # Also check if the test directory structure matches source structure
            if self._paths_match(test_file, affected_file):
                return True

        return False

    def _paths_match(self, test_file: Path, source_file: Path) -> bool:
        """Check if test file path corresponds to source file path."""
        # Convert paths to relative and normalize
        try:
            test_rel = test_file.relative_to(self.root_dir)
            source_rel = source_file.relative_to(self.root_dir)
        except ValueError:
            return False

        # Simple matching logic:
        # tests/test_module.py matches src/module.py
        # tests/subdir/test_module.py matches src/subdir/module.py
        test_parts = list(test_rel.parts)
        source_parts = list(source_rel.parts)

        if len(test_parts) != len(source_parts):
            return False

        for i, (test_part, source_part) in enumerate(zip(test_parts, source_parts)):
            if i == 0:  # First part: tests vs src
                if test_part == "tests" and source_part == "src":
                    continue
                elif test_part == source_part:
                    continue
                else:
                    return False
            elif i == len(test_parts) - 1:  # Last part: filename
                if test_part.startswith("test_") and test_part[5:] == source_part:
                    return True
                else:
                    return False
            else:  # Middle parts: should match exactly
                if test_part != source_part:
                    return False

        return False

    def _print_info(self, message: str) -> None:
        """Print informational message."""
        print(f"[pytest-delta] {message}")

    def _print_warning(self, message: str) -> None:
        """Print warning message."""
        print(f"[pytest-delta] WARNING: {message}")
