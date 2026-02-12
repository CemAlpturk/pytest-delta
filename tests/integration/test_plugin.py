"""Integration tests for the pytest-delta plugin using pytester."""

from __future__ import annotations

import pytest


@pytest.fixture
def delta_project(pytester: pytest.Pytester) -> pytest.Pytester:
    """Create a minimal project with source and test files."""
    pytester.makepyfile(
        **{
            "src/__init__": "",
            "src/utils": "def add(a, b): return a + b\ndef multiply(a, b): return a * b",
            "src/calculator": "from src.utils import add\ndef calc(a, b): return add(a, b)",
            "test_utils": "from src.utils import add\ndef test_add(): assert add(1, 2) == 3",
            "test_calc": "from src.calculator import calc\ndef test_calc(): assert calc(1, 2) == 3",
            "test_independent": "def test_ind(): assert True",
        }
    )
    pytester.makepyprojecttoml("[tool.pytest.ini_options]\npythonpath = ['.']")
    return pytester


class TestFirstRun:
    def test_runs_all_tests(self, delta_project: pytest.Pytester) -> None:
        result = delta_project.runpytest("--delta", "--delta-debug")
        result.assert_outcomes(passed=3)

    def test_creates_delta_file(self, delta_project: pytest.Pytester) -> None:
        delta_project.runpytest("--delta")
        assert (delta_project.path / ".delta.msgpack").exists()

    def test_custom_delta_file_path(self, delta_project: pytest.Pytester) -> None:
        delta_project.runpytest("--delta", "--delta-file", "custom.msgpack")
        assert (delta_project.path / "custom.msgpack").exists()


class TestNoChanges:
    def test_deselects_all_tests(self, delta_project: pytest.Pytester) -> None:
        delta_project.runpytest("--delta")
        result = delta_project.runpytest("--delta", "--delta-debug", "-v")
        result.assert_outcomes()  # No tests run
        assert result.ret == 0

    def test_exits_0(self, delta_project: pytest.Pytester) -> None:
        delta_project.runpytest("--delta")
        result = delta_project.runpytest("--delta")
        assert result.ret == 0


class TestChangedSource:
    def test_changed_source_runs_affected_tests(
        self, delta_project: pytest.Pytester
    ) -> None:
        # First run: establish baseline
        delta_project.runpytest("--delta")

        # Modify src/utils.py
        (delta_project.path / "src" / "utils.py").write_text(
            "def add(a, b): return a + b\ndef multiply(a, b): return a * b\n# changed"
        )

        result = delta_project.runpytest("--delta", "--delta-debug", "-v")
        # test_utils and test_calc should run (both depend on utils directly or transitively)
        # test_independent should be deselected
        assert result.ret == 0
        result.stdout.fnmatch_lines(["*test_add*PASSED*"])
        result.stdout.fnmatch_lines(["*test_calc*PASSED*"])
        # test_independent should be deselected
        assert (
            "test_ind" not in result.stdout.str() or "deselected" in result.stdout.str()
        )

    def test_transitive_dependency(self, delta_project: pytest.Pytester) -> None:
        # First run
        delta_project.runpytest("--delta")

        # Modify utils.py — calculator depends on it transitively
        (delta_project.path / "src" / "utils.py").write_text(
            "def add(a, b): return a + b  # modified\ndef multiply(a, b): return a * b"
        )

        result = delta_project.runpytest("--delta", "--delta-debug", "-v")
        # Both test_utils and test_calc should run due to transitive dependency
        result.stdout.fnmatch_lines(["*test_calc*PASSED*"])


class TestChangedTestFile:
    def test_changed_test_runs(self, delta_project: pytest.Pytester) -> None:
        delta_project.runpytest("--delta")

        # Modify only the test file
        (delta_project.path / "test_independent.py").write_text(
            "def test_ind(): assert True  # modified"
        )

        result = delta_project.runpytest("--delta", "--delta-debug", "-v")
        result.stdout.fnmatch_lines(["*test_ind*PASSED*"])
        result.assert_outcomes(passed=1)


class TestNewTestFile:
    def test_new_test_file_runs(self, delta_project: pytest.Pytester) -> None:
        delta_project.runpytest("--delta")

        # Add a new test file
        (delta_project.path / "test_new.py").write_text(
            "def test_new(): assert 1 + 1 == 2"
        )

        result = delta_project.runpytest("--delta", "--delta-debug", "-v")
        result.stdout.fnmatch_lines(["*test_new*PASSED*"])


class TestDeltaAlwaysMarker:
    def test_delta_always_runs(self, delta_project: pytest.Pytester) -> None:
        # Add a test with delta_always marker
        (delta_project.path / "test_always.py").write_text(
            "import pytest\n\n@pytest.mark.delta_always\ndef test_always(): assert True"
        )
        delta_project.runpytest("--delta")

        # No changes, but delta_always test should still run
        result = delta_project.runpytest("--delta", "--delta-debug", "-v")
        result.stdout.fnmatch_lines(["*test_always*PASSED*"])


class TestFailedTests:
    def test_failed_tests_dont_save(self, delta_project: pytest.Pytester) -> None:
        delta_project.runpytest("--delta")

        # Get the modification time of the delta file
        delta_path = delta_project.path / ".delta.msgpack"
        mtime_before = delta_path.stat().st_mtime

        # Modify a test to fail
        (delta_project.path / "test_independent.py").write_text(
            "def test_ind(): assert False"
        )

        import time

        time.sleep(0.1)  # Ensure mtime would differ

        result = delta_project.runpytest("--delta")
        assert result.ret != 0

        # Delta file should not be updated
        mtime_after = delta_path.stat().st_mtime
        assert mtime_before == mtime_after


class TestCLIOptions:
    def test_delta_no_save(self, delta_project: pytest.Pytester) -> None:
        result = delta_project.runpytest("--delta", "--delta-no-save")
        result.assert_outcomes(passed=3)
        assert not (delta_project.path / ".delta.msgpack").exists()

    def test_delta_rebuild(self, delta_project: pytest.Pytester) -> None:
        # First run
        delta_project.runpytest("--delta")
        # Rebuild should run all tests (treats as first run)
        result = delta_project.runpytest("--delta", "--delta-rebuild", "-v")
        result.assert_outcomes(passed=3)

    def test_without_delta_flag_runs_normally(
        self, delta_project: pytest.Pytester
    ) -> None:
        result = delta_project.runpytest("-v")
        result.assert_outcomes(passed=3)


class TestConftestChanges:
    def test_conftest_change_runs_subtree(self, pytester: pytest.Pytester) -> None:
        # Use "checks/" instead of "tests/" to avoid collision with our own tests/ package
        pytester.makepyfile(
            **{
                "checks/__init__": "",
                "checks/conftest": "import pytest\n\n@pytest.fixture\ndef val(): return 1",
                "checks/test_a": "def test_a(val): assert val == 1",
                "checks/test_b": "def test_b(): assert True",
                "test_top": "def test_top(): assert True",
            }
        )
        pytester.makepyprojecttoml(
            "[tool.pytest.ini_options]\npythonpath = ['.']\ntestpaths = ['checks', '.']"
        )

        # First run
        pytester.runpytest("--delta")

        # Modify the conftest
        (pytester.path / "checks" / "conftest.py").write_text(
            "import pytest\n\n@pytest.fixture\ndef val(): return 1  # changed"
        )

        result = pytester.runpytest("--delta", "--delta-debug", "-v")
        # Both checks/test_a and checks/test_b should run (in conftest's subtree)
        # test_top should NOT run (outside the subtree)
        result.stdout.fnmatch_lines(["*test_a*PASSED*"])
        result.stdout.fnmatch_lines(["*test_b*PASSED*"])


class TestDeletedFile:
    def test_deleted_source_no_crash(self, delta_project: pytest.Pytester) -> None:
        delta_project.runpytest("--delta")

        # Delete a source file
        (delta_project.path / "src" / "calculator.py").unlink()
        # Also update test_calc to not import deleted module
        (delta_project.path / "test_calc.py").write_text("def test_calc(): assert True")

        result = delta_project.runpytest("--delta", "--delta-debug", "-v")
        assert result.ret == 0


class TestPluginDisabled:
    def test_no_filtering_without_flag(self, delta_project: pytest.Pytester) -> None:
        # Run with delta to create file
        delta_project.runpytest("--delta")
        # Run without delta -- should run all tests
        result = delta_project.runpytest("-v")
        result.assert_outcomes(passed=3)
