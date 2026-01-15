"""Tests for utils directly."""

from src.utils import add, multiply


def test_add_directly():
    assert add(1, 2) == 3


def test_multiply_directly():
    assert multiply(2, 4) == 8
