import pytest

from nortl.core.constructs import Condition, Fork
from nortl.core.engine import CoreEngine
from nortl.core.signal import ScratchSignal


def test_memory_map_1() -> None:
    """Test that the Scratch manager class can be initialized correctly."""
    engine = CoreEngine('my_engine')

    scratch_man = engine.scratch_manager
    scratch_man.scratchpad_width = 8

    new_scratch_signal = scratch_man.scratchpad[2:3].as_scratch_signal()
    scratch_man.scratch_signals.append(new_scratch_signal)

    # We expect that only the bits reserved by the scratch signal are marked as true

    expected = [False] * 8
    expected[2] = True
    expected[3] = True

    assert scratch_man.scratch_map == expected


def test_memory_map_2() -> None:
    """Test that the Scratch manager class can be initialized correctly."""
    engine = CoreEngine('my_engine')

    scratch_man = engine.scratch_manager
    scratch_man.scratchpad_width = 8

    new_scratch_signal_1 = scratch_man.scratchpad[2:3].as_scratch_signal()
    scratch_man.scratch_signals.append(new_scratch_signal_1)

    new_scratch_signal_2 = scratch_man.scratchpad[6].as_scratch_signal()
    scratch_man.scratch_signals.append(new_scratch_signal_2)

    # We expect that only the bits reserved by the scratch signal are marked as true

    expected = [False] * 8
    expected[2] = True
    expected[3] = True
    expected[6] = True

    assert scratch_man.scratch_map == expected

    new_scratch_signal_2.release()

    expected[6] = False

    assert scratch_man.scratch_map == expected


def test_memory_map_3() -> None:
    """Test that the Scratch manager class can be initialized correctly."""
    engine = CoreEngine('my_engine')

    scratch_man = engine.scratch_manager
    scratch_man.scratchpad_width = 8

    new_scratch_signal_1 = scratch_man.scratchpad[3:2].as_scratch_signal()
    scratch_man.scratch_signals.append(new_scratch_signal_1)

    new_scratch_signal_2 = scratch_man.scratchpad[6].as_scratch_signal()
    scratch_man.scratch_signals.append(new_scratch_signal_2)

    # We expect that only the bits reserved by the scratch signal are marked as true

    expected = [False] * 8
    expected[2] = True
    expected[3] = True
    expected[6] = True

    assert scratch_man.scratch_map == expected

    new_scratch_signal_2.release()

    expected[6] = False

    assert scratch_man.scratch_map == expected


def test_alloc() -> None:
    """Test that the alloc method finds the first valid place for a new variable."""
    engine = CoreEngine('my_engine')

    scratch_man = engine.scratch_manager
    scratch_man.scratchpad_width = 16

    new_scratch_signal = scratch_man.scratchpad[2:3].as_scratch_signal()
    scratch_man.scratch_signals.append(new_scratch_signal)

    new_scratch_signal = scratch_man.scratchpad[6].as_scratch_signal()
    scratch_man.scratch_signals.append(new_scratch_signal)

    assert engine.scratch_manager.alloc(1) == 0

    assert engine.scratch_manager.alloc(8) == 7

    new_scratch_signal = scratch_man.scratchpad[0].as_scratch_signal()
    scratch_man.scratch_signals.append(new_scratch_signal)

    assert engine.scratch_manager.alloc(1) == 1


def test_write_after_release() -> None:
    engine = CoreEngine('my_engine')
    test = engine.scratch_manager.create(4)

    engine.sync()

    engine.set(test, 1)
    test.release()

    with pytest.raises(Exception):
        engine.set(test, 1)


def test_read_after_release() -> None:
    engine = CoreEngine('my_engine')
    out = engine.define_output('out', 4)
    test = engine.scratch_manager.create(4)

    engine.sync()

    engine.set(test, 1)
    test.release()

    with pytest.raises(Exception):
        engine.set(out, test)


def test_create_and_release_in_context() -> None:
    engine = CoreEngine('my_engine')
    out = engine.define_output('out', 4, 0)

    with Condition(engine, out == 0):
        test = engine.scratch_manager.create(4)
        engine.set(test, 1)
        test.release()

    with pytest.raises(Exception):
        engine.set(out, test)


def test_auto_release_leaving_context() -> None:
    engine = CoreEngine('my_engine')
    out = engine.define_output('out', 4, 0)

    with Condition(engine, out == 0):
        test = engine.scratch_manager.create(4)
        engine.set(test, 1)

    assert test.released


def test_scratch_as_context() -> None:
    engine = CoreEngine('my_engine')

    engine.sync()

    with engine.scratch_manager.create(4) as test:
        pass

    assert test.released


def test_release_in_forked_process() -> None:
    engine = CoreEngine('my_engine')

    engine.sync()

    with Fork(engine, 'f1') as f1:
        test = engine.scratch_manager.create(4)
        print(test.owner.name)
        engine.set(test, 1)
        test.release()
        engine.sync()

    print(f1.running)

    assert not test.released

    f1.cancel()

    assert test.released


def test_parallel_scratch_variables() -> None:
    engine = CoreEngine('my_engine')

    engine.sync()

    with Fork(engine, 'f1') as f1:
        test1 = engine.scratch_manager.create(4)

    with Fork(engine, 'f2') as f2:
        test2 = engine.scratch_manager.create(4)

    assert not test1.released

    f1.cancel()

    assert test1.released
    assert not test2.released  # type:ignore #Weird behavior

    f2.cancel()

    assert test1.released
    assert test2.released


def test_parallel_scratch_access() -> None:
    engine = CoreEngine('my_engine')

    engine.sync()

    with Fork(engine, 'f1') as f1:
        test1 = engine.scratch_manager.create(4)
        engine.set(test1, 1)

    with Fork(engine, 'f2') as f2:
        test2 = engine.scratch_manager.create(4)
        engine.set(test2, 2)

    assert test1.index != test2.index

    f1.cancel()
    f2.cancel()


def test_scratch_signal_disjoint() -> None:
    engine = CoreEngine('my_engine')

    engine.sync()

    a = engine.define_scratch(2)
    b = engine.define_scratch(3)

    engine.sync()
    engine.sync()

    a.release()

    engine.sync()
    engine.sync()

    c = engine.define_scratch(2)
    engine.sync()

    assert not a.states_disjoint(b)
    assert a.states_disjoint(c)


def test_scratch_signal_call_stack_similarity() -> None:
    engine = CoreEngine('my_engine')

    engine.sync()

    a = engine.define_scratch(2)
    b = engine.define_scratch(3)

    engine.sync()

    def test() -> ScratchSignal:
        return engine.define_scratch(3)

    c = test()

    engine.sync()

    assert a.call_stack_similarity(a) == 0
    assert a.call_stack_similarity(b) == -1
    assert b.call_stack_similarity(c) == -2
