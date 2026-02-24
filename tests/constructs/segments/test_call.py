"""Tests correct handling of input and output slots, as well as signal-expiration."""

import re
from pathlib import Path
from typing import Protocol, Union

from nortl import Engine, Segment
from nortl.core.protocols import EngineProto, ScratchSignalProto

ARTIFACTS_PATH = Path(__file__).parent / '..' / 'artifacts'


class TestExecutor(Protocol):
    __test__: bool = False

    def __call__(self, engine: Engine, clock_gating: bool = False) -> str: ...


@Segment.with_input_slots(sig=8).with_output_slots(8)
def a(engine: EngineProto, sig: Union[int, ScratchSignalProto]) -> ScratchSignalProto:
    res = engine.define_scratch(8)
    engine.set(res, sig + 1)
    return res


@Segment.with_input_slots(sig=8).with_output_slots(8)
def b(engine: EngineProto, sig: Union[int, ScratchSignalProto]) -> ScratchSignalProto:
    res = a(engine, sig)
    return res


@Segment.with_input_slots(sig=8).with_output_slots(8)
def c(engine: EngineProto, sig: Union[int, ScratchSignalProto]) -> ScratchSignalProto:
    res = a(engine, sig)
    return res


def test_call_return_address(execute_test: TestExecutor) -> None:
    """Test correct operation of the return address for segments."""
    engine = Engine('my_engine')
    _ = engine.define_input('IN')
    output = engine.define_output('OUT', 8, reset_value=0)
    count = engine.define_local('count', 2, reset_value=0)
    engine.sync()

    # Manually create a for-loop that causes the segment to break, if the return addresses don't work
    engine.set(count, count + 1)
    assert len(engine.states['main']) == 2  # (IDLE + STATE_1)

    start_state = engine.current_state
    x = a(engine, 0)
    engine.set(output, x)  # Should be 1  == STATE_3
    assert len(engine.states['main']) == 4  # + Call, Return for a()

    x = b(engine, 8)
    engine.set(output, x + 1)  # Should be 10
    assert len(engine.states['main']) == 7  # + Call, Return for b(); Call for a()

    x = a(engine, 0)
    engine.set(output, x + 2)  # Should be 3
    assert len(engine.states['main']) == 8  # + Call for a()

    x = c(engine, 4)
    engine.set(output, x + 3)  # Should be 8
    assert len(engine.states['main']) == 11  # + Call, Return for c(); Call for a() + b()

    # End for loop
    engine.jump_if(count < 2, start_state, engine.next_state)

    # Execute test
    result = execute_test(engine)
    print(result)
    res = re.findall(r'OUT=\s*\d+', result)
    res = [re.sub(r'\s*', '', r) for r in res]

    expected = ['OUT=0'] + ['OUT=1', 'OUT=10', 'OUT=3', 'OUT=8'] * 2

    assert res == expected
