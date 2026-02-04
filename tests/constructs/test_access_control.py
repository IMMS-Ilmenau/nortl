import pytest

from nortl import Engine
from nortl.core.constructs import Fork
from nortl.core.exceptions import ExclusiveReadError, ExclusiveWriteError, NonIdenticalRWError
from nortl.core.modifiers import Volatile


def test_same_read_same_write() -> None:
    """Tests, if the output values can actually be probed."""
    engine = Engine('my_engine')
    _ = engine.define_input('IN')
    output = engine.define_output('OUT', 8)
    engine.set(output, 0)
    engine.sync()
    local_cnt = engine.define_local('local_counter', 8, reset_value=0)

    with Fork(engine, 'Timeouttimer') as proc:
        engine.set(local_cnt, 1)
        engine.sync()
        engine.set(local_cnt, local_cnt + 5)

        proc.finish()

    assert 'WORKER_1.Timeouttimer' in local_cnt.access_checker.reading_thread_names
    assert 'WORKER_1.Timeouttimer' in local_cnt.access_checker.writing_thread_names


def test_nonexcl_read() -> None:
    engine = Engine('my_engine')
    _ = engine.define_input('IN')
    output = engine.define_output('OUT', 8)
    engine.set(output, 0)
    engine.sync()
    local_cnt = engine.define_local('local_counter', 8, reset_value=0)
    local_cnt2 = engine.define_local('local_counter2', 8, reset_value=0)

    with Fork(engine, 'Proc1') as proc1:
        engine.set(local_cnt2, local_cnt + 5)

        proc1.finish()

    with Fork(engine, 'Proc2') as proc2:
        with pytest.raises(ExclusiveReadError):
            engine.set(output, local_cnt + 2)

    del proc2


def test_nonexcl_write() -> None:
    engine = Engine('my_engine')
    _ = engine.define_input('IN')
    output = engine.define_output('OUT', 8)
    engine.set(output, 0)
    engine.sync()
    local_cnt = engine.define_local('local_counter', 8, reset_value=0)

    with Fork(engine, 'Proc1') as proc1:
        engine.set(local_cnt, 1)
        engine.sync()
        engine.set(local_cnt, local_cnt + 5)

        proc1.finish()

    with Fork(engine, 'Proc2') as proc2:
        with pytest.raises(ExclusiveWriteError):
            engine.set(local_cnt, 2)

    del proc2


def test_nonid_read_write() -> None:
    engine = Engine('my_engine')
    _ = engine.define_input('IN')
    output = engine.define_output('OUT', 8, reset_value=0)
    engine.sync()
    local_cnt = engine.define_local('local_counter', 8, reset_value=0)

    with Fork(engine, 'Proc1') as proc1:
        engine.set(local_cnt, 1)
        engine.sync()
        engine.set(local_cnt, 5)

        proc1.finish()

    with Fork(engine, 'Proc2') as proc2:
        with pytest.raises(NonIdenticalRWError):
            engine.set(output, local_cnt)

    del proc2


def test_indirection_via_combination_assignment() -> None:
    """Test that indirection through combinational assignments is caught.

    In the example, a signal is accessed from different threads, with one using a "indirection" through a combinational assignment.
    The access checker must not let this pass.
    """
    engine = Engine('my_engine')
    word = engine.define_input('word', width=16)
    lsb = engine.define_local('lsb', width=8, value=word[7:0])
    msb = engine.define_local('msb', width=8, value=word[15:8])

    lsb_out = engine.define_output('lsb_out', lsb.width, reset_value=0)
    msb_out = engine.define_output('msb_out', msb.width, reset_value=0)
    msb_out2 = engine.define_output('msb_out2', msb.width, reset_value=0)

    engine.sync()

    with Fork(engine, 'Proc1') as proc1:
        engine.set(lsb_out, lsb)
        engine.sync()
        proc1.finish()

    # Proc2 accesses word, after Proc1 already has
    with Fork(engine, 'Proc2'):
        with pytest.raises(ExclusiveReadError):
            engine.set(msb_out, msb)

    # Using a Volatile modifier allows the access
    with Fork(engine, 'Proc3') as proc3:
        engine.set(msb_out2, Volatile(msb))
        engine.sync()
        proc3.finish()


def test_free_after_join() -> None:
    """A signal accessed by a thread should be accessible without violaton after the thread has joined."""

    engine = Engine('my_engine')
    _ = engine.define_input('IN')
    engine.sync()
    local_cnt = engine.define_local('local_counter', 8, reset_value=0)

    with Fork(engine, 'Proc1') as proc1:
        engine.set(local_cnt, 1)
        engine.sync()
        engine.set(local_cnt, 5)

        proc1.finish()

    engine.sync()

    proc1.join()

    engine.set(local_cnt, 1)


def test_handoff_to_thread() -> None:
    """A signal is written by the main thread before the fork and accessed inside of the fork."""

    engine = Engine('my_engine')
    _ = engine.define_input('IN')
    engine.sync()
    local_cnt = engine.define_local('local_counter', 8, reset_value=0)
    engine.set(local_cnt, 1)

    with Fork(engine, 'Proc1') as proc1:
        engine.set(local_cnt, 1)
        engine.sync()
        engine.set(local_cnt, 5)

        proc1.finish()


def test_pass_to_thread() -> None:
    """A signal is written by the main thread before the fork and read inside of the fork."""

    engine = Engine('my_engine')
    _ = engine.define_input('IN')
    engine.sync()
    local_cnt = engine.define_local('local_counter', 8, reset_value=0)
    engine.set(local_cnt, 1)
    dummy_before = engine.define_local('test', 2, 0)
    engine.set(dummy_before, local_cnt)

    with Fork(engine, 'proc2') as proc2:
        with Fork(engine, 'Proc1') as proc1:
            dummy = engine.define_scratch(2)
            engine.set(dummy, local_cnt)
            engine.sync()
            engine.set(local_cnt, 2)

        proc1.cancel()
        engine.set(local_cnt, 2)
        engine.set(dummy_before, local_cnt)

    proc2.cancel()
    dummy = engine.define_scratch(2)
    engine.set(dummy, local_cnt)


def test_pass_scratch_reg_to_thread() -> None:
    """A signal is written by the main thread before the fork and read inside of the fork."""

    engine = Engine('my_engine')
    _ = engine.define_input('IN')
    engine.sync()
    local_cnt = engine.define_scratch(4)
    engine.set(local_cnt, 1)
    dummy_before = engine.define_local('test', 2, 0)
    engine.set(dummy_before, local_cnt)

    with Fork(engine, 'proc2') as proc2:
        with Fork(engine, 'Proc1') as proc1:
            dummy = engine.define_scratch(2)
            engine.set(dummy, local_cnt)
            engine.sync()
            engine.set(local_cnt, 2)

        proc1.cancel()
        engine.set(local_cnt, 2)
        engine.set(dummy_before, local_cnt)

    proc2.cancel()
    dummy = engine.define_scratch(2)
    engine.set(dummy, local_cnt)
