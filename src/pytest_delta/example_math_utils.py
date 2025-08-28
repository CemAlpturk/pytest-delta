"""Example math utilities that depend on calculator."""

from .example_calculator import add, multiply


def calculate_area(width: float, height: float) -> float:
    """Calculate rectangular area."""
    return multiply(width, height)


def calculate_perimeter(width: float, height: float) -> float:
    """Calculate rectangular perimeter."""
    return multiply(2, add(width, height))
