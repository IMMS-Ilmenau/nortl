# type: ignore
import pytest

from nortl import Engine


@pytest.fixture
def engine() -> Engine:
    """Returns a noRTL Engine."""
    return Engine('test_engine', reset_state_name='IDLE')
