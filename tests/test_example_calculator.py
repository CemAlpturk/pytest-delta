"""Test cases for example calculator."""

import pytest
from pytest_delta.example_calculator import add, divide, multiply


def test_add():
    """Test addition function."""
    assert add(2, 3) == 5
    assert add(-1, 1) == 0
    assert add(0.1, 0.2) == pytest.approx(0.3)


def test_multiply():
    """Test multiplication function."""
    assert multiply(3, 4) == 12
    assert multiply(-2, 5) == -10
    assert multiply(0, 100) == 0


def test_divide():
    """Test division function."""
    assert divide(10, 2) == 5
    assert divide(1, 3) == pytest.approx(0.3333333)

    with pytest.raises(ValueError):
        divide(5, 0)
