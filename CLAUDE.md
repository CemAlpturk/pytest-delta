# pytest-delta Memory Bank

## Project Overview

pytest-delta is a pytest plugin that optimizes test execution by only running tests affected by code changes. It uses content hashing and AST-based dependency analysis to determine which tests need to run.

- **Author**: Cem Alpturk
- **License**: MIT
- **Python**: >=3.12
- **Dependencies**: pytest >=9.0.2, msgpack >=1.0.0
- **Entry point**: `pytest_delta.plugin` (registered via `[tool.poetry.plugins."pytest11"]`)
- **Branch**: developing on `develop`, previous implementation on `main` (deleted from develop)

## Architecture

```
pytest_delta/
  __init__.py    - version string
  config.py      - DeltaConfig dataclass, CLI option parsing
  delta.py       - Delta file I/O (msgpack serialization)
  graph.py       - AST import analysis, forward/reverse dependency graphs, transitive closure
  plugin.py      - 4 pytest hooks wiring everything together
```

## Design Decisions

1. **Content hashing** for change detection — no git dependency at runtime. Store `{file_path: sha256_hash}` in delta file.
2. **Conservative conftest.py** — if conftest.py changes, re-run ALL tests in its directory tree.
3. **msgpack** binary format — doesn't show line changes in git diffs.
4. **Run all tests** on first run (no delta file exists).
5. **Always exit 0** when no tests are affected by changes.
6. **Only track .py files** — ignore non-Python files.
7. **New test files always run** — any test file not in previous delta is treated as changed.
8. **No xdist** support initially — add later.
9. **`@pytest.mark.delta_always`** marker — tests that always run regardless of changes.
10. **Graph always fully rebuilt** — AST parsing is fast, no incremental complexity.
11. **Plugin never crashes pytest** — all hooks wrapped in try/except.

## CLI Options

- `--delta` — enable the plugin
- `--delta-file PATH` — custom delta file path (default: `.delta.msgpack`)
- `--delta-rebuild` — force rebuild graph from scratch
- `--delta-no-save` — don't save delta file after run
- `--delta-debug` — print debug information

## Plugin Flow

**First run**: Run all tests → save delta (hashes + graph) on success.

**Subsequent runs**: Load delta → hash current files → compare → find changed/new/deleted → reverse graph to get affected files → conftest rule → filter tests → run only affected → save on success.

**No changes detected**: Deselect all tests → exit 0.

## Key Implementation Details

- `__init__.py` files are implicit dependencies of their package's modules
- Relative imports resolved using file's package position
- Exit code 5 (no tests collected) overridden to 0 only when delta filtering determined zero tests needed
- Delta not saved when tests fail (ensures failing tests re-run next time)
- Delta file schema version 1 for forward compatibility

## Verification Commands

```bash
poetry install
pytest tests/unit/ -v
pytest tests/integration/ -v
pytest --delta --delta-debug  # manual test
```

## Current Implementation Status

- [x] CLAUDE.md memory bank
- [x] pytest_delta/__init__.py (v2.0.0)
- [x] pytest_delta/config.py
- [x] pytest_delta/delta.py
- [x] pytest_delta/graph.py
- [x] pytest_delta/plugin.py
- [x] .gitignore update
- [x] Unit tests — 59 tests (config: 9, delta: 9, graph: 41)
- [x] Integration tests — 17 tests (pytester-based)
- [x] All 76 tests passing

## Future Work

- xdist compatibility
- Non-Python file tracking (configurable patterns)
- README.md documentation
