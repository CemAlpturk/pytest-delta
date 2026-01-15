"""Integration tests for the pytest-delta plugin."""

from __future__ import annotations

import subprocess
from pathlib import Path
from textwrap import dedent

import pytest


def run_pytest(
    project_dir: Path,
    *args: str,
    env: dict | None = None,
) -> subprocess.CompletedProcess:
    """Run pytest in a project directory.

    Args:
        project_dir: The project directory.
        *args: Additional pytest arguments.
        env: Environment variables.

    Returns:
        The completed process.
    """
    import os

    full_env = os.environ.copy()
    if env:
        full_env.update(env)

    return subprocess.run(
        ["python", "-m", "pytest", *args],
        cwd=project_dir,
        capture_output=True,
        text=True,
        env=full_env,
    )


def init_git_repo(path: Path) -> None:
    """Initialize a git repository with a commit."""
    subprocess.run(["git", "init"], cwd=path, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=path,
        capture_output=True,
        check=True,
    )


def git_commit(path: Path, message: str) -> None:
    """Add all files and commit."""
    subprocess.run(["git", "add", "."], cwd=path, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", message],
        cwd=path,
        capture_output=True,
        check=True,
    )


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Create a minimal project structure for testing."""
    # Create source files
    src = tmp_path / "src"
    src.mkdir()

    (src / "__init__.py").write_text("")

    (src / "utils.py").write_text(
        dedent(
            """
        def add(a, b):
            return a + b

        def multiply(a, b):
            return a * b
    """
        )
    )

    (src / "calculator.py").write_text(
        dedent(
            """
        from src.utils import add, multiply

        def calculate(op, a, b):
            if op == "add":
                return add(a, b)
            return multiply(a, b)
    """
        )
    )

    # Create test files
    tests = tmp_path / "tests"
    tests.mkdir()

    (tests / "test_utils.py").write_text(
        dedent(
            """
        from src.utils import add, multiply

        def test_add():
            assert add(1, 2) == 3

        def test_multiply():
            assert multiply(2, 3) == 6
    """
        )
    )

    (tests / "test_calculator.py").write_text(
        dedent(
            """
        from src.calculator import calculate

        def test_calculate_add():
            assert calculate("add", 1, 2) == 3

        def test_calculate_multiply():
            assert calculate("multiply", 2, 3) == 6
    """
        )
    )

    (tests / "test_independent.py").write_text(
        dedent(
            """
        def test_independent():
            assert 1 + 1 == 2
    """
        )
    )

    # Create pyproject.toml
    (tmp_path / "pyproject.toml").write_text(
        dedent(
            """
        [project]
        name = "test-project"
        version = "0.1.0"

        [tool.pytest.ini_options]
        pythonpath = ["."]
    """
        )
    )

    # Initialize git
    init_git_repo(tmp_path)
    git_commit(tmp_path, "Initial commit")

    return tmp_path


class TestPluginIntegration:
    """Integration tests for the plugin."""

    def test_first_run_creates_delta_file(self, project_dir: Path) -> None:
        """Test that first run creates a delta file."""
        delta_file = project_dir / ".delta.msgpack"
        assert not delta_file.exists()

        result = run_pytest(project_dir, "--delta")
        assert result.returncode == 0
        assert delta_file.exists()

    def test_first_run_executes_all_tests(self, project_dir: Path) -> None:
        """Test that first run executes all tests."""
        result = run_pytest(project_dir, "--delta", "-v")

        assert result.returncode == 0
        assert "test_add" in result.stdout
        assert "test_multiply" in result.stdout
        assert "test_calculate_add" in result.stdout
        assert "test_calculate_multiply" in result.stdout
        assert "test_independent" in result.stdout
        assert "5 passed" in result.stdout

    def test_no_changes_deselects_all_tests(self, project_dir: Path) -> None:
        """Test that no changes deselects all tests."""
        # First run
        run_pytest(project_dir, "--delta")

        # Second run without changes
        result = run_pytest(project_dir, "--delta", "-v")

        assert "5 deselected" in result.stdout

    def test_changed_file_runs_affected_tests(self, project_dir: Path) -> None:
        """Test that changing a file runs affected tests."""
        # First run
        run_pytest(project_dir, "--delta")

        # Modify utils.py
        utils_file = project_dir / "src" / "utils.py"
        utils_file.write_text(
            dedent(
                """
            def add(a, b):
                return a + b  # Modified

            def multiply(a, b):
                return a * b
        """
            )
        )
        git_commit(project_dir, "Modify utils")

        # Run with delta
        result = run_pytest(project_dir, "--delta", "-v")

        # Should run tests that depend on utils.py
        assert "test_add" in result.stdout
        assert "test_multiply" in result.stdout
        assert "test_calculate_add" in result.stdout
        assert "test_calculate_multiply" in result.stdout

        # Independent test should be deselected
        assert "test_independent" not in result.stdout or "deselected" in result.stdout

    def test_independent_test_not_run_on_unrelated_change(
        self, project_dir: Path
    ) -> None:
        """Test that independent tests are not run when unrelated files change."""
        # First run
        run_pytest(project_dir, "--delta")

        # Modify only utils.py
        utils_file = project_dir / "src" / "utils.py"
        utils_file.write_text(
            dedent(
                """
            def add(a, b):
                return a + b  # Changed

            def multiply(a, b):
                return a * b
        """
            )
        )
        git_commit(project_dir, "Change utils")

        # Run with delta and debug
        result = run_pytest(project_dir, "--delta", "--delta-debug", "-v")

        # test_independent should be deselected
        assert "1 deselected" in result.stdout or "deselected" in result.stdout

    def test_delta_always_marker(self, project_dir: Path) -> None:
        """Test that delta_always marker causes tests to always run."""
        # Add a test with delta_always marker
        (project_dir / "tests" / "test_always.py").write_text(
            dedent(
                """
            import pytest

            @pytest.mark.delta_always
            def test_always_runs():
                assert True
        """
            )
        )
        git_commit(project_dir, "Add always test")

        # First run
        run_pytest(project_dir, "--delta")

        # Modify only utils.py (test_always doesn't depend on it)
        utils_file = project_dir / "src" / "utils.py"
        utils_file.write_text(
            dedent(
                """
            def add(a, b):
                return a + b  # Modified again

            def multiply(a, b):
                return a * b
        """
            )
        )
        git_commit(project_dir, "Modify utils again")

        result = run_pytest(project_dir, "--delta", "-v")

        # test_always_runs should be executed
        assert "test_always_runs" in result.stdout
        assert "PASSED" in result.stdout

    def test_delta_no_save_flag(self, project_dir: Path) -> None:
        """Test that --delta-no-save doesn't update the delta file."""
        # First run to create delta file
        run_pytest(project_dir, "--delta")

        delta_file = project_dir / ".delta.msgpack"
        original_content = delta_file.read_bytes()

        # Make a change and commit
        (project_dir / "src" / "utils.py").write_text(
            "# changed\ndef add(a,b): return a+b"
        )
        git_commit(project_dir, "Change")

        # Run with --delta-no-save
        run_pytest(project_dir, "--delta", "--delta-no-save")

        # Delta file should be unchanged
        assert delta_file.read_bytes() == original_content

    def test_delta_rebuild_flag(self, project_dir: Path) -> None:
        """Test that --delta-rebuild forces a full rebuild."""
        # First run
        run_pytest(project_dir, "--delta")

        # Run with rebuild - should run all tests
        result = run_pytest(project_dir, "--delta", "--delta-rebuild", "-v")

        assert "5 passed" in result.stdout

    def test_delta_debug_shows_info(self, project_dir: Path) -> None:
        """Test that --delta-debug shows debug information."""
        result = run_pytest(project_dir, "--delta", "--delta-debug")

        assert "[pytest-delta]" in result.stdout
        assert "Plugin enabled" in result.stdout

    def test_delta_ignore_pattern(self, project_dir: Path) -> None:
        """Test that --delta-ignore excludes files from dependency analysis."""
        # Create an ignored file
        (project_dir / "src" / "ignored_module.py").write_text("x = 1")
        (project_dir / "tests" / "test_ignored.py").write_text(
            "from src.ignored_module import x\ndef test_ignored(): assert x == 1"
        )
        git_commit(project_dir, "Add ignored module")

        # First run, ignoring the module
        run_pytest(
            project_dir,
            "--delta",
            "--delta-ignore",
            "**/ignored_module.py",
            "--delta-rebuild",
        )

        # Modify the ignored file
        (project_dir / "src" / "ignored_module.py").write_text("x = 2  # Changed")
        git_commit(project_dir, "Change ignored module")

        # Run again - changes to ignored file shouldn't trigger tests
        result = run_pytest(
            project_dir, "--delta", "--delta-ignore", "**/ignored_module.py", "-v"
        )

        # The change should be ignored, so tests should be deselected
        assert "deselected" in result.stdout

    def test_failed_tests_dont_update_delta(self, project_dir: Path) -> None:
        """Test that failed tests don't update the delta file."""
        # First run
        run_pytest(project_dir, "--delta")

        delta_file = project_dir / ".delta.msgpack"
        original_content = delta_file.read_bytes()

        # Add a failing test
        (project_dir / "tests" / "test_fail.py").write_text(
            dedent(
                """
            def test_will_fail():
                assert False
        """
            )
        )
        git_commit(project_dir, "Add failing test")

        # Run - should fail
        result = run_pytest(project_dir, "--delta")
        assert result.returncode != 0

        # Delta file should be unchanged
        assert delta_file.read_bytes() == original_content

    def test_transitive_dependencies(self, project_dir: Path) -> None:
        """Test that transitive dependencies are detected."""
        # Add a third level of dependency
        (project_dir / "src" / "deep.py").write_text("VALUE = 42")

        utils_file = project_dir / "src" / "utils.py"
        utils_file.write_text(
            dedent(
                """
            from src.deep import VALUE

            def add(a, b):
                return a + b

            def multiply(a, b):
                return a * b
        """
            )
        )
        git_commit(project_dir, "Add deep dependency")

        # First run
        run_pytest(project_dir, "--delta", "--delta-rebuild")

        # Modify the deep file
        (project_dir / "src" / "deep.py").write_text("VALUE = 100  # Changed")
        git_commit(project_dir, "Modify deep")

        # Run with delta
        result = run_pytest(project_dir, "--delta", "-v", "--delta-debug")

        # All tests depending on utils (which depends on deep) should run
        assert "test_add" in result.stdout
        assert "test_calculate_add" in result.stdout


class TestPluginWithoutGit:
    """Tests for plugin behavior without git."""

    def test_runs_all_tests_without_git(self, tmp_path: Path) -> None:
        """Test that all tests run when not in a git repo."""
        # Create a simple test file (no git init)
        (tmp_path / "test_simple.py").write_text("def test_one(): assert True")

        result = run_pytest(tmp_path, "--delta", "-v")

        assert result.returncode == 0
        assert "test_one" in result.stdout
        assert "1 passed" in result.stdout
