# pytest-delta

A pytest plugin that runs only the tests affected by your code changes. Instead of running your entire test suite every time, pytest-delta uses content hashing and AST-based dependency analysis to figure out which tests actually need to run.

## How It Works

1. On the **first run**, all tests execute normally. pytest-delta builds a dependency graph by parsing imports across your Python files and saves a snapshot (file hashes + graph) to a `.delta.msgpack` file.

2. On **subsequent runs**, it compares current file hashes against the snapshot to detect changes. Using the reverse dependency graph, it identifies all files transitively affected by those changes and runs only the corresponding tests.

3. If a `conftest.py` changes, all tests in its directory and subdirectories are re-run (conservative approach).

4. The delta file is only updated when all tests pass. If tests fail, the previous snapshot is preserved so those tests run again next time.

## Installation

```bash
pip install pytest-delta
```

Or with Poetry:

```bash
poetry add pytest-delta
```

## Usage

Enable the plugin with the `--delta` flag:

```bash
# First run: executes all tests, creates .delta.msgpack
pytest --delta

# Second run: no changes detected, exits 0 immediately
pytest --delta

# After modifying src/utils.py: only affected tests run
pytest --delta
```

Use `--delta-debug` to see what the plugin is doing:

```bash
pytest --delta --delta-debug
```

```
[pytest-delta] Plugin enabled
[pytest-delta] Loaded delta: 42 files tracked
[pytest-delta] Changed: 1, New: 0, Deleted: 0
[pytest-delta] Affected test files: 3
[pytest-delta]   tests/test_api.py
[pytest-delta]   tests/test_models.py
[pytest-delta]   tests/test_utils.py
[pytest-delta] Selected: 12, Deselected: 85
```

## CLI Options

| Option | Description |
|--------|-------------|
| `--delta` | Enable delta-based test filtering |
| `--delta-file PATH` | Custom delta file path (default: `.delta.msgpack`) |
| `--delta-rebuild` | Force rebuild the dependency graph from scratch |
| `--delta-no-save` | Don't save the delta file after the run (read-only mode) |
| `--delta-debug` | Print debug information about filtering decisions |

## Markers

Force specific tests to always run regardless of changes:

```python
import pytest

@pytest.mark.delta_always
def test_smoke():
    """This test runs every time, even if nothing changed."""
    assert app.health_check() == "ok"
```

## CI Workflow

A typical workflow:

1. Developer runs `pytest --delta` locally. Tests pass, `.delta.msgpack` is updated.
2. Developer commits the delta file along with their changes.
3. CI runs `pytest --delta`. Since the delta file reflects the already-validated state, no tests need to run and CI exits 0 immediately.

For CI pipelines where you want to prevent accidental delta file updates:

```bash
pytest --delta --delta-no-save
```

## Change Detection

pytest-delta uses **content hashing** (SHA-256) to detect changes. This means:

- No dependency on git history or commit hashes
- Works with uncommitted and staged changes
- No issues with rebasing or squash merges
- Detects changes regardless of how they were made

## Dependency Analysis

The plugin builds a dependency graph by parsing Python AST import statements:

- Handles absolute imports (`import pkg.mod`, `from pkg.mod import func`)
- Handles relative imports (`from .utils import helper`, `from ..core import Base`)
- Tracks `__init__.py` as implicit dependencies of package modules
- Computes transitive closure: if A imports B and B imports C, changing C re-runs tests for both A and B

Limitations:
- Only tracks `.py` files (non-Python config/data files are ignored)
- Dynamic imports (`importlib.import_module()`) are not detected
- Only project-local imports are tracked (third-party packages are ignored)

## Configuration

Add `.delta.msgpack` to your `.gitignore` if you don't want to share the delta file across developers, or commit it if you want the CI optimization described above.

```gitignore
# Uncomment to exclude from version control
# .delta.msgpack
```

## License

MIT
