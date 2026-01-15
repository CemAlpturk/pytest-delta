"""Dependency graph builder using AST analysis."""

from __future__ import annotations

import ast
import hashlib
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import DeltaConfig


def compute_file_hash(file_path: Path) -> str:
    """Compute a SHA-256 hash of a file's contents.

    Args:
        file_path: Path to the file.

    Returns:
        The first 16 characters of the SHA-256 hash.
    """
    content = file_path.read_bytes()
    return hashlib.sha256(content).hexdigest()[:16]


def extract_imports(file_path: Path) -> set[str]:
    """Extract all import statements from a Python file.

    Args:
        file_path: Path to the Python file.

    Returns:
        A set of full module paths that are imported.
    """
    try:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(file_path))
    except (SyntaxError, UnicodeDecodeError):
        # Skip files that can't be parsed
        return set()

    imports: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                # Keep the full module path
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                # Keep the full module path
                imports.add(node.module)

    return imports


def resolve_module_to_file(
    module_name: str,
    python_files: dict[str, Path],
    root_path: Path,
) -> Path | None:
    """Resolve a module name to a file path.

    Args:
        module_name: The module name to resolve.
        python_files: Dict mapping relative paths to absolute paths.
        root_path: The project root path.

    Returns:
        The resolved file path, or None if not found in the project.
    """
    # Try different possible file locations
    possible_paths = [
        f"{module_name}.py",
        f"{module_name}/__init__.py",
        f"src/{module_name}.py",
        f"src/{module_name}/__init__.py",
    ]

    for possible_path in possible_paths:
        if possible_path in python_files:
            return python_files[possible_path]

    return None


class DependencyGraph:
    """A dependency graph built from static import analysis.

    Attributes:
        forward_graph: Maps file -> set of files it imports.
        reverse_graph: Maps file -> set of files that import it (transitively).
        file_hashes: Maps file -> content hash for cache invalidation.
    """

    def __init__(self) -> None:
        """Initialize an empty dependency graph."""
        # Maps: relative_path -> set of relative_paths it directly imports
        self.forward_graph: dict[str, set[str]] = defaultdict(set)
        # Maps: relative_path -> set of relative_paths that depend on it (transitive)
        self.reverse_graph: dict[str, set[str]] = defaultdict(set)
        # Maps: relative_path -> content hash
        self.file_hashes: dict[str, str] = {}

    def build(
        self,
        root_path: Path,
        config: DeltaConfig,
        force_rebuild: bool = False,
    ) -> None:
        """Build the dependency graph from Python files.

        This method can work incrementally if the graph already has data.
        Only files with changed hashes will be reprocessed.

        Args:
            root_path: The project root path.
            config: The delta configuration.
            force_rebuild: If True, rebuild the entire graph from scratch.
        """
        existing_hashes = {} if force_rebuild else dict(self.file_hashes)

        if force_rebuild:
            # Clear existing data
            self.forward_graph.clear()
            self.reverse_graph.clear()
            self.file_hashes.clear()

        # Find all Python files
        python_files = self._discover_python_files(root_path, config)

        config.debug_print(f"Found {len(python_files)} Python files")

        # Remove files that no longer exist
        existing_files_to_remove = set(self.file_hashes.keys()) - set(
            python_files.keys()
        )
        for old_file in existing_files_to_remove:
            self.file_hashes.pop(old_file, None)
            self.forward_graph.pop(old_file, None)

        # Build file hashes and determine which files need reprocessing
        files_to_process: set[str] = set()

        for rel_path, abs_path in python_files.items():
            current_hash = compute_file_hash(abs_path)

            if existing_hashes.get(rel_path) != current_hash:
                files_to_process.add(rel_path)

            self.file_hashes[rel_path] = current_hash

        config.debug_print(
            f"Processing {len(files_to_process)} changed files "
            f"(rebuild={force_rebuild})"
        )

        # Build module name to file mapping for import resolution
        module_map = self._build_module_map(python_files, root_path)

        # Process each file that needs updating
        for rel_path in files_to_process:
            abs_path = python_files[rel_path]
            imports = extract_imports(abs_path)

            # Resolve imports to file paths
            self.forward_graph[rel_path] = set()
            for module_name in imports:
                resolved = self._resolve_import(module_name, module_map, rel_path)
                if resolved:
                    self.forward_graph[rel_path].add(resolved)

        # Build the transitive reverse graph
        self._build_reverse_graph()

        config.debug_print(
            f"Graph built: {len(self.forward_graph)} files, "
            f"{sum(len(deps) for deps in self.reverse_graph.values())} dependencies"
        )

    def _discover_python_files(
        self,
        root_path: Path,
        config: DeltaConfig,
    ) -> dict[str, Path]:
        """Discover all Python files in the project.

        Args:
            root_path: The project root path.
            config: The delta configuration.

        Returns:
            Dict mapping relative paths to absolute paths.
        """
        python_files: dict[str, Path] = {}

        for abs_path in root_path.rglob("*.py"):
            # Skip common non-source directories
            parts = abs_path.relative_to(root_path).parts
            if any(
                part.startswith(".")
                or part
                in (
                    "venv",
                    ".venv",
                    "env",
                    ".env",
                    "__pycache__",
                    "node_modules",
                    "build",
                    "dist",
                    ".git",
                )
                for part in parts
            ):
                continue

            rel_path = str(abs_path.relative_to(root_path))

            # Check ignore patterns
            if config.should_ignore(rel_path):
                continue

            python_files[rel_path] = abs_path

        return python_files

    def _build_module_map(
        self,
        python_files: dict[str, Path],
        root_path: Path,
    ) -> dict[str, str]:
        """Build a mapping from module names to file paths.

        Args:
            python_files: Dict mapping relative paths to absolute paths.
            root_path: The project root path.

        Returns:
            Dict mapping module names to relative file paths.
        """
        module_map: dict[str, str] = {}

        for rel_path in python_files:
            path = Path(rel_path)

            # Handle regular modules (foo.py -> foo)
            if path.name != "__init__.py":
                # Remove .py extension and convert path separators
                module_name = (
                    str(path.with_suffix("")).replace("/", ".").replace("\\", ".")
                )
                module_map[module_name] = rel_path

                # Also map without src/ prefix if present
                if module_name.startswith("src."):
                    module_map[module_name[4:]] = rel_path
            else:
                # Handle packages (foo/__init__.py -> foo)
                package_path = path.parent
                module_name = str(package_path).replace("/", ".").replace("\\", ".")
                if module_name:
                    module_map[module_name] = rel_path

                    # Also map without src/ prefix if present
                    if module_name.startswith("src."):
                        module_map[module_name[4:]] = rel_path

        return module_map

    def _resolve_import(
        self,
        module_name: str,
        module_map: dict[str, str],
        importing_file: str,
    ) -> str | None:
        """Resolve an import to a file path within the project.

        Args:
            module_name: The imported module name.
            module_map: Mapping from module names to file paths.
            importing_file: The file doing the import (for relative imports).

        Returns:
            The resolved relative file path, or None if external.
        """
        # Try exact match first
        if module_name in module_map:
            return module_map[module_name]

        # Try as a submodule (import foo might be foo.bar.baz)
        for mapped_module, file_path in module_map.items():
            if mapped_module.startswith(module_name + "."):
                # This is a submodule, but we want the top-level package
                # Return the __init__.py of the top-level package if it exists
                parts = mapped_module.split(".")
                for i in range(len(parts)):
                    prefix = ".".join(parts[: i + 1])
                    if prefix in module_map:
                        return module_map[prefix]

        return None

    def _build_reverse_graph(self) -> None:
        """Build the transitive reverse dependency graph."""
        # First, build direct reverse graph
        direct_reverse: dict[str, set[str]] = defaultdict(set)
        for file_path, dependencies in self.forward_graph.items():
            for dep in dependencies:
                direct_reverse[dep].add(file_path)

        # Now compute transitive closure
        self.reverse_graph = defaultdict(set)

        for file_path in direct_reverse:
            # BFS to find all files that transitively depend on this file
            visited: set[str] = set()
            queue = list(direct_reverse[file_path])

            while queue:
                current = queue.pop(0)
                if current in visited:
                    continue
                visited.add(current)

                # Add files that directly depend on current
                for dep in direct_reverse.get(current, []):
                    if dep not in visited:
                        queue.append(dep)

            self.reverse_graph[file_path] = visited

    def get_affected_files(self, changed_files: set[str]) -> set[str]:
        """Get all files affected by changes to the given files.

        Args:
            changed_files: Set of files that have changed.

        Returns:
            Set of all files that are affected (including the changed files).
        """
        affected: set[str] = set(changed_files)

        for changed_file in changed_files:
            # Add all files that depend on the changed file
            affected.update(self.reverse_graph.get(changed_file, set()))

        return affected

    def to_dict(self) -> dict:
        """Serialize the graph to a dictionary.

        Returns:
            A dictionary representation of the graph.
        """
        return {
            "forward": {k: list(v) for k, v in self.forward_graph.items()},
            "reverse": {k: list(v) for k, v in self.reverse_graph.items()},
            "hashes": self.file_hashes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> DependencyGraph:
        """Deserialize a graph from a dictionary.

        Args:
            data: A dictionary representation of the graph.

        Returns:
            A DependencyGraph instance.
        """
        graph = cls()
        graph.forward_graph = defaultdict(
            set, {k: set(v) for k, v in data.get("forward", {}).items()}
        )
        graph.reverse_graph = defaultdict(
            set, {k: set(v) for k, v in data.get("reverse", {}).items()}
        )
        graph.file_hashes = data.get("hashes", {})
        return graph
