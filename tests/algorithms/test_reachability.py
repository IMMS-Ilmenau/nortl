from nortl import Const, Engine


def test_reachability_all_reachable() -> None:
    e = Engine('my_engine')

    for _ in range(10):
        e.sync()

    e.reachability_analysis()

    for statelist in e.states.values():
        for state in statelist:
            assert state.get_metadata('reachable', True)


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


def test_reachability_floating() -> None:
    e = Engine('my_engine')

    # Create floating segment of states
    e.current_state = e.create_state()
    e.sync()
    save_state = e.current_state
    e.sync()

    e.reachability_analysis()

    assert not save_state.get_metadata('reachable')


def test_reachability_unreachable_fork() -> None:
    e = Engine('my_engine')
    e.sync()

    with e.fork('test'):
        e.sync()
        save_state1 = e.current_state
        e.sync()

    # Create floating segment of states
    e.current_state = e.create_state()
    with e.fork('test2'):
        e.sync()
        save_state2 = e.current_state
        e.sync()

    e.reachability_analysis()

    assert save_state1.get_metadata('reachable')
    assert not save_state2.get_metadata('reachable')


def test_reachability_prune_unreachable() -> None:
    e = Engine('my_engine')
    e.sync()
    e.sync()
    e.sync()

    # Create floating segment of states
    e.current_state = e.create_state()
    e.sync()
    save_state = e.current_state
    e.sync()

    states_before = len(e.main_worker.states)

    e.prune_unreachable_states()
    state_after = len(e.main_worker.states)

    # Pruning should have deleted 3 states
    assert state_after < states_before
    assert state_after == states_before - 3

    for statelist in e.states.values():
        assert save_state not in statelist

        for state in statelist:
            assert state.get_metadata('reachable', True)
