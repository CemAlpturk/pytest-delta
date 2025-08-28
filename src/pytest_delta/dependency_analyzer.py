"""
Dependency analyzer for pytest-delta plugin.

Creates a directional dependency graph based on Python imports
and determines which files are affected by changes.
"""

import ast
import fnmatch
from pathlib import Path
from typing import Dict, List, Set


class DependencyAnalyzer:
    """Analyzes Python file dependencies based on imports."""

    def __init__(self, root_dir: Path, ignore_patterns: List[str] | None = None):
        self.root_dir = root_dir
        self.ignore_patterns = ignore_patterns or []

    def build_dependency_graph(self) -> Dict[Path, Set[Path]]:
        """
        Build a dependency graph where keys are files and values are sets of files they depend on.

        Returns:
            A dictionary mapping file paths to their dependencies.
        """
        dependency_graph = {}
        python_files = self._find_python_files()

        for file_path in python_files:
            dependencies = self._extract_dependencies(file_path, python_files)
            dependency_graph[file_path] = dependencies

        return dependency_graph

    def find_affected_files(
        self, changed_files: Set[Path], dependency_graph: Dict[Path, Set[Path]]
    ) -> Set[Path]:
        """
        Find all files affected by the given changed files.

        This includes:
        1. The changed files themselves
        2. Files that directly depend on changed files
        3. Files that transitively depend on changed files

        Args:
            changed_files: Set of files that have been modified
            dependency_graph: Dependency graph from build_dependency_graph()

        Returns:
            Set of all files that are potentially affected by the changes
        """
        affected = set(changed_files)

        # Build reverse dependency graph (who depends on whom)
        reverse_deps = self._build_reverse_dependency_graph(dependency_graph)

        # Use BFS to find all files affected transitively
        to_process = list(changed_files)
        processed = set()

        while to_process:
            current_file = to_process.pop(0)
            if current_file in processed:
                continue
            processed.add(current_file)

            # Find files that depend on the current file
            dependents = reverse_deps.get(current_file, set())
            for dependent in dependents:
                if dependent not in processed and dependent not in to_process:
                    affected.add(dependent)
                    to_process.append(dependent)

        return affected

    def _find_python_files(self) -> Set[Path]:
        """Find all Python files in the project."""
        python_files = set()

        # Search in common Python directories
        search_dirs = [
            self.root_dir / "src",
            self.root_dir / "tests",
        ]

        # Also check for Python files in the root directory (but not recursively)
        for file_path in self.root_dir.glob("*.py"):
            if file_path.is_file():
                python_files.add(file_path.resolve())

        for search_dir in search_dirs:
            if search_dir.is_dir():
                python_files.update(search_dir.rglob("*.py"))

        # Filter out __pycache__, .venv, and other irrelevant files
        filtered_files = set()
        exclude_patterns = [
            "__pycache__",
            ".venv",
            "venv",
            ".git",
            "node_modules",
            ".pytest_cache",
        ]

        for file_path in python_files:
            path_str = str(file_path)
            relative_path_str = str(file_path.relative_to(self.root_dir))

            # Skip if any exclude pattern is in the path
            if any(pattern in path_str for pattern in exclude_patterns):
                continue

            # Skip if matches any user-provided ignore patterns
            if self._should_ignore_file(file_path, relative_path_str):
                continue

            if file_path.is_file():
                filtered_files.add(file_path.resolve())

        return filtered_files

    def _extract_dependencies(self, file_path: Path, all_files: Set[Path]) -> Set[Path]:
        """Extract dependencies (imports) from a Python file."""
        dependencies = set()

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except (OSError, UnicodeDecodeError):
            # Skip files that can't be read
            return dependencies

        try:
            tree = ast.parse(content)
        except SyntaxError:
            # Skip files with syntax errors
            return dependencies

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    dep_path = self._resolve_import_to_file(alias.name, all_files)
                    if dep_path:
                        dependencies.add(dep_path)

            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    # Handle relative imports
                    if node.level > 0:  # Relative import
                        module_name = self._resolve_relative_import(
                            file_path, node.module, node.level
                        )
                    else:
                        module_name = node.module

                    if module_name:
                        dep_path = self._resolve_import_to_file(module_name, all_files)
                        if dep_path:
                            dependencies.add(dep_path)

                # Also handle individual imports from modules
                for alias in node.names:
                    if node.module:
                        full_name = f"{node.module}.{alias.name}"
                    else:
                        full_name = alias.name

                    dep_path = self._resolve_import_to_file(full_name, all_files)
                    if dep_path:
                        dependencies.add(dep_path)

        return dependencies

    def _resolve_import_to_file(
        self, import_name: str, all_files: Set[Path]
    ) -> Path | None:
        """Resolve an import name to an actual file path."""
        # Convert module name to potential file paths
        parts = import_name.split(".")

        # Try different combinations to find the file
        potential_paths = []

        # Try as a direct module file
        potential_paths.append(Path(*parts).with_suffix(".py"))

        # Try as a package with __init__.py
        potential_paths.append(Path(*parts) / "__init__.py")

        # Try in src/ directory
        potential_paths.append(Path("src") / Path(*parts) / "__init__.py")
        potential_paths.append((Path("src") / Path(*parts)).with_suffix(".py"))

        # Search for matches in all known files
        for potential_path in potential_paths:
            for file_path in all_files:
                try:
                    # Check if the file path ends with our potential path
                    if file_path.relative_to(self.root_dir) == potential_path:
                        return file_path
                except ValueError:
                    continue

                # Also check suffix matching for nested structures
                if str(file_path).endswith(str(potential_path)):
                    return file_path

        return None

    def _resolve_relative_import(
        self, file_path: Path, module_name: str | None, level: int
    ) -> str | None:
        """Resolve relative imports to absolute module names."""
        try:
            file_rel_path = file_path.relative_to(self.root_dir)
        except ValueError:
            return None

        # Remove the file name to get the directory
        current_dir_parts = list(file_rel_path.parent.parts)

        # Remove 'level' number of directories
        if level > len(current_dir_parts):
            return None

        base_parts = current_dir_parts[:-level] if level > 0 else current_dir_parts

        if module_name:
            module_parts = module_name.split(".")
            full_parts = base_parts + module_parts
        else:
            full_parts = base_parts

        return ".".join(full_parts) if full_parts else None

    def _build_reverse_dependency_graph(
        self, dependency_graph: Dict[Path, Set[Path]]
    ) -> Dict[Path, Set[Path]]:
        """Build reverse dependency graph (who depends on whom)."""
        reverse_deps = {}

        for file_path, dependencies in dependency_graph.items():
            for dependency in dependencies:
                if dependency not in reverse_deps:
                    reverse_deps[dependency] = set()
                reverse_deps[dependency].add(file_path)

        return reverse_deps

    def _should_ignore_file(self, file_path: Path, relative_path_str: str) -> bool:
        """Check if a file should be ignored based on user-provided patterns."""
        if not self.ignore_patterns:
            return False

        # Check against both absolute path and relative path
        absolute_path_str = str(file_path)

        for pattern in self.ignore_patterns:
            # Use fnmatch for glob-style pattern matching
            if fnmatch.fnmatch(relative_path_str, pattern):
                return True
            if fnmatch.fnmatch(absolute_path_str, pattern):
                return True
            # Also check if pattern is simply contained in the path
            if pattern in relative_path_str or pattern in absolute_path_str:
                return True

        return False
