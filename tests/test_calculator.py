"""Tests for the calculator module."""

from src.calculator import calculate


def test_add():
    assert calculate("add", 2, 3) == 5


def test_multiply():
    assert calculate("multiply", 2, 3) == 6


def test_invalid_operation():
    try:
        calculate("divide", 2, 3)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "divide" in str(e)
