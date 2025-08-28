from __future__ import annotations

from dataclasses import dataclass

import pytest
from _pytest.config import Config
from _pytest.nodes import Item

from .git_utils import git_changed_paths
from .graph import build_dependency_graph, DependencyGraph
from .selection import impacted_tests


@dataclass(frozen=True)
class DeltaConfig:
    enabled: bool
    base_ref: str | None  # e.g., "origin/main" or commit sha
    include_unstaged: bool


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("depta", "run only tests impacted by code changes")
    group.addoption(
        "--delta",
        action="store_true",
        default=False,
        help="Enable delta-based test selection (run only impacted tests).",
    )
    group.addoption(
        "--delta-base",
        action="store",
        default=None,
        help="Base git reference to diff against (e.g., origin/main, HEAD~1). "
        "If omitted, plugin tries to infer from the current branch's upstream.",
    )
    group.addoption(
        "--delta-include-unstaged",
        action="store_true",
        default=False,
        help="Include unstaged/uncommitted changes in selection.",
    )


def _load_config(config: Config) -> DeltaConfig:
    return DeltaConfig(
        enabled=bool(config.getoption("--delta")),
        base_ref=config.getoption("--delta-base"),
        include_unstaged=bool(config.getoption("--delta-include-unstaged")),
    )


def pytest_collection_modifyitems(config: Config, items: list[Item]) -> None:
    cfg = _load_config(config)
    if not cfg.enabled:
        return

    # 1) Determine changed paths via git
    changed: set[str] = git_changed_paths(
        base_ref=cfg.base_ref,
        include_unstaged=cfg.include_unstaged,
        cwd=str(config.rootpath),
    )

    if not changed:
        config.warn(
            code="delta0",
            message="[pytest-delta] No changes detected; running all tests.",
        )
        return  # nothing changed, run all tests

    # 2) Build a (very) rough dependency graph if your project to trace impact
    graph: DependencyGraph = build_dependency_graph(root=str(config.rootpath))

    # 3) Determine impacted test nodeids given collected items + changed files
    selected: set[str] = impacted_tests(items=items, changed_paths=changed, graph=graph)

    if not selected:
        config.warn(
            code="delta1",
            message="[pytest-delta] No impacted tests found; skipping all.",
        )
        # empty selection: leave items but mark them deselected
        deselected = list(items)
        items.clear()
        config.hook.pytest_deselected(items=deselected)
        return

    # 4) Filter items in-place to only selected ones
    new_items: list[Item] = [it for it in items if it.nodeid in selected]
    deselected = [it for it in items if it.nodeid not in selected]
    items[:] = new_items

    if deselected:
        config.hook.pytest_deselected(items=deselected)

    config.warn(
        code="delta2",
        message=f"[pytest-delta] Selected {len(items)} impacted test(s) "
        f"out of {len(items) + len(deselected)} total.",
    )
