"""Tests for the git module."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pytest_delta.git import (
    GitError,
    get_changed_files,
    get_current_commit,
    get_repo_root,
    is_git_repository,
    run_git_command,
)


class TestRunGitCommand:
    """Tests for run_git_command."""

    def test_successful_command(self, tmp_path: Path) -> None:
        """Test running a successful git command."""
        # Initialize a git repo
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)

        result = run_git_command("status", cwd=tmp_path)
        assert "No commits yet" in result or "nothing to commit" in result

    def test_failed_command_raises_git_error(self, tmp_path: Path) -> None:
        """Test that a failed command raises GitError."""
        with pytest.raises(GitError, match="Git command failed"):
            run_git_command("log", cwd=tmp_path)  # No git repo here

    def test_git_not_found_raises_git_error(self) -> None:
        """Test that missing git binary raises GitError."""
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            with pytest.raises(GitError, match="not installed"):
                run_git_command("status")


class TestGetCurrentCommit:
    """Tests for get_current_commit."""

    def test_returns_commit_sha(self, tmp_path: Path) -> None:
        """Test getting the current commit SHA."""
        # Initialize repo and create a commit
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )

        # Create a file and commit
        (tmp_path / "test.txt").write_text("hello")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )

        commit = get_current_commit(tmp_path)
        assert len(commit) == 40
        assert all(c in "0123456789abcdef" for c in commit)


class TestGetChangedFiles:
    """Tests for get_changed_files."""

    def test_returns_changed_files(self, tmp_path: Path) -> None:
        """Test getting changed files between commits."""
        # Initialize repo
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )

        # First commit
        (tmp_path / "file1.py").write_text("# file 1")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "first"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        first_commit = get_current_commit(tmp_path)

        # Second commit with new file
        (tmp_path / "file2.py").write_text("# file 2")
        (tmp_path / "file1.py").write_text("# file 1 modified")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "second"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )

        changed = get_changed_files(first_commit, tmp_path)
        assert changed == {"file1.py", "file2.py"}

    def test_no_changes_returns_empty_set(self, tmp_path: Path) -> None:
        """Test that no changes returns empty set."""
        # Initialize repo
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )

        (tmp_path / "file.py").write_text("# file")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "commit"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        commit = get_current_commit(tmp_path)

        changed = get_changed_files(commit, tmp_path)
        assert changed == set()

    def test_invalid_commit_raises_error(self, tmp_path: Path) -> None:
        """Test that invalid commit SHA raises GitError."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )

        (tmp_path / "file.py").write_text("# file")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "commit"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )

        with pytest.raises(GitError, match="not found in git history"):
            get_changed_files("invalidcommitsha123456789012345678901234", tmp_path)


class TestIsGitRepository:
    """Tests for is_git_repository."""

    def test_returns_true_for_git_repo(self, tmp_path: Path) -> None:
        """Test that git repos are detected."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
        assert is_git_repository(tmp_path) is True

    def test_returns_false_for_non_git_dir(self, tmp_path: Path) -> None:
        """Test that non-git dirs are detected."""
        assert is_git_repository(tmp_path) is False


class TestGetRepoRoot:
    """Tests for get_repo_root."""

    def test_returns_repo_root(self, tmp_path: Path) -> None:
        """Test getting the repository root."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)

        subdir = tmp_path / "src" / "subdir"
        subdir.mkdir(parents=True)

        root = get_repo_root(subdir)
        assert root == tmp_path
