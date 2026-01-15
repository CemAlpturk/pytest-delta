"""Pytest plugin hooks for pytest-delta."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from .config import DeltaConfig
from .delta import DeltaData, DeltaFileError, load_delta, save_delta
from .git import GitError, get_changed_files, get_current_commit, is_git_repository
from .graph import DependencyGraph

if TYPE_CHECKING:
    from _pytest.terminal import TerminalReporter


# Marker name for tests that should always run
ALWAYS_RUN_MARKER = "delta_always"


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add command-line options for pytest-delta."""
    group = parser.getgroup("delta", "pytest-delta: test filtering based on changes")

    group.addoption(
        "--delta",
        action="store_true",
        default=False,
        help="Enable delta filtering (only run tests affected by changes)",
    )

    group.addoption(
        "--delta-file",
        action="store",
        default=None,
        metavar="PATH",
        help="Path to delta file (default: .delta.msgpack in project root)",
    )

    group.addoption(
        "--delta-debug",
        action="store_true",
        default=False,
        help="Display detailed debug information including dependency graph statistics",
    )

    group.addoption(
        "--delta-pass-if-no-tests",
        action="store_true",
        default=False,
        help="Exit with code 0 when no tests need to be run due to no changes",
    )

    group.addoption(
        "--delta-no-save",
        action="store_true",
        default=False,
        help="Skip updating the delta file after tests (read-only mode for CI/CD)",
    )

    group.addoption(
        "--delta-ignore",
        action="append",
        default=[],
        metavar="PATTERN",
        help="Ignore file patterns during dependency analysis (can be used multiple times)",
    )

    group.addoption(
        "--delta-rebuild",
        action="store_true",
        default=False,
        help="Force rebuild of the dependency graph",
    )


def pytest_configure(config: pytest.Config) -> None:
    """Configure the plugin and compute affected files.

    This hook runs on both the controller and workers in xdist.
    All computation here must be deterministic.
    """
    # Register the marker
    config.addinivalue_line(
        "markers",
        f"{ALWAYS_RUN_MARKER}: mark test to always run regardless of file changes",
    )

    # Create config object
    delta_config = DeltaConfig.from_pytest_config(config)

    # Store on config for later access
    config._delta_config = delta_config  # type: ignore[attr-defined]
    config._delta_affected_files: set[str] | None = None  # type: ignore[attr-defined]
    config._delta_current_commit: str = ""  # type: ignore[attr-defined]
    config._delta_graph: DependencyGraph | None = None  # type: ignore[attr-defined]
    config._delta_run_all: bool = False  # type: ignore[attr-defined]
    config._delta_no_tests_needed: bool = False  # type: ignore[attr-defined]

    if not delta_config.enabled:
        return

    delta_config.debug_print("Plugin enabled")

    # Check if we're in a git repository
    if not is_git_repository(delta_config.root_path):
        delta_config.debug_print("Not a git repository, running all tests")
        config._delta_run_all = True  # type: ignore[attr-defined]
        return

    try:
        # Get current commit
        current_commit = get_current_commit(delta_config.root_path)
        config._delta_current_commit = current_commit  # type: ignore[attr-defined]
        delta_config.debug_print(f"Current commit: {current_commit[:12]}")

        # Load existing delta file
        delta_data: DeltaData | None = None
        existing_graph: DependencyGraph | None = None

        if not delta_config.rebuild:
            try:
                delta_data = load_delta(delta_config.delta_file, delta_config)
                if delta_data:
                    existing_graph = delta_data.graph
            except DeltaFileError as e:
                delta_config.debug_print(f"Error loading delta file: {e}")

        # Build/update dependency graph
        graph = existing_graph if existing_graph else DependencyGraph()
        graph.build(
            delta_config.root_path, delta_config, force_rebuild=delta_config.rebuild
        )
        config._delta_graph = graph  # type: ignore[attr-defined]

        # Determine changed files
        if delta_data and delta_data.last_passed_commit:
            try:
                changed_files = get_changed_files(
                    delta_data.last_passed_commit,
                    delta_config.root_path,
                )
                delta_config.debug_print(f"Changed files: {len(changed_files)}")

                if delta_config.debug:
                    for f in sorted(changed_files)[:10]:
                        delta_config.debug_print(f"  - {f}")
                    if len(changed_files) > 10:
                        delta_config.debug_print(
                            f"  ... and {len(changed_files) - 10} more"
                        )

                # Filter to only Python files and apply ignore patterns
                changed_py_files = {
                    f
                    for f in changed_files
                    if f.endswith(".py") and not delta_config.should_ignore(f)
                }

                if not changed_py_files:
                    delta_config.debug_print("No Python files changed, no tests needed")
                    config._delta_no_tests_needed = True  # type: ignore[attr-defined]
                    config._delta_affected_files = set()  # type: ignore[attr-defined]
                else:
                    # Get affected files
                    affected_files = graph.get_affected_files(changed_py_files)
                    config._delta_affected_files = affected_files  # type: ignore[attr-defined]
                    delta_config.debug_print(f"Affected files: {len(affected_files)}")

                    if delta_config.debug:
                        for f in sorted(affected_files)[:10]:
                            delta_config.debug_print(f"  - {f}")
                        if len(affected_files) > 10:
                            delta_config.debug_print(
                                f"  ... and {len(affected_files) - 10} more"
                            )

            except GitError as e:
                delta_config.debug_print(f"Git error: {e}")
                delta_config.debug_print("Running all tests")
                config._delta_run_all = True  # type: ignore[attr-defined]
        else:
            delta_config.debug_print("No previous delta file, running all tests")
            config._delta_run_all = True  # type: ignore[attr-defined]

    except GitError as e:
        delta_config.debug_print(f"Git error during setup: {e}")
        config._delta_run_all = True  # type: ignore[attr-defined]
    except DeltaFileError as e:
        delta_config.debug_print(f"Delta file error: {e}")
        config._delta_run_all = True  # type: ignore[attr-defined]


def pytest_collection_modifyitems(
    session: pytest.Session,
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    """Filter tests based on affected files.

    This hook runs on each worker in xdist, so filtering must be deterministic.
    """
    delta_config: DeltaConfig = getattr(config, "_delta_config", None)  # type: ignore[assignment]

    if not delta_config or not delta_config.enabled:
        return

    run_all: bool = getattr(config, "_delta_run_all", False)
    if run_all:
        delta_config.debug_print("Running all tests (no filtering)")
        return

    affected_files: set[str] | None = getattr(config, "_delta_affected_files", None)
    if affected_files is None:
        return

    selected: list[pytest.Item] = []
    deselected: list[pytest.Item] = []

    for item in items:
        # Check for always_run marker
        if item.get_closest_marker(ALWAYS_RUN_MARKER):
            selected.append(item)
            continue

        # Get the test file path relative to root
        test_path = Path(item.fspath) if hasattr(item, "fspath") else Path(item.path)
        try:
            rel_path = str(test_path.relative_to(delta_config.root_path))
        except ValueError:
            # File is outside the project root, include it
            selected.append(item)
            continue

        # Check if this test file or any of its dependencies are affected
        if rel_path in affected_files:
            selected.append(item)
        elif _test_depends_on_affected(rel_path, affected_files, config):
            selected.append(item)
        else:
            deselected.append(item)

    delta_config.debug_print(
        f"Selected {len(selected)} tests, deselected {len(deselected)} tests"
    )

    # Apply the filtering
    items[:] = selected

    if deselected:
        config.hook.pytest_deselected(items=deselected)


def _test_depends_on_affected(
    test_file: str,
    affected_files: set[str],
    config: pytest.Config,
) -> bool:
    """Check if a test file depends on any affected files.

    Args:
        test_file: Relative path to the test file.
        affected_files: Set of affected file paths.
        config: Pytest config object.

    Returns:
        True if the test depends on any affected file.
    """
    graph: DependencyGraph | None = getattr(config, "_delta_graph", None)
    if not graph:
        return True  # If no graph, be conservative

    # Get what this test file imports
    dependencies = graph.forward_graph.get(test_file, set())

    # Check if any dependency is affected
    for dep in dependencies:
        if dep in affected_files:
            return True

        # Also check transitive dependencies of the test file
        transitive_deps = graph.forward_graph.get(dep, set())
        if transitive_deps & affected_files:
            return True

    return False


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> int | None:
    """Save the delta file if tests passed and modify exit status if needed.

    This only runs on the controller/master in xdist.
    """
    config = session.config
    delta_config: DeltaConfig = getattr(config, "_delta_config", None)  # type: ignore[assignment]

    if not delta_config or not delta_config.enabled:
        return None

    # Don't save if running in xdist worker mode
    if hasattr(config, "workerinput"):
        return None

    # Check if we should modify exit status
    no_tests_needed: bool = getattr(config, "_delta_no_tests_needed", False)
    should_force_pass = (
        no_tests_needed
        and delta_config.pass_if_no_tests
        and exitstatus == 5  # pytest.ExitCode.NO_TESTS_COLLECTED
    )

    if should_force_pass:
        session.exitstatus = 0  # type: ignore[assignment]

    # Check if we should save
    if delta_config.no_save:
        delta_config.debug_print("Skipping delta file save (--delta-no-save)")
        return 0 if should_force_pass else None

    # Only save if tests passed (exitstatus 0) or no tests collected with force pass
    effective_exit = session.exitstatus
    if effective_exit == 0 or (exitstatus == 5 and no_tests_needed):
        current_commit: str = getattr(config, "_delta_current_commit", "")
        graph: DependencyGraph | None = getattr(config, "_delta_graph", None)

        if current_commit and graph:
            try:
                save_delta(delta_config.delta_file, current_commit, graph, delta_config)
                delta_config.debug_print(
                    f"Delta file saved with commit {current_commit[:12]}"
                )
            except DeltaFileError as e:
                delta_config.debug_print(f"Failed to save delta file: {e}")
    else:
        delta_config.debug_print(
            f"Tests did not pass (exitstatus={exitstatus}), delta file not updated"
        )


@pytest.hookimpl(trylast=True)
def pytest_sessionstart(session: pytest.Session) -> None:
    """Handle the case where no tests need to run."""
    config = session.config
    delta_config: DeltaConfig = getattr(config, "_delta_config", None)  # type: ignore[assignment]

    if not delta_config or not delta_config.enabled:
        return

    no_tests_needed: bool = getattr(config, "_delta_no_tests_needed", False)

    if no_tests_needed and delta_config.pass_if_no_tests:
        delta_config.debug_print("No tests needed and --delta-pass-if-no-tests is set")


@pytest.hookimpl(trylast=True)
def pytest_terminal_summary(
    terminalreporter: TerminalReporter,
    exitstatus: int,
    config: pytest.Config,
) -> None:
    """Add delta summary to terminal output."""
    delta_config: DeltaConfig = getattr(config, "_delta_config", None)  # type: ignore[assignment]

    if not delta_config or not delta_config.enabled:
        return

    no_tests_needed: bool = getattr(config, "_delta_no_tests_needed", False)

    if no_tests_needed:
        terminalreporter.write_sep("=", "pytest-delta: no changes detected")
        terminalreporter.write_line(
            "No Python files changed since last successful run."
        )

        if delta_config.pass_if_no_tests:
            terminalreporter.write_line(
                "Exiting with success (--delta-pass-if-no-tests)."
            )


# Hook to modify exit status when no tests needed
@pytest.hookimpl(trylast=True)
def pytest_collection_finish(session: pytest.Session) -> None:
    """Check if we should exit early with success."""
    config = session.config
    delta_config: DeltaConfig = getattr(config, "_delta_config", None)  # type: ignore[assignment]

    if not delta_config or not delta_config.enabled:
        return

    no_tests_needed: bool = getattr(config, "_delta_no_tests_needed", False)

    if no_tests_needed and delta_config.pass_if_no_tests and len(session.items) == 0:
        # Force exit status to 0 by setting a flag
        config._delta_force_pass = True  # type: ignore[attr-defined]
