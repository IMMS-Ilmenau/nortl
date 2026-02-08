"""Test logical operations."""

import pytest

from nortl import All, Any
from nortl.core.engine import CoreEngine
from nortl.core.operations import BaseOperation
from nortl.core.signal import Signal


def test_any_all(a: Signal, b: Signal, c: Signal) -> None:
    """Test Any and All operations on 1 bit wide signals."""
    val: BaseOperation = Any(a, b, c)
    assert val.operand_width == 1
    assert val.render() == '(a || b || c)'

    val = All(a, b, c)
    assert val.operand_width == 1
    assert val.render() == '(a && b && c)'


def test_any_all_single(a: Signal) -> None:
    """Test Any/All of a single element."""

    val: BaseOperation = Any(a)
    assert val.operand_width == 1
    assert not val.is_constant
    assert val.render() == 'a'

    val = All(a)
    assert val.operand_width == 1
    assert not val.is_constant
    assert val.render() == 'a'

    val = Any('0b1')
    assert val.operand_width == 1
    assert val.is_constant
    assert val.render() == "1'h1"

    val = All('0b1')
    assert val.operand_width == 1
    assert val.is_constant
    assert val.render() == "1'h1"


def test_multibit(byte: Signal, engine: CoreEngine) -> None:
    """Test Any/All operations with multi-bit signals."""

    # Trying to use multi-bit wide signals is not allowed
    with pytest.raises(ValueError):
        Any(byte)

    # Comparison operations will result in a 1 bit wide signal
    val = Any(byte == 0, byte > 3)
    assert val.render() == '((byte == 0) || (byte > 3))'

    # Signals with parametric width are not allowed either
    WIDTH = engine.define_parameter('WIDTH', default_value=1)  # noqa: N806
    signal = engine.define_local('signal', width=WIDTH)
    with pytest.raises(ValueError):
        Any(signal)

    val = Any(signal > 8, signal == 0)
    assert val.render() == '((signal > 8) || (signal == 0))'


def test_generator_expression(engine: CoreEngine) -> None:
    """Any/All operations can be directly created from a generator expression."""
    signals = [engine.define_scratch(8) for _ in range(3)]

    val = All(signal > 0 for signal in signals)
    assert val.render() == '((SCRATCH_SIGNAL[7:0] > 0) && (SCRATCH_SIGNAL[15:8] > 0) && (SCRATCH_SIGNAL[23:16] > 0))'

    # If a generator expression is used as the first argument, no further arguments are allowed
    with pytest.raises(ValueError):
        val = All((signal > 0 for signal in signals), signals[0] > 0)  # type: ignore

    # If the signals have 1 bit width, they can be directly unpacked
    bits = [engine.define_scratch(1) for _ in range(3)]
    val = All(*bits)
    assert val.operand_width == 1
    assert val.render() == '(SCRATCH_SIGNAL[24] && SCRATCH_SIGNAL[25] && SCRATCH_SIGNAL[26])'

    # This works too
    val = All(*bits, bits[0])
    assert val.operand_width == 1
    assert val.render() == '(SCRATCH_SIGNAL[24] && SCRATCH_SIGNAL[25] && SCRATCH_SIGNAL[26] && SCRATCH_SIGNAL[24])'
