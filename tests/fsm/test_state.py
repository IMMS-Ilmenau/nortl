from nortl import Const, Engine


def test_unreachable_transitions_not_added() -> None:
    e = Engine('my_engine')

    e.sync()

    c = Const(1)

    e.jump_if(c == 0, e.reset_state)  # Transition that is never taken

    assert len(e.current_state.transitions) == 0
