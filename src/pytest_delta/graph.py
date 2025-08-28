from __future__ import annotations

import ast
from pathlib import Path

# A tiny graph type: file -> set of files that depend on it (reverse edges)
DependencyGraph = dict[str, set[str]]

PY_ECTS = {".py"}


def build_dependency_graph(root: str) -> DependencyGraph:
    """
    Very lightweight, file-based reverse dependency graph:
        - parses imports vie AST
        - maps modules to files using naive heuristics
        - returns reverse edges: dependency_file -> {dependant_file, ...}
    """
    root_path = Path(root)
    all_py_files = [
        p
        for p in root_path.rglob("*.py")
        if ".venv" not in p.parts and "site-packages" not in p.parts
    ]

    # forward: file -> imported modules (as strings)
    imports_by_file: dict[str, set[str]] = {}

    for f in all_py_files:
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        except Exception:
            continue  # tolerant parse
        modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for n in node.names:
                    modules.add(n.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    modules.add(node.module.split(".")[0])
        imports_by_file[str(f.resolve())] = modules

    # naive module -> file map from project tree (top-level packages)
    module_to_file: dict[str, str] = {}
    for f in all_py_files:
        name = f.stem
        module_to_file[name] = str(f.resolve())

    # Build reverse graph: for each file, who depends on it
    reverse: DependencyGraph = {}
    for file_path, mods in imports_by_file.items():
        for m in mods:
            dep_file = module_to_file.get(m)
            if not dep_file:
                continue
            reverse.setdefault(dep_file, set()).add(file_path)

    return reverse


def closure_from_changed(
    graph: DependencyGraph, changed_abs_paths: set[str]
) -> set[str]:
    """
    Given reverse dependency graph, return transitive closure of impacted files
    (changed files + all who depend on them, breadth-first).
    """
    impacted = set(changed_abs_paths)
    frontier = list(changed_abs_paths)
    while frontier:
        cur = frontier.pop()
        for dep in graph.get(cur, set()):
            if dep not in impacted:
                impacted.add(dep)
                frontier.append(dep)
    return impacted
