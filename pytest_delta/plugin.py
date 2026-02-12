from __future__ import annotations

from pathlib import Path

import pytest

from pytest_delta.config import DeltaConfig
from pytest_delta.delta import DeltaData, DeltaFileError, load_delta, save_delta
from pytest_delta.graph import (
    apply_conftest_rule,
    build_forward_graph,
    build_module_map,
    build_reverse_graph,
    compute_hashes,
    discover_py_files,
    get_affected_files,
)


def _is_test_file(rel_path: str) -> bool:
    name = Path(rel_path).name
    return name.startswith("test_") or name.endswith("_test.py")


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("delta", "Delta-based test filtering")
    group.addoption(
        "--delta",
        action="store_true",
        default=False,
        help="Enable delta-based test filtering (only run affected tests).",
    )
    group.addoption(
        "--delta-file",
        action="store",
        default=None,
        help="Path to the delta file (default: .delta.msgpack).",
    )
    group.addoption(
        "--delta-rebuild",
        action="store_true",
        default=False,
        help="Force rebuild the dependency graph from scratch.",
    )
    group.addoption(
        "--delta-no-save",
        action="store_true",
        default=False,
        help="Do not save the delta file after the test run.",
    )
    group.addoption(
        "--delta-debug",
        action="store_true",
        default=False,
        help="Print debug information about delta filtering.",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "delta_always: mark test to always run regardless of file changes.",
    )

    try:
        _configure(config)
    except Exception as e:
        delta_config = getattr(config, "_delta_config", None)
        if delta_config:
            delta_config.debug_print(f"Error during configuration: {e}")
        config._delta_first_run = True


def _configure(config: pytest.Config) -> None:
    delta_config = DeltaConfig.from_pytest_config(config)
    config._delta_config = delta_config  # type: ignore[attr-defined]
    config._delta_first_run = False  # type: ignore[attr-defined]
    config._delta_affected_test_files: set[str] | None = None  # type: ignore[attr-defined]
    config._delta_no_changes = False  # type: ignore[attr-defined]

    if not delta_config.enabled:
        return

    delta_config.debug_print("Plugin enabled")

    # Load existing delta file
    stored: DeltaData | None = None
    if not delta_config.rebuild:
        try:
            stored = load_delta(delta_config.delta_file)
            if stored:
                delta_config.debug_print(
                    f"Loaded delta: {len(stored.file_hashes)} files tracked"
                )
        except DeltaFileError as e:
            delta_config.debug_print(f"Error loading delta: {e}")

    if stored is None:
        delta_config.debug_print("First run -- will run all tests")
        config._delta_first_run = True  # type: ignore[attr-defined]
        return

    # Discover current files and compute hashes
    py_files = discover_py_files(delta_config.root_path)
    current_hashes = compute_hashes(py_files)

    # Compare hashes
    changed: set[str] = set()
    new_files: set[str] = set()
    for path, hash_val in current_hashes.items():
        if path not in stored.file_hashes:
            new_files.add(path)
        elif stored.file_hashes[path] != hash_val:
            changed.add(path)

    deleted = set(stored.file_hashes.keys()) - set(current_hashes.keys())
    all_changed = changed | new_files | deleted

    delta_config.debug_print(
        f"Changed: {len(changed)}, New: {len(new_files)}, Deleted: {len(deleted)}"
    )

    if not all_changed:
        delta_config.debug_print("No changes detected")
        config._delta_affected_test_files = set()  # type: ignore[attr-defined]
        config._delta_no_changes = True  # type: ignore[attr-defined]
        return

    # Build dependency graph
    module_map = build_module_map(py_files)
    forward = build_forward_graph(py_files, module_map)
    reverse = build_reverse_graph(forward)

    # Find affected files
    affected = get_affected_files(all_changed, reverse)

    # Apply conftest rule
    test_files = {p for p in py_files if _is_test_file(p)}
    affected = apply_conftest_rule(all_changed, affected, test_files)

    # Filter to test files only
    affected_test_files = affected & test_files
    # Ensure new test files are included
    new_test_files = {f for f in test_files if f not in stored.file_hashes}
    affected_test_files |= new_test_files

    config._delta_affected_test_files = affected_test_files  # type: ignore[attr-defined]

    # Cache for reuse in sessionfinish
    config._delta_current_hashes = current_hashes  # type: ignore[attr-defined]
    config._delta_forward_graph = forward  # type: ignore[attr-defined]
    config._delta_reverse_graph = reverse  # type: ignore[attr-defined]

    delta_config.debug_print(f"Affected test files: {len(affected_test_files)}")
    if delta_config.debug:
        for f in sorted(affected_test_files):
            delta_config.debug_print(f"  {f}")


def pytest_collection_modifyitems(
    session: pytest.Session,
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    delta_config: DeltaConfig | None = getattr(config, "_delta_config", None)
    if not delta_config or not delta_config.enabled:
        return

    try:
        _filter_items(config, delta_config, items)
    except Exception as e:
        delta_config.debug_print(f"Error during filtering: {e}")


def _filter_items(
    config: pytest.Config,
    delta_config: DeltaConfig,
    items: list[pytest.Item],
) -> None:
    first_run: bool = getattr(config, "_delta_first_run", False)
    if first_run:
        delta_config.debug_print("First run -- running all tests")
        return

    affected_test_files: set[str] | None = getattr(config, "_delta_affected_test_files", None)
    if affected_test_files is None:
        return

    selected: list[pytest.Item] = []
    deselected: list[pytest.Item] = []

    for item in items:
        if item.get_closest_marker("delta_always"):
            selected.append(item)
            continue

        try:
            rel_path = str(Path(item.path).relative_to(delta_config.root_path))
        except ValueError:
            selected.append(item)
            continue

        if rel_path in affected_test_files:
            selected.append(item)
        else:
            deselected.append(item)

    delta_config.debug_print(f"Selected: {len(selected)}, Deselected: {len(deselected)}")

    items[:] = selected
    if deselected:
        config.hook.pytest_deselected(items=deselected)


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    config = session.config
    delta_config: DeltaConfig | None = getattr(config, "_delta_config", None)
    if not delta_config or not delta_config.enabled:
        return

    try:
        _sessionfinish(session, config, delta_config, exitstatus)
    except Exception as e:
        delta_config.debug_print(f"Error during session finish: {e}")


def _sessionfinish(
    session: pytest.Session,
    config: pytest.Config,
    delta_config: DeltaConfig,
    exitstatus: int,
) -> None:
    first_run: bool = getattr(config, "_delta_first_run", False)
    no_changes: bool = getattr(config, "_delta_no_changes", False)

    # Override exit code when no tests needed
    if not first_run and no_changes and exitstatus == 5:
        session.exitstatus = 0
        delta_config.debug_print("No changes detected -- exit 0")
        return

    if delta_config.no_save:
        delta_config.debug_print("Skipping save (--delta-no-save)")
        return

    # Only save on success
    if session.exitstatus != 0:
        delta_config.debug_print(f"Tests failed (exit {session.exitstatus}) -- not saving delta")
        return

    if first_run:
        # Build everything fresh for first save
        py_files = discover_py_files(delta_config.root_path)
        current_hashes = compute_hashes(py_files)
        module_map = build_module_map(py_files)
        forward = build_forward_graph(py_files, module_map)
        reverse = build_reverse_graph(forward)
    else:
        # Reuse cached data from configure
        current_hashes = getattr(config, "_delta_current_hashes", {})
        forward = getattr(config, "_delta_forward_graph", {})
        reverse = getattr(config, "_delta_reverse_graph", {})

    data = DeltaData(
        file_hashes=current_hashes,
        forward_graph=forward,
        reverse_graph=reverse,
    )

    try:
        save_delta(delta_config.delta_file, data)
        delta_config.debug_print(f"Saved delta: {len(current_hashes)} files tracked")
    except DeltaFileError as e:
        delta_config.debug_print(f"Failed to save delta: {e}")
