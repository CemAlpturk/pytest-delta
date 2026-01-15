"""Git operations for pytest-delta."""

from __future__ import annotations

import subprocess
from pathlib import Path


class GitError(Exception):
    """Raised when a git operation fails."""

    pass


def run_git_command(
    *args: str,
    cwd: Path | None = None,
    check: bool = True,
) -> str:
    """Run a git command and return its stdout.

    Args:
        *args: Git command arguments (without 'git' prefix).
        cwd: Working directory for the command.
        check: Whether to raise an exception on non-zero exit code.

    Returns:
        The stdout of the command, stripped of trailing whitespace.

    Raises:
        GitError: If the command fails and check is True.
    """
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=check,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        raise GitError(f"Git command failed: git {' '.join(args)}\n{e.stderr}") from e
    except FileNotFoundError as e:
        raise GitError("Git is not installed or not in PATH") from e


def get_current_commit(cwd: Path | None = None) -> str:
    """Get the current commit SHA.

    Args:
        cwd: Working directory (should be inside a git repository).

    Returns:
        The full 40-character commit SHA.
    """
    return run_git_command("rev-parse", "HEAD", cwd=cwd)


def get_changed_files(
    base_commit: str,
    cwd: Path | None = None,
) -> set[str]:
    """Get the set of files changed between base_commit and HEAD.

    Args:
        base_commit: The commit SHA to compare against.
        cwd: Working directory (should be inside a git repository).

    Returns:
        A set of file paths (relative to repo root) that have changed.
        Includes added, modified, and deleted files.
    """
    # Check if base_commit exists in history
    try:
        run_git_command("cat-file", "-e", base_commit, cwd=cwd)
    except GitError as e:
        raise GitError(
            f"Base commit {base_commit[:12]} not found in git history. "
            "This may happen if history was rewritten or shallow cloned. "
            "Consider using --delta-rebuild to reset."
        ) from e

    # Get diff between base_commit and HEAD
    output = run_git_command(
        "diff",
        "--name-only",
        f"{base_commit}..HEAD",
        cwd=cwd,
    )

    if not output:
        return set()

    return set(output.splitlines())


def get_all_tracked_files(cwd: Path | None = None) -> set[str]:
    """Get all files tracked by git.

    Args:
        cwd: Working directory (should be inside a git repository).

    Returns:
        A set of all tracked file paths (relative to repo root).
    """
    output = run_git_command("ls-files", cwd=cwd)

    if not output:
        return set()

    return set(output.splitlines())


def is_git_repository(path: Path) -> bool:
    """Check if a path is inside a git repository.

    Args:
        path: The path to check.

    Returns:
        True if the path is inside a git repository, False otherwise.
    """
    try:
        run_git_command("rev-parse", "--git-dir", cwd=path)
        return True
    except GitError:
        return False


def get_repo_root(cwd: Path | None = None) -> Path:
    """Get the root directory of the git repository.

    Args:
        cwd: Working directory (should be inside a git repository).

    Returns:
        The absolute path to the repository root.
    """
    root = run_git_command("rev-parse", "--show-toplevel", cwd=cwd)
    return Path(root)
