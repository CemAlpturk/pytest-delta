"""Test cases for example math utilities."""

from pytest_delta.example_math_utils import calculate_area, calculate_perimeter


def test_calculate_area():
    """Test area calculation."""
    assert calculate_area(5, 4) == 20
    assert calculate_area(2.5, 3.0) == 7.5


def test_calculate_perimeter():
    """Test perimeter calculation."""
    assert calculate_perimeter(5, 4) == 18
    assert calculate_perimeter(2.5, 3.0) == 11.0
