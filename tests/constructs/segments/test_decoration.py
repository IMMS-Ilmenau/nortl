"""Tests correct functionality of the segment decorator."""

import re
from typing import Iterable, Iterator, Protocol

from nortl import Engine, Segment
from nortl.core.protocols import SignalProto


class TestExecutor(Protocol):
    def __call__(self, engine: Engine, clock_gating: bool = False) -> str: ...


def sync_between[T](engine: Engine, it: Iterable[T]) -> Iterator[T]:
    it = iter(it)
    yield next(it)
    while (elem := next(it, None)) is not None:
        engine.sync()
        yield elem


# Test different styles of decoration
# Segments can be added to functions, or methods on subclasses of an noRTL engine, or on methods on helper classes
@Segment
def count_to_four(engine: Engine, counter: SignalProto) -> None:
    for _ in sync_between(engine, range(4)):
        engine.set(counter, counter + 1)


def test_function_segment(execute_test: TestExecutor) -> None:
    """Test calling the segment function."""
    engine = Engine('my_engine')
    _ = engine.define_input('IN')
    output = engine.define_output('OUT', 8, reset_value=0)
    engine.sync()
    assert len(engine.states['main']) == 2

    # Call the segment (output will be at 4)
    # This will create 5 new states (4 within the segment, and one return state)
    count_to_four(engine, output)
    assert len(engine.states['main']) == 7

    # Call the segment again
    # This will only create 1 new state for the new, second return state!
    count_to_four(engine, output)
    assert len(engine.states['main']) == 8

    # Execute test
    result = execute_test(engine)
    print(result)
    res = re.findall(r'OUT=\s*\d+', result)
    res = [re.sub(r'\s*', '', r) for r in res]

    expected = [f'OUT={i}' for i in range(9)]

    assert res == expected


class MyEngine(Engine):
    @Segment
    def count_to_four(self, counter: SignalProto) -> None:
        for _ in sync_between(self, range(4)):
            self.set(counter, counter + 1)


def test_method_segment(execute_test: TestExecutor) -> None:
    """Test adding a segment to a class method."""
    engine = MyEngine('my_engine')
    _ = engine.define_input('IN')
    output = engine.define_output('OUT', 8, reset_value=0)
    engine.sync()

    # Call the segment
    engine.count_to_four(output)
    assert len(engine.states['main']) == 7

    # Call the segment again
    engine.count_to_four(output)
    assert len(engine.states['main']) == 8

    # Execute test
    result = execute_test(engine)
    print(result)
    res = re.findall(r'OUT=\s*\d+', result)
    res = [re.sub(r'\s*', '', r) for r in res]

    expected = [f'OUT={i}' for i in range(9)]

    assert res == expected


class MyHelper:
    def __init__(self, engine: Engine):
        self.engine = engine  # the engine must always be stored in a attribute engine, for the segment to work

    @Segment
    def count_to_four(self, counter: SignalProto) -> None:
        for _ in sync_between(self.engine, range(4)):
            self.engine.set(counter, counter + 1)


def test_helper_method_segment(execute_test: TestExecutor) -> None:
    """Test adding a segment to a helper class method."""
    engine = MyEngine('my_engine')
    _ = engine.define_input('IN')
    output = engine.define_output('OUT', 8, reset_value=0)
    engine.sync()

    helper = MyHelper(engine)

    # Call the segment
    helper.count_to_four(output)
    assert len(engine.states['main']) == 7

    # Call the segment again
    helper.count_to_four(output)
    assert len(engine.states['main']) == 8

    # Execute test
    result = execute_test(engine)
    print(result)
    res = re.findall(r'OUT=\s*\d+', result)
    res = [re.sub(r'\s*', '', r) for r in res]

    expected = [f'OUT={i}' for i in range(9)]

    assert res == expected


# Test inlining
def test_function_inline(execute_test: TestExecutor) -> None:
    """Test calling the segment function as an inline.

    Effectively, this treats the decorated function as if it wouldn't have the decorator.
    """
    engine = Engine('my_engine')
    _ = engine.define_input('IN')
    output = engine.define_output('OUT', 8, reset_value=0)
    engine.sync()

    # Call the segment as an inline
    # Inlining will save two states for the entry and exit.
    # However, an additional sync is still required here, that is merged into the exit state of the call by the sync_between.
    count_to_four.inline(engine, output)
    engine.sync()
    assert len(engine.states['main']) == 6

    # However, calling the segment again, will add 3 new states (because there are 3x sync() in the function)
    count_to_four.inline(engine, output)
    engine.sync()
    assert len(engine.states['main']) == 10

    # Execute test
    result = execute_test(engine)
    print(result)
    res = re.findall(r'OUT=\s*\d+', result)
    res = [re.sub(r'\s*', '', r) for r in res]

    expected = [f'OUT={i}' for i in range(9)]

    assert res == expected


def test_method_inline(execute_test: TestExecutor) -> None:
    """Test calling the segment method as an inline."""

    engine = MyEngine('my_engine')
    _ = engine.define_input('IN')
    output = engine.define_output('OUT', 8, reset_value=0)
    engine.sync()

    # Call the segment
    engine.count_to_four.inline(output)
    engine.sync()
    assert len(engine.states['main']) == 6

    # Call the segment again
    engine.count_to_four.inline(output)
    engine.sync()
    assert len(engine.states['main']) == 10

    # Execute test
    result = execute_test(engine)
    print(result)
    res = re.findall(r'OUT=\s*\d+', result)
    res = [re.sub(r'\s*', '', r) for r in res]

    expected = [f'OUT={i}' for i in range(9)]

    assert res == expected


def test_helper_method_inline(execute_test: TestExecutor) -> None:
    """Test calling the segment method as an inline."""

    engine = Engine('my_engine')
    _ = engine.define_input('IN')
    output = engine.define_output('OUT', 8, reset_value=0)
    engine.sync()

    helper = MyHelper(engine)

    # Call the segment
    helper.count_to_four.inline(output)
    engine.sync()
    assert len(engine.states['main']) == 6

    # Call the segment again
    helper.count_to_four.inline(output)
    engine.sync()
    assert len(engine.states['main']) == 10

    # Execute test
    result = execute_test(engine)
    print(result)
    res = re.findall(r'OUT=\s*\d+', result)
    res = [re.sub(r'\s*', '', r) for r in res]

    expected = [f'OUT={i}' for i in range(9)]

    assert res == expected
