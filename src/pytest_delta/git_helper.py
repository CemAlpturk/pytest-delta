"""
Git operations helper using subprocess for better performance.

This module provides Git operations using native git commands via subprocess,
which is significantly faster than gitpython for large repositories.
"""

import subprocess
from pathlib import Path
from typing import Optional, Set


class GitError(Exception):
    """Base exception for Git-related errors."""

    pass


class NotAGitRepositoryError(GitError):
    """Raised when the directory is not a Git repository."""

    pass


class GitCommandError(GitError):
    """Raised when a Git command fails."""

    pass


class GitHelper:
    """Helper class for Git operations using subprocess."""

    def __init__(self, root_dir: Path, search_parent_directories: bool = True):
        """
        Initialize Git helper.

        Args:
            root_dir: Directory to start searching for Git repository
            search_parent_directories: Whether to search parent directories for .git

        Raises:
            NotAGitRepositoryError: If no Git repository is found
        """
        self.root_dir = root_dir.resolve()
        self.git_root = self._find_git_root(search_parent_directories)

    def _find_git_root(self, search_parents: bool) -> Path:
        """
        Find the Git repository root directory.

        Args:
            search_parents: Whether to search parent directories

        Returns:
            Path to Git repository root

        Raises:
            NotAGitRepositoryError: If no Git repository is found
        """
        current = self.root_dir

        while True:
            git_dir = current / ".git"
            if git_dir.exists():
                return current

            if not search_parents or current.parent == current:
                # Reached filesystem root without finding .git
                raise NotAGitRepositoryError(f"Not a Git repository: {self.root_dir}")

            current = current.parent

    def _run_git_command(
        self, args: list[str], check: bool = True, cwd: Optional[Path] = None
    ) -> subprocess.CompletedProcess[str]:
        """
        Run a git command using subprocess.

        Args:
            args: Git command arguments (without 'git' prefix)
            check: Whether to raise exception on non-zero exit code
            cwd: Working directory for the command (defaults to git_root)

        Returns:
            CompletedProcess instance

        Raises:
            GitCommandError: If command fails and check=True
        """
        work_dir = cwd or self.git_root
        cmd = ["git"] + args

        try:
            result = subprocess.run(
                cmd,
                cwd=work_dir,
                capture_output=True,
                text=True,
                check=check,
            )
            return result
        except subprocess.CalledProcessError as e:
            raise GitCommandError(
                f"Git command failed: {' '.join(cmd)}\nExit code: {e.returncode}\nError: {e.stderr}"
            ) from e
        except FileNotFoundError as e:
            raise GitCommandError("Git executable not found") from e

    def get_current_commit(self) -> str:
        """
        Get the current HEAD commit hash.

        Returns:
            Current commit SHA hash

        Raises:
            GitCommandError: If unable to get commit hash
        """
        result = self._run_git_command(["rev-parse", "HEAD"])
        return result.stdout.strip()

    def get_changed_files(self, from_commit: str, to_commit: str = "HEAD") -> Set[Path]:
        """
        Get files changed between two commits.

        Uses git diff-tree for fast file listing.

        Args:
            from_commit: Starting commit hash
            to_commit: Ending commit hash (defaults to HEAD)

        Returns:
            Set of Path objects for changed files

        Raises:
            GitCommandError: If unable to get changed files
        """
        changed_files = set()

        try:
            # Get committed changes using diff-tree (faster than gitpython)
            result = self._run_git_command(
                [
                    "diff-tree",
                    "--no-commit-id",
                    "--name-only",
                    "-r",
                    from_commit,
                    to_commit,
                ],
                check=False,  # Don't fail if commit doesn't exist
            )

            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if line.strip():
                        file_path = self.git_root / line.strip()
                        if file_path.suffix == ".py" and file_path.exists():
                            changed_files.add(file_path)

        except GitCommandError:
            # Commit might not exist, continue to get uncommitted changes
            pass

        return changed_files

    def get_staged_changes(self) -> Set[Path]:
        """
        Get staged (index) changes.

        Returns:
            Set of Path objects for staged files

        Raises:
            GitCommandError: If unable to get staged changes
        """
        changed_files = set()

        try:
            # Get staged changes
            result = self._run_git_command(["diff", "--cached", "--name-only", "HEAD"], check=False)

            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if line.strip():
                        file_path = self.git_root / line.strip()
                        if file_path.suffix == ".py" and file_path.exists():
                            changed_files.add(file_path)

        except GitCommandError:
            pass

        return changed_files

    def get_unstaged_changes(self) -> Set[Path]:
        """
        Get unstaged (working tree) changes.

        Returns:
            Set of Path objects for unstaged files

        Raises:
            GitCommandError: If unable to get unstaged changes
        """
        changed_files = set()

        try:
            # Get unstaged changes
            result = self._run_git_command(["diff", "--name-only"], check=False)

            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if line.strip():
                        file_path = self.git_root / line.strip()
                        if file_path.suffix == ".py" and file_path.exists():
                            changed_files.add(file_path)

        except GitCommandError:
            pass

        return changed_files

    def get_all_changes(self, from_commit: Optional[str] = None) -> Set[Path]:
        """
        Get all changed files including committed, staged, and unstaged changes.

        Args:
            from_commit: Optional starting commit to compare against

        Returns:
            Set of all changed Python files

        Raises:
            GitCommandError: If unable to get changes
        """
        all_changes = set()

        # Get committed changes if from_commit is provided
        if from_commit:
            all_changes.update(self.get_changed_files(from_commit))

        # Get staged changes
        all_changes.update(self.get_staged_changes())

        # Get unstaged changes
        all_changes.update(self.get_unstaged_changes())

        return all_changes

    @property
    def working_dir(self) -> Path:
        """Get the Git working directory (repository root)."""
        return self.git_root
