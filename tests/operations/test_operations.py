"""Test operation framework."""

import pytest

from nortl.core import Const, Signal
from nortl.core.engine import CoreEngine


def test_arithmethics(a: Signal, b: Signal) -> None:
    """Test all arithmetic operations."""
    # Addition
    assert (a + 1).render() == '(a + 1)'  # Note that all two-sided operations are wrapped in brackets
    assert (1 + a).render() == '(1 + a)'

    # Addition short circuits for addition of 0
    assert (a + 0).render() == 'a'
    assert (0 + a).render() == 'a'

    # Substraction
    assert (a - 1).render() == '(a - 1)'
    assert (1 - a).render() == '(1 - a)'

    # Substraction short circuits for substrction of 0
    assert (a - 0).render() == 'a'
    assert (0 - a).render() == '-a'

    # Multiplication
    assert (a * 2).render() == '(a * 2)'
    assert (2 * a).render() == '(2 * a)'

    # Multiplication short circuits for multiplication with 0 or 1
    assert (a * 0).render() == '0'
    assert (0 * a).render() == '0'
    assert (a * 1).render() == 'a'
    assert (1 * a).render() == 'a'

    # Division
    assert (a / 2).render() == '(a / 2)'
    assert (2 / a).render() == '(2 / a)'

    # Division short circuits for division by 0 or 1
    with pytest.raises(ZeroDivisionError):
        a / 0
    assert (0 / a).render() == '0'
    assert (a / 1).render() == 'a'

    # Modulo
    assert (a % 1).render() == r'(a % 1)'
    assert (1 % a).render() == r'(1 % a)'


def test_comparison(a: Signal) -> None:
    """Test all comparison operations.

    There are some details in how comparison behaves, if the left value is not already a Renderable.
    """

    # Equality
    assert (a == 1).render() == '(a == 1)'
    assert (Const(1) == a).render() == '(1 == a)'  # (Non-)Equality only works with Const or Signal on left hand side

    # Unequality
    assert (a != 1).render() == '(a != 1)'
    assert (Const(1) != a).render() == '(1 != a)'

    # Less
    assert (a < 1).render() == '(a < 1)'
    assert (1 < a).render() == '(a > 1)'  # Comparison with integer on left hand side gets reordered by Python
    assert (Const(1) < a).render() == '(1 < a)'  # With a Const, the order stays at is is

    # Less Or Equal
    assert (a <= 1).render() == '(a <= 1)'
    assert (1 <= a).render() == '(a >= 1)'
    assert (Const(1) <= a).render() == '(1 <= a)'

    # Greater
    assert (a > 1).render() == r'(a > 1)'
    assert (1 > a).render() == r'(a < 1)'
    assert (Const(1) > a).render() == '(1 > a)'

    # Greater Or Equal
    assert (a >= 1).render() == '(a >= 1)'
    assert (1 >= a).render() == '(a <= 1)'
    assert (Const(1) >= a).render() == '(1 >= a)'


def test_logic(a: Signal) -> None:
    """Test all logic operations."""
    # And
    assert (a & 1).render() == '(a & 1)'
    assert (1 & a).render() == '(1 & a)'

    # And short-circuits for x & 0
    assert (a & 0).render() == '0'
    assert (0 & a).render() == '0'

    # Or
    assert (a | 1).render() == '(a | 1)'
    assert (1 | a).render() == '(1 | a)'

    # Or short circuits for x | 0
    assert (a | 0).render() == 'a'
    assert (0 | a).render() == 'a'

    # ExclusiveOr
    assert (a ^ 1).render() == '(a ^ 1)'
    assert (1 ^ a).render() == '(1 ^ a)'

    # ExclusiveOr Short Circuits for x ^ 0
    assert (a ^ 0).render() == 'a'
    assert (0 ^ a).render() == 'a'

    # LeftShift
    assert (a << 1).render() == '(a << 1)'
    assert (1 << a).render() == '(1 << a)'

    # LeftShift short circuits for shift of/by 0
    assert (a << 0).render() == 'a'
    assert (0 << a).render() == '0'

    # RightShift
    assert (a >> 1).render() == r'(a >> 1)'
    assert (1 >> a).render() == r'(1 >> a)'

    # RightShift short circuits for shift of/by 0
    assert (a >> 0).render() == 'a'
    assert (0 >> a).render() == '0'


def test_misc(a: Signal) -> None:
    """Test all miscellaneous operations."""
    # Negative
    assert (-a).render() == '-a'
    assert (-Const(1)).render() == '-1'

    # Positive
    assert (+a).render() == 'a'
    assert (+Const(1)).render() == '1'

    # Inversion
    assert (~a).render() == '~(a)'
    assert (~Const(1)).render() == '~(1)'


def test_operation_slice() -> None:
    """Test slicing operations on OperationTraits (except signals)."""
    design_id = Const(0x0815A0, 24)

    # Slices on non-primitive objects must used a mask instead of indexes
    byte0 = design_id[7:0]
    assert byte0.render() == "(24'h0815A0 & 255)"
    assert byte0.operand_width == 8

    byte1 = design_id[15:8]
    assert byte1.render() == "((24'h0815A0 >> 8) & 255)"
    assert byte1.operand_width == 8

    bit = design_id[17]
    assert bit.render() == "((24'h0815A0 >> 17) & 1)"
    assert bit.operand_width == 1


def test_signal_slice(byte: Signal) -> None:
    """Test signal slicing operation."""

    # Single index
    assert byte[0].render() == 'byte[0]'
    assert byte[1].render() == 'byte[1]'

    # Slices are rendered "as-is" - note that this effectively flips the bit order compared to what you would expect.
    assert byte[7:0].render() == 'byte[7:0]'
    assert byte[0:7].render() == 'byte[0:7]'

    # Slices can be used in expressions, like any normal signal would
    assert (2 * byte[7:0] + 1).render() == '((2 * byte[7:0]) + 1)'


def test_nested_signal_slice(engine: CoreEngine, byte: Signal) -> None:
    """Test nested signal slicing operation."""
    # Slices can be nested for convenience, this will slice the base signal (2D signals don't exist)
    assert byte[7:0][0].render() == 'byte[0]'
    assert byte[7:1][2].render() == 'byte[3]'
    assert byte[7:0][7].render() == 'byte[7]'

    # Slices can be nested even more often, it just gets confusing
    assert byte[7:0][6:1][4:1].render() == 'byte[5:2]'
    assert byte[7:0][6:1][4:1][2].render() == 'byte[4]'

    # Nested slices must not go out of range
    with pytest.raises(IndexError):
        byte[7:0][8]
    with pytest.raises(IndexError):
        byte[7:0][-1]

    with pytest.raises(IndexError):
        byte[7:0][8:0]
    with pytest.raises(IndexError):
        byte[7:0][10:9]

    # Nested slices must not revert the bit order of a previous slice
    with pytest.raises(IndexError):
        byte[7:0][0:7]

    # Nested slices even work for signals without fixed width
    WIDTH = engine.define_parameter('WIDTH')  # noqa: N806
    var = engine.define_local('var', WIDTH)
    var[1345:400][100:0]
    # The first slice is always assumed to work, but a nested slice will be validated
    with pytest.raises(IndexError):
        var[1345:0][6789:0]


def test_scratch_signal_slice(scratch_pad: Signal) -> None:
    """Test nested slicing of scratch signals."""
    # Resize scratch pad signal
    scratch_pad.width.update(16)  # type: ignore

    scratch_signal = scratch_pad[15:8].as_scratch_signal()

    scratch_signal[0].render() == 'scratch_signal[8]'
    scratch_signal[7:1].render() == 'scratch_signal[15:9]'
    scratch_signal[7:1][2].render() == 'scratch_signal[11]'


def test_signal_operations(a: Signal, b: Signal, c: Signal) -> None:
    """All operations also work on signals."""
    assert (a + b).render() == '(a + b)'

    # Operations can be chained
    # Wrapping all operations in brackets may be ugly, but ensures that the term order is correctly conveyed.
    # For equally-ranked operations, the expression is simply grouped from left-to-right
    assert (a + b + c).render() == '((a + b) + c)'

    # For non-equally-ranked operations, the implicit term order is used, or explicitely set
    assert (a + b * c).render() == '(a + (b * c))'
    assert ((a + b) * c).render() == '((a + b) * c)'

    # Single-value operations like inversions obviously need no wrapping
    assert (a + b * ~c).render() == '(a + (b * ~(c)))'
