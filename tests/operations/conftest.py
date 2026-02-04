# type: ignore
import pytest

from nortl.core.engine import CoreEngine
from nortl.core.operations import Var
from nortl.core.signal import Signal


@pytest.fixture()
def engine() -> CoreEngine:
    """NoRTL Engine."""
    return CoreEngine('my_engine')


@pytest.fixture
def a(engine: CoreEngine) -> Signal:
    """Signal a."""
    return Signal(engine, 'input', 'a')


@pytest.fixture
def b(engine: CoreEngine) -> Signal:
    """Signal b."""
    return Signal(engine, 'input', 'b')


@pytest.fixture
def c(engine: CoreEngine) -> Signal:
    """Signal c."""
    return Signal(engine, 'input', 'c')


@pytest.fixture
def byte(engine: CoreEngine) -> Signal:
    """8-Bit Signal byte."""
    return Signal(engine, 'input', 'byte', width=8)


@pytest.fixture
def scratch_pad(engine: CoreEngine) -> Signal:
    """Scratch pad signal."""
    return Signal(engine, 'input', 'byte', width=Var(32))
