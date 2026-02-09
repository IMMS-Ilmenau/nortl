from nortl import Engine


def test_state_merger_no_merge() -> None:
    e = Engine('my_engine')

    for _ in range(10):
        e.sync()

    e.state_merging()


def test_state_merger() -> None:
    # State machine with merges
    e = Engine('my_engine')
    a = e.define_input('A')
    b = e.define_input('B')

    with e.condition(a):
        for _ in range(10):
            e.sync()

    with e.condition(b):
        for _ in range(10):
            e.sync()

    e.state_merging()

    # State machine without merges
    e2 = Engine('my_engine')
    a = e2.define_input('A')
    b = e2.define_input('B')

    with e2.condition(a):
        for _ in range(10):
            e2.sync()

    assert len(e.main_worker.states) == len(e2.main_worker.states)
