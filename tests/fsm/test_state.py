from nortl import Const, Engine


def test_unreachable_transitions_not_added() -> None:
    e = Engine('my_engine')

    e.sync()

    c = Const(1)

    e.jump_if(c == 0, e.reset_state)  # Transition that is never taken

    assert len(e.current_state.transitions) == 0


def test_state_metadata_template() -> None:
    """Test that states created via engine.sync() inherit metadata from state_metadata_template."""
    e = Engine('test_engine')

    # Set the state metadata template
    e.state_metadata_template = {'key1': 'value1', 'key2': 42}

    # Create states using sync()
    e.sync()

    # Verify that each state has the metadata from the template
    state = e.current_state
    assert state.has_metadata('key1')
    assert state.get_metadata('key1') == 'value1'
    assert state.has_metadata('key2')
    assert state.get_metadata('key2') == 42
