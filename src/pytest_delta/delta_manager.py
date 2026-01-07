"""
Delta metadata manager for pytest-delta plugin.

Handles saving and loading metadata about the last test run,
including the git commit hash and other relevant information.
"""

import ast
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from .git_helper import GitHelper, NotAGitRepositoryError


class DeltaManager:
    """Manages delta metadata file operations."""

    def __init__(self, delta_file: Path):
        self.delta_file = delta_file

    def _detect_project_version(self, root_dir: Path) -> Optional[str]:
        """
        Detect the project version from various sources.

        Tries to find version in:
        1. pyproject.toml ([tool.poetry.version] or [project.version])
        2. Main package __init__.py (__version__ attribute)

        Args:
            root_dir: Root directory of the project

        Returns:
            Version string if found, None otherwise
        """
        # Try pyproject.toml first
        pyproject_path = root_dir / "pyproject.toml"
        if pyproject_path.exists():
            try:
                import tomllib

                with open(pyproject_path, "rb") as f:
                    data = tomllib.load(f)

                # Check for Poetry style [tool.poetry.version]
                if (
                    "tool" in data
                    and "poetry" in data["tool"]
                    and "version" in data["tool"]["poetry"]
                ):
                    version = data["tool"]["poetry"]["version"]
                    return str(version) if version is not None else None

                # Check for PEP 621 style [project.version]
                if "project" in data and "version" in data["project"]:
                    version = data["project"]["version"]
                    return str(version) if version is not None else None

            except Exception:
                # If tomllib import fails or file parsing fails, continue to next method
                pass

        # Try to find version in main package __init__.py
        for candidate_dir in ["src", "."]:
            candidate_path = root_dir / candidate_dir
            if candidate_path.exists() and candidate_path.is_dir():
                # Look for packages (directories with __init__.py)
                for item in candidate_path.iterdir():
                    if item.is_dir() and (item / "__init__.py").exists():
                        init_file = item / "__init__.py"
                        try:
                            with open(init_file, "r", encoding="utf-8") as f:
                                content = f.read()

                            # Parse AST to find __version__
                            tree = ast.parse(content)
                            for node in ast.walk(tree):
                                if isinstance(node, ast.Assign):
                                    for target in node.targets:
                                        if (
                                            isinstance(target, ast.Name)
                                            and target.id == "__version__"
                                        ):
                                            if isinstance(node.value, ast.Constant):
                                                value = node.value.value
                                                return (
                                                    str(value)
                                                    if isinstance(value, str)
                                                    else None
                                                )
                        except Exception:
                            continue

        return None

    def load_metadata(self) -> Optional[Dict[str, Any]]:
        """Load metadata from the delta file."""
        if not self.delta_file.exists():
            return None

        try:
            with open(self.delta_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Ensure we're returning a Dict[str, Any] or None
                return data if isinstance(data, dict) else None
        except (json.JSONDecodeError, OSError) as e:
            raise ValueError(f"Failed to load delta metadata: {e}") from e

    def save_metadata(self, metadata: Dict[str, Any]) -> None:
        """
        Save metadata to the delta file using hybrid JSON format.

        The hybrid format uses:
        - Readable indentation for simple scalar fields
        - Compact single-line format for large dictionaries (dependency_graph, file_hashes)

        This minimizes Git diff impact while maintaining JSON compatibility.

        Uses atomic write (temp file + rename) to prevent corruption from
        concurrent access or interrupted writes (e.g., pytest-xdist).
        """
        try:
            # Ensure parent directory exists
            self.delta_file.parent.mkdir(parents=True, exist_ok=True)

            # Write to a temporary file first, then atomically rename
            # This prevents corruption if the write is interrupted
            fd, tmp_path = tempfile.mkstemp(
                suffix=".tmp",
                prefix=".delta_",
                dir=self.delta_file.parent,
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    # Collect all fields to write in order
                    lines = []

                    # Simple scalar fields - readable format
                    simple_fields = ["last_commit", "last_successful_run", "version"]
                    for field in simple_fields:
                        if field in metadata:
                            value = metadata[field]
                            # Format value appropriately
                            if isinstance(value, str):
                                json_value = json.dumps(value)
                            elif isinstance(value, bool):
                                json_value = "true" if value else "false"
                            else:
                                json_value = json.dumps(value)
                            lines.append(f'  "{field}": {json_value}')

                    # Large dictionary fields - compact single-line format
                    dict_fields = ["dependency_graph", "file_hashes"]
                    for field in dict_fields:
                        if field in metadata:
                            # Compact JSON without spaces
                            json_value = json.dumps(
                                metadata[field], sort_keys=True, separators=(",", ":")
                            )
                            lines.append(f'  "{field}": {json_value}')

                    # Write with proper comma placement
                    f.write("{\n")
                    for i, line in enumerate(lines):
                        # Add comma for all but the last line
                        comma = "," if i < len(lines) - 1 else ""
                        f.write(f"{line}{comma}\n")
                    f.write("}\n")

                # Atomically replace the target file
                os.replace(tmp_path, self.delta_file)
            except BaseException:
                # Clean up temp file on any error
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        except OSError as e:
            raise ValueError(f"Failed to save delta metadata: {e}") from e

    def update_metadata(
        self,
        root_dir: Path,
        dependency_graph: Optional[Dict[Path, set[Path]]] = None,
        file_hashes: Optional[Dict[Path, str]] = None,
    ) -> None:
        """
        Update metadata with current git state and optionally the dependency graph.

        Args:
            root_dir: Root directory of the project
            dependency_graph: Optional dependency graph to store
            file_hashes: Optional file hashes corresponding to the dependency graph
        """
        try:
            git_helper = GitHelper(root_dir, search_parent_directories=True)
        except NotAGitRepositoryError as e:
            raise ValueError("Not a Git repository") from e

        try:
            # Get current commit hash
            current_commit = git_helper.get_current_commit()

            # Detect project version
            project_version = self._detect_project_version(root_dir)

            # Create metadata
            metadata: Dict[str, Any] = {
                "last_commit": current_commit,
                "last_successful_run": True,
                "version": project_version,
            }

            # Add dependency graph if provided
            if dependency_graph is not None and file_hashes is not None:
                # Convert Path objects to strings for JSON serialization
                graph_data = {}
                for file_path, dependencies in dependency_graph.items():
                    # Store relative paths for portability
                    rel_path = str(file_path.relative_to(root_dir))
                    dep_rel_paths = [
                        str(dep.relative_to(root_dir)) for dep in dependencies
                    ]
                    graph_data[rel_path] = dep_rel_paths

                hash_data = {
                    str(file_path.relative_to(root_dir)): file_hash
                    for file_path, file_hash in file_hashes.items()
                }

                metadata["dependency_graph"] = graph_data
                metadata["file_hashes"] = hash_data

            self.save_metadata(metadata)

        except Exception as e:
            raise ValueError(f"Failed to get Git information: {e}") from e

    def load_dependency_graph(
        self, root_dir: Path
    ) -> Optional[tuple[Dict[Path, set[Path]], Dict[Path, str]]]:
        """
        Load the dependency graph from metadata.

        Args:
            root_dir: Root directory of the project

        Returns:
            Tuple of (dependency_graph, file_hashes) if available, None otherwise
        """
        metadata = self.load_metadata()
        if metadata is None:
            return None

        if "dependency_graph" not in metadata or "file_hashes" not in metadata:
            return None

        try:
            # Convert string paths back to Path objects
            graph_data = metadata["dependency_graph"]
            hash_data = metadata["file_hashes"]

            dependency_graph = {}
            for rel_path_str, dep_rel_paths in graph_data.items():
                file_path = root_dir / rel_path_str
                dependencies = {root_dir / dep for dep in dep_rel_paths}
                dependency_graph[file_path] = dependencies

            file_hashes = {
                root_dir / rel_path_str: file_hash
                for rel_path_str, file_hash in hash_data.items()
            }

            return dependency_graph, file_hashes

        except Exception:
            # If there's any error loading the graph, return None
            return None
