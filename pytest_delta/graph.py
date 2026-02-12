from __future__ import annotations

import ast
import hashlib
from collections import deque
from pathlib import Path

SKIP_DIRS = frozenset({
    ".venv",
    "venv",
    ".env",
    "env",
    "__pycache__",
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "build",
    "dist",
    ".eggs",
    ".tox",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
})


def compute_file_hash(file_path: Path) -> str:
    h = hashlib.sha256(file_path.read_bytes())
    return h.hexdigest()[:16]


def discover_py_files(root: Path) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for path in root.rglob("*.py"):
        # Skip files in excluded directories
        parts = path.relative_to(root).parts
        if any(part in SKIP_DIRS or part.startswith(".") for part in parts[:-1]):
            continue
        rel = str(path.relative_to(root))
        result[rel] = path
    return result


def compute_hashes(files: dict[str, Path]) -> dict[str, str]:
    return {rel: compute_file_hash(abs_path) for rel, abs_path in files.items()}


def extract_imports(file_path: Path, rel_path: str) -> set[str]:
    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return set()

    imports: set[str] = set()
    # Compute the package parts for resolving relative imports
    rel_parts = Path(rel_path).parts

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                # Absolute import
                if node.module:
                    imports.add(node.module)
            else:
                # Relative import: resolve using file's package position
                # For a file at pkg/sub/mod.py, the package is ["pkg", "sub"]
                # For __init__.py at pkg/sub/__init__.py, the package is ["pkg", "sub"]
                if rel_parts[-1] == "__init__.py":
                    package_parts = list(rel_parts[:-1])
                else:
                    package_parts = list(rel_parts[:-1])

                # Go up `level` packages
                # level=1 means current package, level=2 means parent, etc.
                up = node.level - 1
                if up > len(package_parts):
                    continue  # Invalid relative import, skip
                if up > 0:
                    package_parts = package_parts[:-up]

                if node.module:
                    resolved = ".".join(package_parts + [node.module]) if package_parts else node.module
                else:
                    resolved = ".".join(package_parts) if package_parts else None

                if resolved:
                    imports.add(resolved)

    return imports


def build_module_map(py_files: dict[str, Path]) -> dict[str, str]:
    module_map: dict[str, str] = {}
    for rel_path in py_files:
        parts = Path(rel_path).parts
        # Convert path to module name
        if parts[-1] == "__init__.py":
            # Package: pkg/sub/__init__.py -> pkg.sub
            module_parts = parts[:-1]
        else:
            # Module: pkg/sub/mod.py -> pkg.sub.mod
            module_parts = parts[:-1] + (parts[-1].removesuffix(".py"),)

        if module_parts:
            module_name = ".".join(module_parts)
            module_map[module_name] = rel_path

            # Also register without src. prefix for projects using src layout
            if module_parts[0] == "src" and len(module_parts) > 1:
                alt_name = ".".join(module_parts[1:])
                module_map.setdefault(alt_name, rel_path)

    return module_map


def resolve_import(module_name: str, module_map: dict[str, str]) -> str | None:
    # Exact match
    if module_name in module_map:
        return module_map[module_name]
    # Try progressively shorter prefixes (from X.Y.Z import something -> try X.Y, then X)
    parts = module_name.split(".")
    for i in range(len(parts) - 1, 0, -1):
        prefix = ".".join(parts[:i])
        if prefix in module_map:
            return module_map[prefix]
    return None


def _get_init_files_for_import(resolved_path: str, py_files: dict[str, Path]) -> set[str]:
    """Get all __init__.py files along the path of an import."""
    parts = Path(resolved_path).parts
    init_files: set[str] = set()
    for i in range(1, len(parts)):
        init_path = str(Path(*parts[:i]) / "__init__.py")
        if init_path in py_files:
            init_files.add(init_path)
    return init_files


def build_forward_graph(
    py_files: dict[str, Path], module_map: dict[str, str]
) -> dict[str, set[str]]:
    forward: dict[str, set[str]] = {rel: set() for rel in py_files}
    for rel_path, abs_path in py_files.items():
        imports = extract_imports(abs_path, rel_path)
        for module_name in imports:
            resolved = resolve_import(module_name, module_map)
            if resolved and resolved != rel_path:
                forward[rel_path].add(resolved)
                # Also add __init__.py files along the import path
                for init_file in _get_init_files_for_import(resolved, py_files):
                    if init_file != rel_path:
                        forward[rel_path].add(init_file)
    return forward


def build_reverse_graph(forward: dict[str, set[str]]) -> dict[str, set[str]]:
    # Build direct reverse edges
    direct_reverse: dict[str, set[str]] = {k: set() for k in forward}
    for file, deps in forward.items():
        for dep in deps:
            if dep not in direct_reverse:
                direct_reverse[dep] = set()
            direct_reverse[dep].add(file)

    # Compute transitive closure via BFS from each node
    reverse: dict[str, set[str]] = {}
    for start in direct_reverse:
        visited: set[str] = set()
        queue = deque(direct_reverse.get(start, set()))
        while queue:
            node = queue.popleft()
            if node in visited:
                continue
            visited.add(node)
            queue.extend(direct_reverse.get(node, set()) - visited)
        reverse[start] = visited

    return reverse


def get_affected_files(changed: set[str], reverse: dict[str, set[str]]) -> set[str]:
    affected = set(changed)
    for file in changed:
        affected |= reverse.get(file, set())
    return affected


def apply_conftest_rule(
    changed_files: set[str], affected: set[str], all_test_files: set[str]
) -> set[str]:
    result = set(affected)
    for changed_file in changed_files:
        if Path(changed_file).name == "conftest.py":
            # Get the directory of the conftest
            conftest_dir = str(Path(changed_file).parent)
            if conftest_dir == ".":
                # Root conftest: affects all tests
                result |= all_test_files
            else:
                # Subdirectory conftest: affects tests in that subtree
                prefix = conftest_dir + "/"
                result |= {t for t in all_test_files if t.startswith(prefix)}
    return result
