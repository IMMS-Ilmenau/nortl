from nortl.core import CoreEngine
from nortl.core.constructs import Condition


def test_condition_enter_exit() -> None:
    """Test that the Condition context manager can be entered and exited without errors."""
    engine = CoreEngine('test_engine')
    input = engine.define_input('In')

    with Condition(engine, input == 1):
        engine.sync()


def test_dual_condition_enter_exit() -> None:
    """Test that the Condition context manager can be entered and exited without errors."""
    engine = CoreEngine('test_engine')
    input = engine.define_input('In')

    with Condition(engine, input == 1):
        engine.sync()

    with Condition(engine, input == 2):
        engine.sync()
