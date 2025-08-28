# pytest-delta Development Instructions

pytest-delta is a pytest plugin that reduces test execution time by running only tests affected by code changes. It creates dependency graphs based on Python imports and intelligently selects tests using Git integration.

**ALWAYS follow these instructions first and only fallback to search or bash commands when you encounter unexpected information that contradicts what is documented here.**

# pytest-delta Development Instructions

pytest-delta is a pytest plugin that reduces test execution time by running only tests affected by code changes. It creates dependency graphs based on Python imports and intelligently selects tests using Git integration.

**ALWAYS follow these instructions first and only fallback to search or bash commands when you encounter unexpected information that contradicts what is documented here.**

## Working Effectively

### Prerequisites
- Python 3.12+ required (check with `python3 --version`)
- pytest and gitpython packages must be available
- Git repository (plugin falls back to running all tests if not in Git repo)

### Bootstrap Development Environment

**Method 1: Full Installation (when network allows)**
```bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install package in editable mode (takes ~6 seconds when network works)
pip install -e .

# Verify installation
pytest --help | grep -A 10 "pytest-delta"
```

**Method 2: Manual Setup (for restricted environments)**
```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# If dependencies are available, install them:
pip install pytest gitpython  # May fail due to network restrictions

# Set up Python path for development
export PYTHONPATH=$PWD/src:$PYTHONPATH

# Test import works
python3 -c "import pytest_delta; print('Plugin import successful')"
```

**CRITICAL LIMITATION**: In network-restricted environments, initial setup may fail due to PyPI timeouts. The plugin requires pytest and gitpython to function.

### Run Tests
**IMPORTANT**: These commands assume pytest is available in your environment.

```bash
# Activate virtual environment first
source .venv/bin/activate
export PYTHONPATH=$PWD/src:$PYTHONPATH  # If using manual setup

# Run full test suite - FAST: takes 0.06s execution, ~0.35s total. NEVER CANCEL.
pytest tests/ -v

# Test plugin functionality (requires working pytest installation)
pytest --delta -v  # First run: creates .delta.json, runs all tests
pytest --delta -v  # Second run: detects no changes, skips tests
```

### Test Plugin Options
```bash
source .venv/bin/activate

# Force regeneration and run all tests
pytest --delta --delta-force -v

# Custom delta file location
pytest --delta --delta-filename custom-name --delta-dir /path/to/dir -v

# Ignore patterns during dependency analysis
pytest --delta --delta-ignore "*.pyc" --delta-ignore "__pycache__" -v
```

### Code Quality and Linting
**IMPORTANT**: These commands assume ruff and mypy are available.

```bash
source .venv/bin/activate

# Install linting tools (takes ~4 seconds, may fail in restricted networks)
pip install ruff mypy

# Run linter - FAST: takes 0.01s. NEVER CANCEL.
ruff check .

# Check formatting - FAST: takes 0.01s. NEVER CANCEL.
ruff format --check .

# Fix formatting if needed
ruff format .

# Run type checker - takes ~4.4s. NEVER CANCEL.
mypy src/
# Note: Currently has 3 type annotation issues in dependency_analyzer.py and delta_manager.py
```

## Validation

### Manual Testing Workflow
ALWAYS run through this complete validation after making changes **if pytest is available**:

1. **Basic Plugin Functionality**:
   ```bash
   source .venv/bin/activate
   export PYTHONPATH=$PWD/src:$PYTHONPATH  # If using manual setup
   pytest --delta -v  # Should run all tests first time
   pytest --delta -v  # Should skip tests if no changes
   ```

2. **Change Detection**:
   ```bash
   # Modify a source file
   echo "# Test change" >> src/pytest_delta/__init__.py
   pytest --delta -v  # Should detect changes and run affected tests
   git checkout -- src/pytest_delta/__init__.py  # Revert change
   ```

3. **Command Line Options**:
   ```bash
   pytest --delta --delta-force -v  # Force mode
   pytest --delta --delta-filename test --delta-dir /tmp -v  # Custom location
   ```

### Alternative Validation (without pytest/git dependencies)
If pytest and gitpython are not available, you can still validate basic functionality:

```bash
# Test dependency analysis functionality  
python3 -c "
import sys
sys.path.insert(0, 'src')
from pytest_delta.dependency_analyzer import DependencyAnalyzer
from pathlib import Path
root = Path('.').resolve()
analyzer = DependencyAnalyzer(root)
files = analyzer._find_python_files()
print(f'Found {len(files)} Python files in project:')
for f in sorted(files):
    rel_path = f.relative_to(root)
    print(f'  {rel_path}')
"

# Test that core modules can be imported individually
python3 -c "
import sys
sys.path.insert(0, 'src')
# Only import modules without external dependencies
import pytest_delta
print(f'pytest-delta version: {pytest_delta.__version__}')
print('Basic import validation successful')
"
```

**Note**: Full plugin testing requires pytest and gitpython to be available. The plugin cannot function without these dependencies.

### Expected Test Results
- **Test suite**: All 13 tests should pass in under 1 second
- **Plugin integration**: `pytest --delta` should work without errors
- **Change detection**: Plugin should detect file modifications correctly
- **No changes**: Plugin should skip tests when no changes detected

## Project Structure

### Repository Layout
```
.
├── .gitignore (excludes .venv/, __pycache__/, .delta.json)
├── LICENSE (MIT)
├── README.md
├── pyproject.toml (Poetry config, Python 3.12+ required)
├── src/
│   └── pytest_delta/
│       ├── __init__.py (version 0.1.0)
│       ├── plugin.py (main entry point, 82 lines)
│       ├── dependency_analyzer.py (255 lines, dependency graph logic)
│       └── delta_manager.py (manages .delta.json metadata)
└── tests/
    ├── __init__.py
    └── test_plugin.py (comprehensive test suite, 13 test cases)
```

**Total**: 6 Python files (4 source + 2 test files)

### Key Components
- **plugin.py**: Main pytest plugin with CLI options and hooks
- **dependency_analyzer.py**: Analyzes Python imports to build dependency graphs
- **delta_manager.py**: Manages .delta.json metadata file
- **tests/test_plugin.py**: Comprehensive test suite (13 test cases)

### Important Files to Check After Changes
- Always run tests after modifying any file in `src/pytest_delta/`
- Check that plugin entry point works: `pytest --delta --help`
- Validate dependency analysis if changing `dependency_analyzer.py`
- Test delta file management if changing `delta_manager.py`

## Common Tasks

### Development Workflow
```bash
# 1. Make your changes
# 2. Run linting
source .venv/bin/activate
ruff check .
ruff format .

# 3. Run tests
pytest tests/ -v

# 4. Test plugin functionality
pytest --delta -v

# 5. Manual validation
echo "# test" >> src/pytest_delta/__init__.py
pytest --delta -v  # Should detect changes
git checkout -- src/pytest_delta/__init__.py
```

### Debugging Plugin Issues
```bash
# Enable verbose pytest output
pytest --delta -v -s

# Check plugin is loaded
pytest --delta --tb=long

# Test without delta (baseline)
pytest tests/ -v
```

## Timing Expectations and Timeouts

**CRITICAL: NEVER CANCEL these commands before completion times:**

- **Environment setup**: ~6 seconds - Set timeout to 60+ seconds
- **Test suite**: ~0.35 seconds total - Set timeout to 30+ seconds  
- **Plugin execution**: ~0.3 seconds - Set timeout to 30+ seconds
- **Linting (ruff)**: ~0.01 seconds - Set timeout to 30+ seconds
- **Type checking (mypy)**: ~4.4 seconds - Set timeout to 60+ seconds
- **Installing lint tools**: ~4 seconds - Set timeout to 60+ seconds

## Known Limitations

### Network Restrictions
- **Poetry**: Not available due to network restrictions. Use pip-based workflow instead.
- **Full build**: `python -m build` fails due to poetry-core download timeouts. Use pip development installation.
- **Fresh installations**: `pip install -e .` may fail with network timeouts. In restricted environments, dependencies may need to be pre-installed or available locally.
- **Package publishing**: Not testable in restricted environments.

### Type Issues
Current mypy issues (non-blocking for functionality):
- `dependency_analyzer.py:128`: Need type annotation for "dependencies"
- `dependency_analyzer.py:244`: Need type annotation for "reverse_deps" 
- `delta_manager.py:29`: Return type annotation issue

### Git Integration
- Plugin works in Git repositories
- Falls back to running all tests when not in Git repo
- Requires committed changes for optimal change detection

## CI/CD Integration

The plugin does not currently have GitHub Actions workflows, but when adding them:
- Use `pip install -e .` (not Poetry) due to network restrictions
- Set appropriate timeouts for test runs (minimum 60 seconds)
- Include linting steps: `ruff check .` and `ruff format --check .`
- Consider type checking: `mypy src/` (currently has 3 issues)

## Quick Reference Commands

```bash
# Complete setup from scratch (if network allows)
python3 -m venv .venv && source .venv/bin/activate && pip install -e .

# Manual setup for restricted environments:
python3 -m venv .venv && source .venv/bin/activate
export PYTHONPATH=$PWD/src:$PYTHONPATH

# Basic validation (works without external dependencies):
python3 -c "import sys; sys.path.insert(0, 'src'); import pytest_delta; print('Version:', pytest_delta.__version__)"

# Full testing workflow (requires pytest):
pytest tests/ -v && pytest --delta -v && ruff check . && ruff format --check .

# Plugin help (requires pytest):
pytest --delta --help

# Clean slate test (requires pytest):
rm -f .delta.json && pytest --delta -v

# File discovery test (works without dependencies):
python3 -c "import sys; sys.path.insert(0, 'src'); from pytest_delta.dependency_analyzer import DependencyAnalyzer; from pathlib import Path; files = DependencyAnalyzer(Path('.'))._find_python_files(); print(f'{len(files)} Python files found')"
```

**Always verify commands work in your specific environment. Network restrictions may prevent full setup.**