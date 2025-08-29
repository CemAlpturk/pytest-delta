"""
Delta metadata manager for pytest-delta plugin.

Handles saving and loading metadata about the last test run,
including the git commit hash and other relevant information.
"""

import ast
import json
from pathlib import Path
from typing import Any, Dict, Optional

from git import Repo
from git.exc import GitCommandError, InvalidGitRepositoryError


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
                    return data["tool"]["poetry"]["version"]

                # Check for PEP 621 style [project.version]
                if "project" in data and "version" in data["project"]:
                    return data["project"]["version"]

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
                                                return node.value.value
                        except Exception:
                            continue

        return None

    def load_metadata(self) -> Optional[Dict[str, Any]]:
        """Load metadata from the delta file."""
        if not self.delta_file.exists():
            return None

        try:
            with open(self.delta_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            raise ValueError(f"Failed to load delta metadata: {e}") from e

    def save_metadata(self, metadata: Dict[str, Any]) -> None:
        """Save metadata to the delta file."""
        try:
            # Ensure parent directory exists
            self.delta_file.parent.mkdir(parents=True, exist_ok=True)

            with open(self.delta_file, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2, sort_keys=True)
        except OSError as e:
            raise ValueError(f"Failed to save delta metadata: {e}") from e

    def update_metadata(self, root_dir: Path) -> None:
        """Update metadata with current git state."""
        try:
            repo = Repo(root_dir, search_parent_directories=True)
        except InvalidGitRepositoryError as e:
            raise ValueError("Not a Git repository") from e

        try:
            # Get current commit hash
            current_commit = repo.head.commit.hexsha

            # Detect project version
            project_version = self._detect_project_version(root_dir)

            # Create metadata
            metadata = {
                "last_commit": current_commit,
                "last_successful_run": True,
                "version": project_version,
            }

            self.save_metadata(metadata)

        except GitCommandError as e:
            raise ValueError(f"Failed to get Git information: {e}") from e
