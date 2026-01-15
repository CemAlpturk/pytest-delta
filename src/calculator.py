"""Calculator module that uses utils."""

from src.utils import add, multiply


def calculate(operation: str, a: int, b: int) -> int:
    """Perform a calculation."""
    if operation == "add":
        return add(a, b)
    elif operation == "multiply":
        return multiply(a, b)
    else:
        raise ValueError(f"Unknown operation: {operation}")


# Marker test
