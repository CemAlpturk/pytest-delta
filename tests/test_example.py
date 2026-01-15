"""Example tests to verify the plugin works."""

import pytest


def test_one():
    assert 1 + 1 == 2


@pytest.mark.delta_always
def test_two():
    """This test always runs regardless of changes."""
    assert 2 + 2 == 4
