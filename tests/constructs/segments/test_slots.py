"""Tests correct handling of input and output slots, as well as signal-expiration."""

import re
from typing import Iterable, Iterator, Protocol

import pytest

from nortl import Engine, Segment
from nortl.core.protocols import ScratchSignalProto, SignalProto


class TestExecutor(Protocol):
    def __call__(self, engine: Engine, clock_gating: bool = False) -> str: ...


def sync_between[T](engine: Engine, it: Iterable[T]) -> Iterator[T]:
    it = iter(it)
    yield next(it)
    while (elem := next(it, None)) is not None:
        engine.sync()
        yield elem


@Segment.with_input_slots(value=8).with_output_slots(8)
def incr(engine: Engine, value: SignalProto) -> ScratchSignalProto:
    engine.current_state.name = 'start_state'
    result = engine.define_scratch(8)
    engine.set(result, value)
    engine.sync()

    engine.set(result, result + 1)
    engine.current_state.name = 'end_state'
    return result


def test_copy(execute_test: TestExecutor) -> None:
    """Test copying values in and out of the segment."""
    engine = Engine('my_engine')
    _ = engine.define_input('IN')
    output = engine.define_output('OUT', 8, reset_value=0)
    engine.sync()

    for i in range(4):
        engine.current_state.name = f'call_state{i}'
        output_plus_one = incr(engine, output)
        engine.current_state.name = f'return_state{i}'
        engine.set(output, output_plus_one)

        # This sync() plays an important role: it copies output_plus_one to output, before calling the segment again
        # Currently, the segment doesn't insert a safety sync() itself
        # FIXME remove once segments have a safety sync() or intelligent copy
        engine.sync()

        # Each call takes 3 states (call, copy-out, return)
        # The first call takes two more states
        assert len(engine.states['main']) == 7 + 3 * i

    # Execute test
    result = execute_test(engine)
    print(result)
    res = re.findall(r'OUT=\s*\d+', result)
    res = [re.sub(r'\s*', '', r) for r in res]

    expected = [f'OUT={i}' for i in range(5)]

    assert res == expected


class MyEngine(Engine):
    def __init__(self, module_name: str, reset_state_name: str = 'IDLE') -> None:
        super().__init__(module_name, reset_state_name)

        # Define a result pointer as a fixed resource for the segment
        # Note that this signal must not be accessed directly outside of the segment, or else the reference-invalidation
        # feature will not apply.
        self.result_pointer = self.define_local('result_pointer', 8, reset_value=0)

    # This function always returns the same signal
    @Segment.with_input_slots(value=8)
    def incr_with_ptr(self, value: SignalProto) -> SignalProto:
        self.current_state.name = 'start_state'
        self.set(self.result_pointer, value)
        self.sync()

        self.set(self.result_pointer, self.result_pointer + 1)
        self.current_state.name = 'end_state'

        return self.result_pointer


def test_signal_reference(execute_test: TestExecutor) -> None:
    """Test Weak Reference invalidation of returned signals.

    When a segment returns a regular signal, and doesn't have an (unnecessary) output slot for it, the signal is wrapped in a WeakReference modifier.
    This reference is invalidated/expired when the segment is called again, because then the underlying signal will already contain the next result.

    Warning: this safety feature can be bypassed, if the signal is not explicitely returned from the segment.
    """
    engine = MyEngine('my_engine')
    _ = engine.define_input('IN')
    output = engine.define_output('OUT', 8, reset_value=0)
    engine.sync()

    previous_output_plus_one: SignalProto = None  # type: ignore
    for i in range(4):
        engine.current_state.name = f'call_state{i}'

        output_plus_one = engine.incr_with_ptr(output)
        engine.current_state.name = f'return_state{i}'
        engine.set(output, output_plus_one)
        engine.sync()

        # output_plus_one will contain a WeakReference modifier of the signal
        # It gets invalidated once the segment is called again
        if i > 0:
            with pytest.raises(RuntimeError):
                engine.set(output, previous_output_plus_one)

        previous_output_plus_one = output_plus_one

        # Each call now takes 2 states (call, return), because no copy-out state is needed
        # The first call takes two more states
        assert len(engine.states['main']) == 6 + 2 * i

    # Execute test
    result = execute_test(engine)
    print(result)
    res = re.findall(r'OUT=\s*\d+', result)
    res = [re.sub(r'\s*', '', r) for r in res]

    expected = [f'OUT={i}' for i in range(5)]

    assert res == expected
