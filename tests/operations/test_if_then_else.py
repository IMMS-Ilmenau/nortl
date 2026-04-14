"""Test If-Then-Else operator."""

import pytest

from nortl import Const, IfThenElse
from nortl.core.signal import Signal


def test_if_then_else_condition_width(a: Signal, b: Signal, byte: Signal) -> None:
    """Test condition width inference for ternary operator."""

    # The condition must have a fixed width of 1
    with pytest.raises(ValueError):
        # a + 1 looses fixed width due to the arithmetic operation
        IfThenElse(a + 1, a, b)

    with pytest.raises(ValueError):
        IfThenElse(byte, a, b)

    # As a workaround, signals with undefined operand width can be used in a comparison
    val = IfThenElse((a + 1) > 0, a, b)
    assert val.operand_width == 1
    assert val.render() == '(((a + 1) > 0) ? a : b)'


def test_if_then_else_operand_width(a: Signal, byte: Signal) -> None:
    """Test operand width inference for ternary operator."""

    # If one value has a fixed width and the other doesn't, the fixed width is used
    val = IfThenElse(a, byte, 0)
    assert val.operand_width == 8
    assert val.render() == '(a ? byte : 0)'

    # If both have a fixed width, the larger is used
    val = IfThenElse(a, byte, Const('0xFFFF'))
    assert val.operand_width == 16
    assert val.render() == "(a ? byte : 16'hFFFF)"

    # If none has a fixed width, the operand width is None
    val = IfThenElse(a, 123, 456)
    assert val.operand_width is None
    assert val.render() == '(a ? 123 : 456)'
