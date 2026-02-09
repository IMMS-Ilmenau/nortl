from nortl import Const, Engine


def test_reachability_all_reachable() -> None:
    e = Engine('my_engine')

    for _ in range(10):
        e.sync()

    e.reachability_analysis()

    for statelist in e.states.values():
        for state in statelist:
            assert state.get_metadata('reachable', True)


def test_reachability_unreachable_condition() -> None:
    e = Engine('my_engine')

    with e.condition(Const(0) == 1):
        e.sync()
        save_state = e.current_state
        e.sync()

    e.reachability_analysis()

    assert not save_state.get_metadata('reachable')


def test_reachability_in_fork() -> None:
    e = Engine('my_engine')

    with e.condition(Const(1) == 1):
        e.sync()
        with e.fork('test'):
            e.sync()
            save_state = e.current_state
            e.sync()
        e.sync()

    e.reachability_analysis()

    assert save_state.get_metadata('reachable')


def test_reachability_unreachable_fork() -> None:
    e = Engine('my_engine')

    with e.condition(Const(1) == 1):
        e.sync()
        with e.fork('test'):
            e.sync()
            save_state1 = e.current_state
            e.sync()
        e.sync()

    with e.condition(Const(1) == 0):
        e.sync()
        with e.fork('test2'):
            e.sync()
            save_state2 = e.current_state
            e.sync()
        e.sync()

    e.reachability_analysis()

    assert save_state1.get_metadata('reachable')
    assert not save_state2.get_metadata('reachable')


def test_reachability_prune_unreachable() -> None:
    e = Engine('my_engine')

    with e.condition(Const(0) == 1):
        e.sync()
        save_state = e.current_state
        e.sync()

    e.prune_unreachable_states()

    for statelist in e.states.values():
        assert save_state not in statelist

        for state in statelist:
            assert state.get_metadata('reachable', True)
