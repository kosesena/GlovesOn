"""Offline checks must fail immediately if an unmocked database path is reached."""
from unittest.mock import patch

import pytest

from gateway import store


@pytest.fixture(autouse=True)
def no_database():
    with patch.object(store, 'db', side_effect=AssertionError('Offline check attempted database access')):
        yield
