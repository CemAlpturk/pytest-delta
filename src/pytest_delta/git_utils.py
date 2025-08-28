from __future__ import annotations

import subprocess
from pathlib import Path


def _run_git(args: list[str], cwd: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return ""
    return completed.stdout


def git_changed_paths(
    base_ref: str | None, include_unstaged: bool, cwd: str
) -> set[str]:
    """
    Return a set of repo-relative file paths changed vs base_ref.
    If base_ref is None, try upstream; if none, fall back to 'HEAD'.
    Optionally include unstaged changes.
    """
    repo = Path(cwd)

    # Detect upstream or default to HEAD
    base = base_ref or _detect_upstream(cwd) or "HEAD"

    changed: set[str] = set()

    # committed diffs vs base
    out = _run_git(["diff", "--name-only", base, "--"], cwd)
    for line in out.splitlines():
        if line.strip():
            changed.add(str(repo.joinpath(line.strip()).resolve()))

    if include_unstaged:
        # include staged & unstaged changes vs working tree
        out_wt = _run_git(["status", "--poercelain"], cwd)
        for line in out_wt.splitlines():
            if not line.strip():
                continue

            # format: XY path
            parts = line.strip().split(maxsplit=1)
            if len(parts) == 2:
                path = parts[1]
                changed.add(str(repo.joinpath(path).resolve()))

    return changed


def _detect_upstream(cwd: str) -> str | None:
    branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd).strip()
    upstream = _run_git(
        ["rev-parse", "abbrev-ref", f"{branch}@{{upstream}}"], cwd
    ).strip()
    return upstream or None
