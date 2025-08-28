# pytest-delta

Run only tests impacted by your code changes (delta-based selection) for pytest.

## Overview

pytest-delta is a pytest plugin that reduces test execution time by running only the tests that are potentially affected by your code changes. It creates a directional dependency graph based on Python imports and selects tests intelligently based on what files have changed since the last successful test run.

## Features

- **Smart Test Selection**: Only runs tests affected by changed files
- **Dependency Tracking**: Creates a dependency graph based on Python imports
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
- `--delta-filename NAME`: Specify filename for delta metadata file (default: `.delta`, `.json` extension added automatically)
- `--delta-dir PATH`: Specify directory for delta metadata file (default: current directory)
- `--delta-force`: Force regeneration of delta file and run all tests
- `--delta-ignore PATTERN`: Ignore file patterns during dependency analysis (can be used multiple times)

### Examples

```bash
# Run only affected tests
pytest --delta

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

## Configuration

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

- Finds Python files in `src/` and `tests/` directories
- Excludes virtual environments, `__pycache__`, and other irrelevant directories
- Creates dependency graphs based on import statements
- Maps test files to source files using naming conventions

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
