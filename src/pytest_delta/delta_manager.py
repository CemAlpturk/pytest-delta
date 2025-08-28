"""
Delta metadata manager for pytest-delta plugin.

Handles saving and loading metadata about the last test run,
including the git commit hash and other relevant information.
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional

from git import Repo
from git.exc import GitCommandError, InvalidGitRepositoryError


class DeltaManager:
    """Manages delta metadata file operations."""

    def __init__(self, delta_file: Path):
        self.delta_file = delta_file

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
            repo = Repo(root_dir)
        except InvalidGitRepositoryError as e:
            raise ValueError("Not a Git repository") from e

        try:
            # Get current commit hash
            current_commit = repo.head.commit.hexsha

            # Create metadata
            metadata = {
                "last_commit": current_commit,
                "last_successful_run": True,
                "version": "0.1.0",
            }

            self.save_metadata(metadata)

        except GitCommandError as e:
            raise ValueError(f"Failed to get Git information: {e}") from e
