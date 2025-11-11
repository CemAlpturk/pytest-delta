# pytest-delta

Run only tests impacted by your code changes (delta-based selection) for pytest.

## Overview

pytest-delta is a pytest plugin that reduces test execution time by running only the tests that are potentially affected by your code changes. It creates a directional dependency graph based on Python imports and selects tests intelligently based on what files have changed since the last successful test run.

## Features

- **Smart Test Selection**: Only runs tests affected by changed files
- **High Performance**: Up to 47x faster with intelligent caching and incremental updates
- **Dependency Tracking**: Creates a dependency graph based on Python imports
- **Dependency Visualization**: Generate visual representations of project structure
- **Git Integration**: Compares against the last successful test run commit
- **Uncommitted Changes Support**: Includes both staged and unstaged changes
- **Force Regeneration**: Option to force running all tests and regenerate metadata
- **File-based Mapping**: Assumes test files follow standard naming conventions

## Installation

```bash
pip install pytest-delta
```

Or for development:

```bash
git clone https://github.com/CemAlpturk/pytest-delta
cd pytest-delta
pip install -e .
```

## Usage

### Basic Usage

Run tests with delta selection:

```bash
pytest --delta
```

On first run, it will execute all tests and create a `.delta.json` file with metadata.

### Command Line Options

- `--delta`: Enable delta-based test selection
- `--delta-filename NAME`: Specify filename for delta metadata file (default: `.delta`)
- `--delta-dir PATH`: Specify directory for delta metadata file (default: current directory)
- `--delta-force`: Force regeneration of delta file and run all tests
- `--delta-ignore PATTERN`: Ignore file patterns during dependency analysis (can be used multiple times)
- `--delta-vis`: Generate a visual representation of the project's dependency graph
- `--delta-source-dirs PATH`: Source directories to search for Python files (default: `.` and `src/`)
- `--delta-test-dirs PATH`: Test directories to search for test files (default: `tests/`)
- `--delta-debug`: Display detailed debug information including incremental update statistics
- `--delta-pass-if-no-tests`: Exit with code 0 when no tests need to be run due to no changes
- `--delta-no-save`: Skip updating the delta file after tests (read-only mode for CI/CD)

### Examples

```bash
# Run only affected tests
pytest --delta

# Generate dependency visualization
pytest --delta-vis

# Combine visualization with delta testing
pytest --delta --delta-vis

# Force run all tests and regenerate metadata
pytest --delta --delta-force

# Use custom delta filename (will become custom-delta.json)
pytest --delta --delta-filename custom-delta

# Use custom directory for delta file
pytest --delta --delta-dir .metadata

# Combine custom filename and directory
pytest --delta --delta-filename my-tests --delta-dir /tmp/deltas

# Combine with other pytest options
pytest --delta -v --tb=short

# Ignore generated files during analysis
pytest --delta --delta-ignore "*generated*"

# Ignore multiple patterns
pytest --delta --delta-ignore "*generated*" --delta-ignore "vendor/*"

# Ignore test files from dependency analysis (useful for complex test hierarchies)
pytest --delta --delta-ignore "tests/integration/*"

# Use custom source directories (for non-standard project layouts)
pytest --delta --delta-source-dirs lib --delta-source-dirs modules

# Use custom test directories
pytest --delta --delta-test-dirs unit_tests --delta-test-dirs integration_tests

# Combine custom directories
pytest --delta --delta-source-dirs src --delta-source-dirs lib --delta-test-dirs tests --delta-test-dirs e2e

# Enable debug output to see detailed information
pytest --delta --delta-debug

# Debug with custom directories
pytest --delta --delta-debug --delta-source-dirs custom_src --delta-test-dirs custom_tests

# Read-only mode for CI/CD (use existing delta file but don't update it)
pytest --delta --delta-no-save
```

## Dependency Visualization

The `--delta-vis` option generates visual representations of your project's dependency graph, which is useful for:

- **Understanding code relationships**: See which files depend on each other
- **Debugging the plugin**: Visualize how pytest-delta determines affected tests
- **Code review**: Get insights into project structure and coupling
- **Documentation**: Generate dependency diagrams for your project

### Visualization Output

When you run `pytest --delta-vis`, the plugin generates:

1. **Console output**: Immediate feedback showing file counts and top dependencies
2. **DOT file** (`dependency_graph.dot`): GraphViz format for rendering images
3. **Text summary** (`dependency_summary.txt`): Detailed human-readable analysis

### Example Console Output

```
📊 Dependency Graph Visualization
==================================================
Files: 7 | Dependencies: 5 | Max per file: 5

🔗 Files with most dependencies:
   5 deps: tests/test_plugin.py
   0 deps: src/myproject/utils.py
   0 deps: src/myproject/models.py
```

### Rendering Graphical Output

If you have Graphviz installed, you can render the DOT file as an image:

```bash
# Generate visualization
pytest --delta-vis

# Render as PNG image (requires graphviz)
dot -Tpng dependency_graph.dot -o dependency_graph.png

# Render as SVG (scalable)
dot -Tsvg dependency_graph.dot -o dependency_graph.svg

# Render as PDF
dot -Tpdf dependency_graph.dot -o dependency_graph.pdf
```

### Installation of Optional Dependencies

For rendering graphical outputs, you can install Graphviz:

```bash
# On Ubuntu/Debian
sudo apt-get install graphviz

# On macOS
brew install graphviz

# On Windows (using chocolatey)
choco install graphviz
```

### Migration from Previous Versions

If you were using the old `--delta-file` option, you can migrate as follows:

```bash
# Old way (no longer supported):
# pytest --delta --delta-file /path/to/custom.json

# New way:
pytest --delta --delta-filename custom --delta-dir /path/to
# This creates: /path/to/custom.json
```

## How It Works

1. **First Run**: On the first run (or when the delta file doesn't exist), all tests are executed and a delta metadata file is created containing the current Git commit hash.

2. **Change Detection**: On subsequent runs, the plugin:
   - Compares current Git state with the last successful run
   - Identifies changed Python files (both committed and uncommitted)
   - Builds a dependency graph based on Python imports
   - Finds all files transitively affected by the changes

3. **Test Selection**: The plugin selects tests based on:
   - Direct test files that were modified
   - Test files that test the modified source files
   - Test files that test files affected by the changes (transitive dependencies)

4. **File Mapping**: Test files are mapped to source files using naming conventions:
   - `tests/test_module.py` ↔ `src/module.py`
   - `tests/subdir/test_module.py` ↔ `src/subdir/module.py`

## Project Structure Assumptions

The plugin works best with projects that follow these conventions:

```
project/
├── src/                    # Source code
│   ├── module1.py
│   └── package/
│       └── module2.py
├── tests/                  # Test files
│   ├── test_module1.py
│   └── package/
│       └── test_module2.py
└── .delta.json            # Delta metadata (auto-generated, default location)
```

## Delta File Format

The delta metadata file (`.delta.json` by default) stores information about the last successful test run. The file uses a **hybrid JSON format** optimized for minimal Git diffs:

```json
{
  "last_commit": "abc123def456...",
  "last_successful_run": true,
  "version": "1.0.0",
  "dependency_graph": {"src/a.py":["src/b.py"],"src/b.py":[]},
  "file_hashes": {"src/a.py":"hash1","src/b.py":"hash2"}
}
```

### Format Features

- **Minimal Git Diffs**: Simple fields (commit, version) are readable; large dictionaries (dependency graph, file hashes) are compact one-liners
- **82% Fewer Changed Lines**: When adding a single file, only 3 lines change instead of 17+ in the old format
- **Backward Compatible**: Standard JSON format that works with existing tooling
- **Human Readable**: Simple fields remain easy to read and understand

### Benefits for Version Control

When tracked in Git, this format provides:
- Smaller, cleaner diffs
- Easier code reviews
- Fewer merge conflicts
- Better Git history tracking
- Only changed sections appear in diffs

The format automatically handles dependency graphs with hundreds of files while keeping Git diffs minimal.

## Configuration

### Configurable Directories

By default, pytest-delta searches for source files in the project root (`.`) and `src/` directories, and test files in the `tests/` directory. You can customize these locations:

```bash
# Use custom source directories
pytest --delta --delta-source-dirs lib --delta-source-dirs modules

# Use custom test directories
pytest --delta --delta-test-dirs unit_tests --delta-test-dirs integration_tests

# Combine both for complex project layouts
pytest --delta --delta-source-dirs src --delta-source-dirs lib --delta-test-dirs tests --delta-test-dirs e2e
```

This is useful for projects with non-standard layouts or when you want to exclude certain directories from analysis.

### Debug Information

Use `--delta-debug` to get detailed information about the plugin's behavior:

```bash
pytest --delta --delta-debug
```

This will show you:
- Which directories are being searched
- What files were found and analyzed
- Which files changed since the last run
- How the dependency graph was built
- Which tests were selected and why

### Ignoring Files

The `--delta-ignore` option allows you to exclude certain files from dependency analysis. This is useful for:

- **Generated files**: Auto-generated code that shouldn't trigger test runs
- **Vendor/third-party code**: External dependencies that don't need analysis
- **Temporary files**: Files that are frequently modified but don't affect tests
- **Documentation**: Markdown, text files that might be mixed with Python code

The ignore patterns support:
- **Glob patterns**: `*generated*`, `*.tmp`, `vendor/*`
- **Path matching**: Both relative and absolute paths are checked
- **Multiple patterns**: Use the option multiple times for different patterns

Examples:
```bash
# Ignore all generated files
pytest --delta --delta-ignore "*generated*"

# Ignore vendor directory and any temp files
pytest --delta --delta-ignore "vendor/*" --delta-ignore "*.tmp"

# Ignore specific test subdirectories from analysis
pytest --delta --delta-ignore "tests/integration/*" --delta-ignore "tests/e2e/*"
```

### Default Configuration

The plugin requires no configuration for basic usage. It automatically:

- Finds Python files in the current directory (`.`) and `src/` directories by default
- Searches for test files in the `tests/` directory by default
- Excludes virtual environments, `__pycache__`, and other irrelevant directories
- Creates dependency graphs based on import statements
- Maps test files to source files using naming conventions

You can override the default directories using `--delta-source-dirs` and `--delta-test-dirs` options to customize the search paths for your specific project layout.

## Error Handling

The plugin includes robust error handling:

- **No Git Repository**: Falls back to running all tests
- **Invalid Delta File**: Regenerates metadata and runs all tests
- **Git Errors**: Falls back to running all tests with warnings
- **Import Analysis Errors**: Continues with partial dependency graph

## Example Output

```bash
$ pytest --delta -v
================ test session starts ================
plugins: delta-0.1.0
[pytest-delta] Selected 3/10 tests based on code changes
[pytest-delta] Affected files: src/calculator.py, tests/test_calculator.py

tests/test_calculator.py::test_add PASSED
tests/test_calculator.py::test_multiply PASSED
tests/test_math_utils.py::test_area PASSED

[pytest-delta] Delta metadata updated successfully
================ 3 passed in 0.02s ================
```

## Development

To set up for development:

```bash
git clone https://github.com/CemAlpturk/pytest-delta
cd pytest-delta
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e .
pip install pytest gitpython

# Run tests
pytest tests/

# Test the plugin
pytest --delta
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
