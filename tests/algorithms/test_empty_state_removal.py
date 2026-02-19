"""Tests for empty state removal optimization."""

from nortl import Engine


def test_empty_state_removal_basic() -> None:
    """Test basic empty state removal using collapse_sync context manager."""
    e = Engine('my_engine')

    # Engine has only the reset state at this point

    # Create three states that can be collapsed
    with e.collapse_sync():
        e.sync()
        e.sync()
        e.sync()

    # Introduce last state that will not be removed
    e.sync()
    e.current_state.name = 'Final State'

    # Run empty state removal
    e.empty_state_removal()

    # S_empty should be removed
    assert len(e.main_worker.states) == 2  # Now we only have two states

    cond, next_state = e.reset_state.transitions[0]

    assert len(e.reset_state.transitions) == 1
    assert cond.render() == "1'h1"
    assert next_state.name == 'Final State'


def test_empty_state_not_removed_with_assignments() -> None:
    """Test that states with assignments are not removed."""
    e = Engine('my_engine')

    with e.collapse_sync():
        e.sync()
        e.sync()
        e.set(e.define_scratch(1), 1)
        e.sync()

    e.sync()

    e.empty_state_removal()

    # State should not be removed because it has assignments
    assert len(e.main_worker.states) == 3
