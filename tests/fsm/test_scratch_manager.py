import pytest

from nortl.core.constructs import Condition, Fork
from nortl.core.engine import CoreEngine
from nortl.core.exceptions import AccessAfterReleaseError


def test_memory_map_1() -> None:
    """Test that the Scratch manager class can be initialized correctly."""
    engine = CoreEngine('my_engine')

    zone = engine.scratch_manager.active_zone
    zone.width = 8

    new_scratch_signal = zone.scratchpad[2:3].as_scratch_signal()
    zone.active_view._scratch_signals.append(new_scratch_signal)  # type: ignore[arg-type]

    # We expect that only the bits reserved by the scratch signal are marked as true

    expected = [False] * 8
    expected[2] = True
    expected[3] = True

    assert zone.scratch_map == expected


def test_memory_map_2() -> None:
    """Test that the Scratch manager class can be initialized correctly."""
    engine = CoreEngine('my_engine')

    zone = engine.scratch_manager.active_zone
    zone.width = 8

    new_scratch_signal_1 = zone.scratchpad[2:3].as_scratch_signal()
    zone.active_view._scratch_signals.append(new_scratch_signal_1)  # type: ignore[arg-type]

    new_scratch_signal_2 = zone.scratchpad[6].as_scratch_signal()
    zone.active_view._scratch_signals.append(new_scratch_signal_2)  # type: ignore[arg-type]

    # We expect that only the bits reserved by the scratch signal are marked as true

    expected = [False] * 8
    expected[2] = True
    expected[3] = True
    expected[6] = True

    assert zone.scratch_map == expected

    new_scratch_signal_2.release()

    expected[6] = False

    assert zone.scratch_map == expected


def test_memory_map_3() -> None:
    """Test that the Scratch manager class can be initialized correctly."""
    engine = CoreEngine('my_engine')

    zone = engine.scratch_manager.active_zone
    zone.width = 8

    new_scratch_signal_1 = zone.scratchpad[3:2].as_scratch_signal()
    zone.active_view._scratch_signals.append(new_scratch_signal_1)  # type: ignore[arg-type]

    new_scratch_signal_2 = zone.scratchpad[6].as_scratch_signal()
    zone.active_view._scratch_signals.append(new_scratch_signal_2)  # type: ignore[arg-type]

    # We expect that only the bits reserved by the scratch signal are marked as true

    expected = [False] * 8
    expected[2] = True
    expected[3] = True
    expected[6] = True

    assert zone.scratch_map == expected

    new_scratch_signal_2.release()

    expected[6] = False

    assert zone.scratch_map == expected


def test_alloc() -> None:
    """Test that the alloc method finds the first valid place for a new variable."""
    engine = CoreEngine('my_engine')

    zone = engine.scratch_manager.active_zone

    zone.width = 16

    new_scratch_signal = zone.scratchpad[2:3].as_scratch_signal()
    zone.active_view._scratch_signals.append(new_scratch_signal)  # type: ignore[arg-type]

    new_scratch_signal = zone.scratchpad[6].as_scratch_signal()
    zone.active_view._scratch_signals.append(new_scratch_signal)  # type: ignore[arg-type]

    assert engine.scratch_manager.active_zone.alloc(1) == 0

    assert engine.scratch_manager.active_zone.alloc(8) == 7

    new_scratch_signal = zone.scratchpad[0].as_scratch_signal()
    zone.active_view._scratch_signals.append(new_scratch_signal)  # type: ignore[arg-type]

    assert engine.scratch_manager.active_zone.alloc(1) == 1


def test_write_after_release() -> None:
    engine = CoreEngine('my_engine')
    test = engine.scratch_manager.create_signal(4)

    engine.sync()

    engine.set(test, 1)
    test.release()

    with pytest.raises(Exception):
        engine.set(test, 1)


def test_read_after_release() -> None:
    engine = CoreEngine('my_engine')
    out = engine.define_output('out', 4)
    test = engine.scratch_manager.create_signal(4)

    engine.sync()

    engine.set(test, 1)
    test.release()

    with pytest.raises(Exception):
        engine.set(out, test)


def test_create_and_release_in_context() -> None:
    engine = CoreEngine('my_engine')
    out = engine.define_output('out', 4, 0)

    with Condition(engine, out == 0):
        test = engine.scratch_manager.create_signal(4)
        engine.set(test, 1)
        test.release()

    with pytest.raises(Exception):
        engine.set(out, test)


def test_auto_release_leaving_context() -> None:
    engine = CoreEngine('my_engine')
    out = engine.define_output('out', 4, 0)

    with Condition(engine, out == 0):
        test = engine.scratch_manager.create_signal(4)
        engine.set(test, 1)

    assert test.released


def test_scratch_as_context() -> None:
    engine = CoreEngine('my_engine')

    engine.sync()

    with engine.scratch_manager.create_signal(4) as test:
        pass

    assert test.released


def test_release_in_forked_process() -> None:
    engine = CoreEngine('my_engine')

    engine.sync()

    with Fork(engine, 'f1') as f1:
        test = engine.scratch_manager.create_signal(4)
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
        test1 = engine.scratch_manager.create_signal(4)

    with Fork(engine, 'f2') as f2:
        test2 = engine.scratch_manager.create_signal(4)

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
        test1 = engine.scratch_manager.create_signal(4)
        engine.set(test1, 1)

    with Fork(engine, 'f2') as f2:
        test2 = engine.scratch_manager.create_signal(4)
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


def test_memory_zone() -> None:
    """Test creating a memory zone and allocating signals in it."""
    engine = CoreEngine('my_engine')

    local_signal = engine.define_local('local_signal', 1)
    engine.sync()

    # Create a scratch signal, it will be located in the main zone
    outside_signal = engine.scratch_manager.create_signal(1)
    assert outside_signal.zone == engine.scratch_manager.main_zone

    # The signal can be used as usual
    engine.set(local_signal, outside_signal)
    engine.sync()

    # Create a memory zone
    zone = engine.scratch_manager.create_zone()
    with zone:
        inner_signal = engine.define_scratch(1)
        assert inner_signal.zone is not engine.scratch_manager.main_zone
        assert inner_signal.zone is zone  #  The context manager actually

        # The signal inside the zone can also be used as usual
        engine.set(local_signal, inner_signal)
        engine.sync()

        # The outer signal can still be accessed (the zone is suspended)
        engine.set(local_signal, outside_signal)
        engine.sync()

    # However, after the zone is left, the signals defined within are no longer accessible
    with pytest.raises(AccessAfterReleaseError):
        engine.set(local_signal, inner_signal)


def test_scratch_signal_reclaim() -> None:
    """Tests that scratch signals can be reclaimed.

    This is danger zone!
    """
    engine = CoreEngine('my_engine')
    local_signal = engine.define_local('local_signal', 1)
    engine.sync()

    # Create a memory zone and a scratch signal
    zone = engine.scratch_manager.create_zone()
    with zone as view:  # Save reference to view, normally this is not needed
        inner_signal = engine.define_scratch(1)

    # There can be situations, where signals in a memory zone need to be "revisited",
    # e.g. when copying signals out of a segment. To allow this without disabling access checks, the signal can be reclaimed.

    # Recover the correct view from where inner_signal originates.
    with zone.recover(view):
        # Now, the scratch signal can be reclaimed,
        inner_signal.reclaim()

        engine.set(local_signal, inner_signal)
        engine.sync()

        # Multiple reclaims indicate systematic issues and are not allowed
        with pytest.raises(RuntimeError):
            inner_signal.reclaim()

    # When entering the zone normally, a new view is created. This signal is not accessible.
    with zone:
        # The signal cannot be reclaimed, because it is in the wrong view
        with pytest.raises(RuntimeError):
            inner_signal.reclaim()
