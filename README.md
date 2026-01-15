# pytest-delta

A pytest plugin that filters tests to only those affected by changes since the last successful run.

## Installation

```bash
pip install pytest-delta
```

## Usage

```bash
# Enable delta filtering
pytest --delta

# With debug output
pytest --delta --delta-debug

# With pytest-xdist for parallel execution
pytest --delta -n auto
```

## CLI Options

| Flag | Description |
|------|-------------|
| `--delta` | Enable delta filtering |
| `--delta-file PATH` | Custom delta file path (default: `.delta.msgpack` in project root) |
| `--delta-debug` | Show debug info: changed files, affected files, graph stats |
| `--delta-pass-if-no-tests` | Exit 0 when no tests need to run |
| `--delta-no-save` | Don't update delta file after run (read-only mode for CI/CD) |
| `--delta-ignore PATTERN` | Ignore file pattern (repeatable) |
| `--delta-rebuild` | Force rebuild dependency graph |

## Markers

```python
import pytest

@pytest.mark.delta_always
def test_critical():
    """This test runs on every invocation regardless of changes."""
    ...
```

## How It Works

1. On first run, builds a dependency graph by analyzing Python imports
2. Saves a `.delta.msgpack` file with the current commit SHA and graph
3. On subsequent runs, compares current state to last successful run
4. Only runs tests that depend on changed files (transitively)

## CI Integration

```yaml
# .github/workflows/test.yml
jobs:
  test:
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # Need full history for git diff

      - name: Run affected tests
        run: pytest --delta --delta-pass-if-no-tests -n auto
```

## License

MIT
