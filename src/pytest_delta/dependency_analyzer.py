"""
Dependency analyzer for pytest-delta plugin.

Creates a directional dependency graph based on Python imports
and determines which files are affected by changes.
"""

import ast
import fnmatch
import hashlib
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Set, Tuple


class DependencyAnalyzer:
    """Analyzes Python file dependencies based on imports."""

    # Regex patterns for fast import detection
    _IMPORT_REGEX = re.compile(
        r"^\s*(?:from\s+([.\w]+)\s+)?import\s+(.+?)(?:\s+as\s+\w+)?(?:\s*[#\n]|$)",
        re.MULTILINE,
    )

    # Patterns that indicate a file needs full AST parsing
    _COMPLEX_PATTERNS = [
        "try:",
        "except",
        "if __name__",
        "exec(",
        "eval(",
        "__import__(",
        "importlib",
    ]

    def __init__(
        self,
        root_dir: Path,
        ignore_patterns: List[str] | None = None,
        source_dirs: List[str] | None = None,
        test_dirs: List[str] | None = None,
    ):
        self.root_dir = root_dir
        self.ignore_patterns = ignore_patterns or []
        self.source_dirs = source_dirs or [".", "src"]
        self.test_dirs = test_dirs or ["tests"]

        # Cache for file hashes and parsed dependencies
        self._file_hash_cache: Dict[Path, str] = {}
        self._dependency_cache: Dict[str, Set[Path]] = {}

        # Debug information storage
        self._debug_info: Dict[str, Any] = {
            "configured_source_dirs": self.source_dirs.copy(),
            "configured_test_dirs": self.test_dirs.copy(),
            "searched_dirs": [],
            "skipped_dirs": [],
            "excluded_files": [],
            "ignored_files": [],
            "directory_file_counts": {},
            "cache_hits": 0,
            "cache_misses": 0,
            "regex_fast_path": 0,
            "ast_full_parse": 0,
            "incremental_added_files": 0,
            "incremental_removed_files": 0,
            "incremental_modified_files": 0,
            "incremental_reparsed_files": 0,
            "incremental_reused_files": 0,
        }

    def build_dependency_graph(self) -> Dict[Path, Set[Path]]:
        """
        Build a dependency graph where keys are files and values are sets of files they depend on.

        Includes both source files and test files in the dependency graph to enable
        accurate test selection based on actual imports.

        Returns:
            A dictionary mapping file paths to their dependencies.
        """
        dependency_graph = {}
        source_files = self._find_source_files()
        test_files = self._find_test_files()
        all_files = source_files | test_files
        all_python_files = self._find_python_files()

        for file_path in all_files:
            dependencies = self._extract_dependencies(file_path, all_python_files)
            # Filter dependencies to only include files in our tracked set (source + test files)
            tracked_dependencies = {dep for dep in dependencies if dep in all_files}
            dependency_graph[file_path] = tracked_dependencies

        return dependency_graph

    def build_dependency_graph_incremental(
        self,
        previous_graph: Dict[Path, set[Path]],
        previous_hashes: Dict[Path, str],
    ) -> tuple[Dict[Path, set[Path]], set[Path], Dict[Path, str]]:
        """
        Build dependency graph incrementally by only reparsing changed files.

        This method provides significant performance improvements when only a few files
        have changed by:
        1. Detecting which files have been added, removed, or modified
        2. Only reparsing those files and files that depend on them
        3. Reusing the previous graph for unchanged files

        Args:
            previous_graph: Previously computed dependency graph
            previous_hashes: File hashes from when previous_graph was built

        Returns:
            Tuple of (new_dependency_graph, reparsed_files_set, new_file_hashes)
        """
        # Find current files
        source_files = self._find_source_files()
        test_files = self._find_test_files()
        all_files = source_files | test_files
        all_python_files = self._find_python_files()

        # Track what changed
        current_hashes = {}
        changed_files = set()
        added_files = set()
        removed_files = set()

        # Compute current hashes and detect changes
        for file_path in all_files:
            current_hash = self._get_file_hash(file_path)
            if current_hash is None:
                continue

            current_hashes[file_path] = current_hash

            if file_path not in previous_hashes:
                # New file
                added_files.add(file_path)
                changed_files.add(file_path)
            elif previous_hashes[file_path] != current_hash:
                # Modified file
                changed_files.add(file_path)

        # Detect removed files
        for file_path in previous_hashes:
            if file_path not in all_files:
                removed_files.add(file_path)

        # Build reverse dependency graph to find affected files
        reverse_deps = self._build_reverse_dependency_graph(previous_graph)

        # Find all files that need reparsing:
        # 1. Changed files themselves
        # 2. Files that import changed files (direct dependents)
        # 3. Files that transitively depend on changed files
        files_to_reparse = set(changed_files)

        # Add direct and transitive dependents of changed files
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
                if dependent in all_files and dependent not in processed:
                    files_to_reparse.add(dependent)
                    to_process.append(dependent)

        # Build new graph incrementally
        new_graph = {}

        # Copy unchanged files from previous graph
        for file_path in all_files:
            if file_path not in files_to_reparse and file_path in previous_graph:
                # File hasn't changed and doesn't depend on changed files
                # Reuse dependencies from previous graph, but filter to current files
                old_deps = previous_graph[file_path]
                new_graph[file_path] = {dep for dep in old_deps if dep in all_files}

        # Reparse changed files and their dependents
        for file_path in files_to_reparse:
            if file_path in all_files:  # Skip removed files
                dependencies = self._extract_dependencies(file_path, all_python_files)
                tracked_dependencies = {dep for dep in dependencies if dep in all_files}
                new_graph[file_path] = tracked_dependencies

        # Track statistics
        self._debug_info["incremental_added_files"] = len(added_files)
        self._debug_info["incremental_removed_files"] = len(removed_files)
        self._debug_info["incremental_modified_files"] = len(changed_files - added_files)
        self._debug_info["incremental_reparsed_files"] = len(files_to_reparse)
        self._debug_info["incremental_reused_files"] = len(all_files) - len(files_to_reparse)

        return new_graph, files_to_reparse, current_hashes

    def get_debug_info(self) -> Dict[str, Any]:
        """Return debug information collected during analysis."""
        return self._debug_info.copy()

    def _get_file_hash(self, file_path: Path) -> str | None:
        """
        Compute MD5 hash of file contents for caching purposes.

        Args:
            file_path: Path to the file to hash

        Returns:
            MD5 hash string, or None if file cannot be read
        """
        # Check if hash is already cached
        if file_path in self._file_hash_cache:
            return self._file_hash_cache[file_path]

        try:
            with open(file_path, "rb") as f:
                content = f.read()
                file_hash = hashlib.md5(content).hexdigest()
                self._file_hash_cache[file_path] = file_hash
                return file_hash
        except (OSError, IOError):
            return None

    def _get_cached_dependencies(
        self, file_path: Path, all_files: Set[Path]
    ) -> Tuple[Set[Path], bool]:
        """
        Get dependencies from cache if file hasn't changed, otherwise parse the file.

        Args:
            file_path: Path to the file to analyze
            all_files: Set of all files in the project

        Returns:
            Tuple of (dependencies set, cache_hit boolean)
        """
        file_hash = self._get_file_hash(file_path)
        if file_hash is None:
            return set(), False

        # Create cache key combining file path and hash
        cache_key = f"{file_path}:{file_hash}"

        # Check if we have cached dependencies for this file hash
        if cache_key in self._dependency_cache:
            self._debug_info["cache_hits"] += 1
            return self._dependency_cache[cache_key], True

        # Cache miss - need to parse the file
        self._debug_info["cache_misses"] += 1
        dependencies = self._parse_file_dependencies(file_path, all_files)

        # Store in cache
        self._dependency_cache[cache_key] = dependencies

        return dependencies, False

    def _parse_file_dependencies(self, file_path: Path, all_files: Set[Path]) -> Set[Path]:
        """
        Parse a Python file and extract its dependencies.
        This is the actual parsing logic separated from caching.

        Args:
            file_path: Path to the file to parse
            all_files: Set of all files in the project

        Returns:
            Set of file paths that this file depends on
        """
        dependencies: Set[Path] = set()

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except (OSError, UnicodeDecodeError):
            # Skip files that can't be read
            return dependencies

        # Try fast path: regex-based import detection for simple files
        if not self._has_complex_patterns(content):
            module_names = self._quick_scan_imports(content)
            if module_names is not None:
                # Fast path succeeded
                self._debug_info["regex_fast_path"] += 1
                for module_name in module_names:
                    dep_path = self._resolve_import_to_file(module_name, all_files)
                    if dep_path:
                        dependencies.add(dep_path)
                return dependencies

        # Fall back to full AST parsing for complex files
        self._debug_info["ast_full_parse"] += 1

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
                    resolved_module: str | None
                    if node.level > 0:  # Relative import
                        resolved_module = self._resolve_relative_import(
                            file_path, node.module, node.level
                        )
                    else:
                        resolved_module = node.module

                    if resolved_module:
                        dep_path = self._resolve_import_to_file(resolved_module, all_files)
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

    def _has_complex_patterns(self, content: str) -> bool:
        """
        Check if file content contains patterns that require full AST parsing.

        Args:
            content: File content to analyze

        Returns:
            True if file needs AST parsing, False if regex is sufficient
        """
        # Check for complex patterns that regex can't handle reliably
        for pattern in self._COMPLEX_PATTERNS:
            if pattern in content:
                return True
        return False

    def _quick_scan_imports(self, content: str) -> Set[str] | None:
        """
        Fast regex-based import detection for simple files.

        Returns a set of module names if successful, None if AST parsing is needed.

        Args:
            content: File content to scan

        Returns:
            Set of imported module names, or None if full AST parsing is required
        """
        # Check if this file needs full AST parsing
        if self._has_complex_patterns(content):
            return None

        imports: Set[str] = set()

        # Find all import statements using regex
        for match in self._IMPORT_REGEX.finditer(content):
            from_module = match.group(1)  # The module after 'from'
            import_part = match.group(2)  # The module/names after 'import'

            if from_module:
                # from module import something
                imports.add(from_module)
            else:
                # import module or import module, module2
                # Split by comma and get the first module name
                for item in import_part.split(","):
                    module_name = item.strip().split()[0]  # Get name before 'as'
                    if module_name:
                        imports.add(module_name)

        return imports

    def print_directory_debug_info(self, print_func: Callable[[str], None]) -> None:
        """Print detailed directory search debug information."""
        debug_info = self._debug_info

        print_func("=== Directory Search Debug Information ===")

        # Configured directories
        print_func(f"Configured source directories: {debug_info['configured_source_dirs']}")
        print_func(f"Configured test directories: {debug_info['configured_test_dirs']}")

        # Directories actually searched
        if debug_info["searched_dirs"]:
            print_func(
                f"Directories searched ({len(debug_info['searched_dirs'])}): {', '.join(debug_info['searched_dirs'])}"
            )
        else:
            print_func("Directories searched: None")

        # Directories skipped (don't exist)
        if debug_info["skipped_dirs"]:
            print_func(
                f"Directories skipped (not found) ({len(debug_info['skipped_dirs'])}): {', '.join(debug_info['skipped_dirs'])}"
            )

        # File counts per directory
        if debug_info["directory_file_counts"]:
            print_func("Files found per directory:")
            for dir_name, count in sorted(debug_info["directory_file_counts"].items()):
                print_func(f"  {dir_name}: {count} files")

        # Excluded files (by built-in patterns)
        if debug_info["excluded_files"]:
            excluded_summary = (
                f"{len(debug_info['excluded_files'])} files excluded by built-in patterns"
            )
            if len(debug_info["excluded_files"]) <= 5:
                print_func(f"{excluded_summary}: {', '.join(debug_info['excluded_files'])}")
            else:
                print_func(
                    f"{excluded_summary} (showing first 5): {', '.join(debug_info['excluded_files'][:5])}"
                )

        # Ignored files (by user patterns)
        if debug_info["ignored_files"]:
            ignored_summary = f"{len(debug_info['ignored_files'])} files ignored by user patterns"
            if len(debug_info["ignored_files"]) <= 5:
                print_func(f"{ignored_summary}: {', '.join(debug_info['ignored_files'])}")
            else:
                print_func(
                    f"{ignored_summary} (showing first 5): {', '.join(debug_info['ignored_files'][:5])}"
                )

        # User ignore patterns (if any)
        if self.ignore_patterns:
            print_func(f"User ignore patterns: {self.ignore_patterns}")

        # Cache statistics
        total_cache_requests = debug_info["cache_hits"] + debug_info["cache_misses"]
        if total_cache_requests > 0:
            hit_rate = (debug_info["cache_hits"] / total_cache_requests) * 100
            print_func(
                f"Cache statistics: {debug_info['cache_hits']} hits, "
                f"{debug_info['cache_misses']} misses ({hit_rate:.1f}% hit rate)"
            )

        # Parsing method statistics
        total_parses = debug_info["regex_fast_path"] + debug_info["ast_full_parse"]
        if total_parses > 0:
            regex_rate = (debug_info["regex_fast_path"] / total_parses) * 100
            print_func(
                f"Parsing methods: {debug_info['regex_fast_path']} regex fast path, "
                f"{debug_info['ast_full_parse']} AST full parse ({regex_rate:.1f}% fast path)"
            )

        # Incremental update statistics
        total_reparsed = debug_info["incremental_reparsed_files"]
        total_reused = debug_info["incremental_reused_files"]
        if total_reparsed > 0 or total_reused > 0:
            print_func("\n=== Incremental Update Statistics ===")
            print_func(f"Added files: {debug_info['incremental_added_files']}")
            print_func(f"Removed files: {debug_info['incremental_removed_files']}")
            print_func(f"Modified files: {debug_info['incremental_modified_files']}")
            print_func(f"Files reparsed: {total_reparsed}")
            print_func(f"Files reused from cache: {total_reused}")

            total_files = total_reparsed + total_reused
            if total_files > 0:
                reuse_rate = (total_reused / total_files) * 100
                print_func(f"Cache reuse rate: {reuse_rate:.1f}%")

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

        # Reset debug info for this search
        self._debug_info.update(
            {
                "searched_dirs": [],
                "skipped_dirs": [],
                "excluded_files": [],
                "ignored_files": [],
                "directory_file_counts": {},
            }
        )

        # Search in configured source and test directories
        search_dirs = []
        for source_dir in self.source_dirs:
            search_dirs.append(self.root_dir / source_dir)
        for test_dir in self.test_dirs:
            search_dirs.append(self.root_dir / test_dir)

        for search_dir in search_dirs:
            if search_dir.is_dir():
                self._debug_info["searched_dirs"].append(str(search_dir.relative_to(self.root_dir)))
                files_found_in_dir = 0

                # If search_dir is the root directory, only get .py files directly in root (not recursive)
                if search_dir == self.root_dir:
                    for file_path in search_dir.glob("*.py"):
                        if file_path.is_file():
                            python_files.add(file_path.resolve())
                            files_found_in_dir += 1
                else:
                    # For subdirectories, search recursively
                    found_files = set(search_dir.rglob("*.py"))
                    python_files.update(found_files)
                    files_found_in_dir = len(found_files)

                # Store directory file count
                dir_name = (
                    str(search_dir.relative_to(self.root_dir))
                    if search_dir != self.root_dir
                    else "."
                )
                self._debug_info["directory_file_counts"][dir_name] = files_found_in_dir
            else:
                # Directory doesn't exist or isn't a directory
                self._debug_info["skipped_dirs"].append(str(search_dir.relative_to(self.root_dir)))

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
            excluded = False
            for pattern in exclude_patterns:
                if pattern in path_str:
                    self._debug_info["excluded_files"].append(relative_path_str)
                    excluded = True
                    break

            if excluded:
                continue

            # Skip if matches any user-provided ignore patterns
            if self._should_ignore_file(file_path, relative_path_str):
                self._debug_info["ignored_files"].append(relative_path_str)
                continue

            if file_path.is_file():
                filtered_files.add(file_path.resolve())

        return filtered_files

    def _find_source_files(self) -> Set[Path]:
        """Find all Python source files in the project, excluding test files."""
        source_files = set()

        # Search in configured source directories
        for source_dir in self.source_dirs:
            search_dir = self.root_dir / source_dir
            if search_dir.is_dir():
                # If search_dir is the root directory, only get .py files directly in root (not recursive)
                if search_dir == self.root_dir:
                    for file_path in search_dir.glob("*.py"):
                        if file_path.is_file():
                            source_files.add(file_path.resolve())
                else:
                    # For subdirectories, search recursively
                    source_files.update(search_dir.rglob("*.py"))

        # Filter out __pycache__, .venv, test files and other irrelevant files
        filtered_files = set()
        exclude_patterns = [
            "__pycache__",
            ".venv",
            "venv",
            ".git",
            "node_modules",
            ".pytest_cache",
        ]

        for file_path in source_files:
            path_str = str(file_path)
            relative_path_str = str(file_path.relative_to(self.root_dir))

            # Skip if any exclude pattern is in the path
            if any(pattern in path_str for pattern in exclude_patterns):
                continue

            # Skip test files - any file with "test" in its path or name
            if self._is_test_file(file_path, relative_path_str):
                continue

            # Skip if matches any user-provided ignore patterns
            if self._should_ignore_file(file_path, relative_path_str):
                continue

            if file_path.is_file():
                filtered_files.add(file_path.resolve())

        return filtered_files

    def _find_test_files(self) -> Set[Path]:
        """Find all Python test files in the project."""
        test_files = set()

        # Get all python files and filter for test files
        all_python_files = self._find_python_files()
        for file_path in all_python_files:
            try:
                relative_path_str = str(file_path.relative_to(self.root_dir))
                if self._is_test_file(file_path, relative_path_str):
                    test_files.add(file_path)
            except ValueError:
                # Skip files that are not under root_dir
                continue

        return test_files

    def _is_test_file(self, file_path: Path, relative_path_str: str) -> bool:
        """Determine if a file is a test file."""
        # Check if file is in configured test directories
        for test_dir in self.test_dirs:
            test_path = test_dir.rstrip("/") + "/"
            if test_path in relative_path_str or relative_path_str.startswith(test_dir):
                return True

        # If no custom test directories match, also check filename patterns
        # Check if filename starts with "test_"
        if file_path.name.startswith("test_"):
            return True

        # Check if filename ends with "_test.py"
        if file_path.name.endswith("_test.py"):
            return True

        return False

    def _extract_dependencies(self, file_path: Path, all_files: Set[Path]) -> Set[Path]:
        """
        Extract dependencies (imports) from a Python file.
        Uses caching to avoid re-parsing unchanged files.

        Args:
            file_path: Path to the file to analyze
            all_files: Set of all files in the project

        Returns:
            Set of file paths that this file depends on
        """
        dependencies, _ = self._get_cached_dependencies(file_path, all_files)
        return dependencies

    def _resolve_import_to_file(self, import_name: str, all_files: Set[Path]) -> Path | None:
        """Resolve an import name to an actual file path."""
        # Handle empty or invalid import names
        if not import_name or not import_name.strip():
            return None

        # Convert module name to potential file paths
        parts = import_name.split(".")

        # Filter out empty parts (e.g., from malformed imports or edge cases)
        # This handles cases like ".", "..", or imports with trailing/leading dots
        parts = [part for part in parts if part]

        # If no valid parts remain after filtering, cannot resolve
        if not parts:
            return None

        # Try different combinations to find the file
        potential_paths = []

        # Try as a direct module file
        try:
            potential_paths.append(Path(*parts).with_suffix(".py"))
        except (ValueError, TypeError):
            # Skip if Path construction fails
            pass

        # Try as a package with __init__.py
        try:
            potential_paths.append(Path(*parts) / "__init__.py")
        except (ValueError, TypeError):
            # Skip if Path construction fails
            pass

        # Try in configured source directories
        for source_dir in self.source_dirs:
            if source_dir == ".":
                # Already handled above for direct paths
                continue
            source_path = Path(source_dir)
            try:
                potential_paths.append(source_path / Path(*parts) / "__init__.py")
            except (ValueError, TypeError):
                pass
            try:
                potential_paths.append((source_path / Path(*parts)).with_suffix(".py"))
            except (ValueError, TypeError):
                pass

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
                # But ensure it's a proper path match, not just a string suffix match
                try:
                    file_relative = file_path.relative_to(self.root_dir)
                    # Check if the relative path matches the potential path exactly
                    # or if it's in a subdirectory structure that matches
                    if str(file_relative) == str(potential_path) or str(file_relative).endswith(
                        "/" + str(potential_path)
                    ):
                        return file_path
                except ValueError:
                    continue

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

        # For relative imports, level indicates how many levels up to go
        # level=1 means current directory, level=2 means parent directory, etc.
        # So we need to go up (level-1) directories from the current directory
        levels_to_go_up = level - 1

        # Check if we can go up that many levels
        if levels_to_go_up > len(current_dir_parts):
            return None

        base_parts = (
            current_dir_parts[:-levels_to_go_up] if levels_to_go_up > 0 else current_dir_parts
        )

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
        reverse_deps: Dict[Path, Set[Path]] = {}

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
        filename = file_path.name

        for pattern in self.ignore_patterns:
            # Use fnmatch for glob-style pattern matching
            if fnmatch.fnmatch(relative_path_str, pattern):
                return True
            if fnmatch.fnmatch(absolute_path_str, pattern):
                return True
            # Also check just the filename (common case for patterns like "test_*")
            if fnmatch.fnmatch(filename, pattern):
                return True
            # Also check if pattern is simply contained in the path
            if pattern in relative_path_str or pattern in absolute_path_str:
                return True

        return False
