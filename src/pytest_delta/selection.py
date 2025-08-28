from __future__ import annotations

from _pytest.nodes import Item

from .graph import DependencyGraph, closure_from_changed


def impacted_tests(
    items: list[Item], changed_paths: set[str], graph: DependencyGraph
) -> set[str]:
    """
    Maps changed files -> impacted files via reverse graph -> keep only test items
    whose underlying file is in the impacted set.

    Simplest heuristic:
        - select a test if its file is impacted OR it directly imports an impacted module/file.
    """
    impacted_files = closure_from_changed(graph, changed_paths)

    selected: set[str] = set()
    for it in items:
        # node paths are absolute FS nodes; normalize through fspath
        try:
            path = str(it.path.resolve())
        except Exception:
            path = it.nodeid.split("::")[0]
        if path in impacted_files:
            selected.add(it.nodeid)

    return selected
