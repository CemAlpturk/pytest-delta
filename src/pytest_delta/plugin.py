"""
pytest-delta plugin for running only tests impacted by code changes.

This plugin creates a directional dependency graph based on imports and selects
only the tests that are potentially affected by the changed files.
"""

from pathlib import Path
from typing import List, Set

import pytest

from .dependency_analyzer import DependencyAnalyzer
from .delta_manager import DeltaManager
from .git_helper import GitCommandError, GitHelper, NotAGitRepositoryError
from .visualizer import DependencyVisualizer


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
    group.addoption(
        "--delta-vis",
        action="store_true",
        default=False,
        help="Generate a visual representation of the project's dependency graph",
    )
    group.addoption(
        "--delta-source-dirs",
        action="append",
        default=[],
        help="Source directories to search for Python files (default: project root and src/). Can be used multiple times.",
    )
    group.addoption(
        "--delta-test-dirs",
        action="append",
        default=[],
        help="Test directories to search for test files (default: tests). Can be used multiple times.",
    )
    group.addoption(
        "--delta-debug",
        action="store_true",
        default=False,
        help="Display detailed debug information about changed files, affected files, and selected tests",
    )
    group.addoption(
        "--delta-pass-if-no-tests",
        action="store_true",
        default=False,
        help="Exit with code 0 (success) instead of 5 when no tests need to be run due to no changes",
    )
    group.addoption(
        "--delta-no-save",
        action="store_true",
        default=False,
        help="Skip updating the delta file after tests complete (read-only mode for CI/CD)",
    )


def pytest_configure(config: pytest.Config) -> None:
    """Configure the plugin if --delta flag is used."""
    if (
        config.getoption("--delta")
        or config.getoption("--delta-vis")
        or config.getoption("--delta-debug")
    ):
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
        self.enable_visualization = config.getoption("--delta-vis")
        self.debug = config.getoption("--delta-debug")
        self.pass_if_no_tests = config.getoption("--delta-pass-if-no-tests")
        self.no_save = config.getoption("--delta-no-save")

        # Get configurable directories with backwards compatible defaults
        self.source_dirs = config.getoption("--delta-source-dirs") or [".", "src"]
        self.test_dirs = config.getoption("--delta-test-dirs") or ["tests"]

        self.root_dir = Path.cwd().resolve()
        self.delta_manager = DeltaManager(self.delta_file)
        self.dependency_analyzer = DependencyAnalyzer(
            self.root_dir,
            ignore_patterns=self.ignore_patterns,
            source_dirs=self.source_dirs,
            test_dirs=self.test_dirs,
        )
        self.visualizer = DependencyVisualizer(self.root_dir)
        self.affected_files: Set[Path] = set()
        self.changed_test_files: Set[Path] = set()
        self.should_run_all = False

        # Debug information storage
        self.changed_source_files: Set[Path] = set()
        self.all_changed_files: Set[Path] = set()

        # Track if no tests were run due to delta analysis
        self.no_tests_due_to_delta = False

    def pytest_collection_modifyitems(
        self, config: pytest.Config, items: List[pytest.Item]
    ) -> None:
        """Modify the collected test items to only include affected tests."""
        try:
            # Generate visualization if requested
            if self.enable_visualization:
                self._generate_visualization()

            # Only proceed with delta analysis if --delta is enabled
            if not config.getoption("--delta"):
                return

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
                self.no_tests_due_to_delta = True
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
                self._print_debug(f"Affected files: {affected_files_str}")

            # Debug information
            if self.debug:
                self._print_debug_analysis_results()

        except Exception as e:
            self._print_warning(f"Error in delta analysis: {e}")
            self._print_warning("Running all tests as fallback")
            self.should_run_all = True

    def _is_xdist_worker(self, session: pytest.Session) -> bool:
        """Check if running as a pytest-xdist worker process."""
        return hasattr(session.config, "workerinput")

    def _is_xdist_controller(self, session: pytest.Session) -> bool:
        """Check if running as a pytest-xdist controller process."""
        return (
            hasattr(session.config, "workeroutput")
            or session.config.pluginmanager.hasplugin("xdist")
            and not self._is_xdist_worker(session)
        )

    def pytest_sessionfinish(self, session: pytest.Session, exitstatus: int) -> None:
        """Update delta metadata after test session completion."""
        # Skip saving on xdist worker processes - only controller should save
        if self._is_xdist_worker(session):
            return

        # Handle exit code override for no tests scenario
        if (
            self.pass_if_no_tests
            and self.no_tests_due_to_delta
            and session.testscollected == 0
            and exitstatus == pytest.ExitCode.NO_TESTS_COLLECTED
        ):
            session.exitstatus = pytest.ExitCode.OK
            self._print_info(
                "No tests were required due to no changes - exiting with success code 0"
            )

        if exitstatus == 0:  # Tests passed successfully
            if not self.no_save:
                try:
                    # Save dependency graph along with metadata if available
                    if hasattr(self, "dependency_graph") and hasattr(
                        self, "file_hashes"
                    ):
                        self.delta_manager.update_metadata(
                            self.root_dir, self.dependency_graph, self.file_hashes
                        )
                    else:
                        self.delta_manager.update_metadata(self.root_dir)
                    self._print_info("Delta metadata updated successfully")
                except Exception as e:
                    self._print_warning(f"Failed to update delta metadata: {e}")
            else:
                self._print_info(
                    "Delta metadata update skipped (--delta-no-save enabled)"
                )

    def _analyze_changes(self) -> None:
        """Analyze what files have changed and determine affected files."""
        try:
            git_helper = GitHelper(self.root_dir, search_parent_directories=True)
        except NotAGitRepositoryError:
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
                changed_files = self._get_changed_files(git_helper, last_commit)
            except GitCommandError as e:
                self._print_warning(f"Git error: {e}")
                self._print_warning("Running all tests")
                self.should_run_all = True
                return

            if not changed_files:
                # No changes detected
                self._print_debug("No changed files detected since last commit")
                return

            # Separate source files from test files in the changed files
            source_files = self.dependency_analyzer._find_source_files()
            test_files = self.dependency_analyzer._find_test_files()

            changed_source_files = {f for f in changed_files if f in source_files}
            changed_test_files = {f for f in changed_files if f in test_files}

            # Build dependency graph - use incremental if possible
            previous_graph_data = self.delta_manager.load_dependency_graph(
                self.root_dir
            )

            if previous_graph_data is not None and not self.force_regenerate:
                # Use incremental update
                previous_graph, previous_hashes = previous_graph_data
                (
                    dependency_graph,
                    reparsed_files,
                    file_hashes,
                ) = self.dependency_analyzer.build_dependency_graph_incremental(
                    previous_graph, previous_hashes
                )
                self._print_debug(
                    f"Incremental graph update: reparsed {len(reparsed_files)} files"
                )
            else:
                # Full rebuild
                dependency_graph = self.dependency_analyzer.build_dependency_graph()
                # Compute file hashes for next time
                file_hashes = {}
                for file_path in dependency_graph.keys():
                    file_hash = self.dependency_analyzer._get_file_hash(file_path)
                    if file_hash:
                        file_hashes[file_path] = file_hash

            # Find all files affected by the changes (including test files that depend on changed source files)
            all_changed_files = changed_source_files | changed_test_files
            affected_files = self.dependency_analyzer.find_affected_files(
                all_changed_files, dependency_graph
            )

            # Store for later use
            self.dependency_graph = dependency_graph
            self.file_hashes = file_hashes
            self.affected_files = affected_files
            self.changed_test_files = changed_test_files
            self.changed_source_files = changed_source_files
            self.all_changed_files = all_changed_files

        except Exception as e:
            self._print_warning(f"Error analyzing changes: {e}")
            self.should_run_all = True

    def _get_changed_files(self, git_helper: GitHelper, last_commit: str) -> Set[Path]:
        """
        Get list of files changed since the last commit.

        Uses GitHelper for fast git operations via subprocess.

        Args:
            git_helper: GitHelper instance
            last_commit: Last commit hash to compare against

        Returns:
            Set of changed Python file paths
        """
        # Get all changes (committed, staged, and unstaged)
        return git_helper.get_all_changes(from_commit=last_commit)

    def _filter_affected_tests(self, items: List[pytest.Item]) -> List[pytest.Item]:
        """Filter test items to only include those affected by changes."""
        affected_tests = []

        for item in items:
            test_file = Path(item.fspath)

            # Check if the test file itself was changed directly
            if test_file in self.changed_test_files:
                affected_tests.append(item)
                continue

            # Check if the test file is affected by changes (now includes dependency tracking)
            if test_file in self.affected_files:
                affected_tests.append(item)

        return affected_tests

    def _generate_visualization(self) -> None:
        """Generate dependency graph visualization."""
        try:
            self._print_info("Generating dependency graph visualization...")

            # Build the dependency graph (or reuse if already built)
            if hasattr(self, "dependency_graph"):
                dependency_graph = self.dependency_graph
            else:
                dependency_graph = self.dependency_analyzer.build_dependency_graph()

            # Generate console output for immediate feedback
            console_output = self.visualizer.generate_console_output(dependency_graph)
            print("\n" + console_output)

            # Save DOT format file
            dot_file = self.visualizer.save_visualization(
                dependency_graph, format="dot"
            )
            self._print_info(f"DOT format saved to: {dot_file}")

            # Save text summary
            txt_file = self.visualizer.save_visualization(
                dependency_graph, format="txt"
            )
            self._print_info(f"Text summary saved to: {txt_file}")

            self._print_info("Visualization complete!")

        except Exception as e:
            self._print_warning(f"Failed to generate visualization: {e}")

    def _print_debug_analysis_results(self) -> None:
        """Print detailed debug information about the analysis results."""
        if not self.debug:
            return

        # Print directory search debug information first
        self.dependency_analyzer.print_directory_debug_info(self._print_debug)

        self._print_debug("=== Delta Analysis Debug Information ===")

        # Changed files breakdown
        if self.all_changed_files:
            self._print_debug(f"Total changed files: {len(self.all_changed_files)}")

            if self.changed_source_files:
                source_files_str = ", ".join(
                    str(f.relative_to(self.root_dir))
                    for f in sorted(self.changed_source_files)
                )
                self._print_debug(
                    f"Changed source files ({len(self.changed_source_files)}): {source_files_str}"
                )
            else:
                self._print_debug("Changed source files: None")

            if self.changed_test_files:
                test_files_str = ", ".join(
                    str(f.relative_to(self.root_dir))
                    for f in sorted(self.changed_test_files)
                )
                self._print_debug(
                    f"Changed test files ({len(self.changed_test_files)}): {test_files_str}"
                )
            else:
                self._print_debug("Changed test files: None")
        else:
            self._print_debug("No files changed")

        # Affected files (result of dependency analysis)
        if self.affected_files:
            affected_files_str = ", ".join(
                str(f.relative_to(self.root_dir)) for f in sorted(self.affected_files)
            )
            self._print_debug(
                f"Files affected by changes ({len(self.affected_files)}): {affected_files_str}"
            )
        else:
            self._print_debug("No files affected by changes")

        # Test files that will be run
        try:
            # Get all Python test files to understand the filtering
            all_test_files = self.dependency_analyzer._find_test_files()
            selected_test_files = set()

            # Determine which test files will be selected
            for test_file in all_test_files:
                if (
                    test_file in self.changed_test_files
                    or test_file in self.affected_files
                ):
                    selected_test_files.add(test_file)

            if selected_test_files:
                selected_test_files_str = ", ".join(
                    str(f.relative_to(self.root_dir))
                    for f in sorted(selected_test_files)
                )
                self._print_debug(
                    f"Test files to be run ({len(selected_test_files)}): {selected_test_files_str}"
                )
            else:
                self._print_debug("No test files will be run")

        except Exception as e:
            self._print_debug(f"Error determining selected test files: {e}")

        self._print_debug("=== End Debug Information ===")

    def _print_info(self, message: str) -> None:
        """Print informational message."""
        print(f"[pytest-delta] {message}")

    def _print_warning(self, message: str) -> None:
        """Print warning message."""
        print(f"[pytest-delta] WARNING: {message}")

    def _print_debug(self, message: str) -> None:
        """Print debug message if debug mode is enabled."""
        if self.debug:
            print(f"[pytest-delta] DEBUG: {message}")
