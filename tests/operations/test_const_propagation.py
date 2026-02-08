"""Test calculating with constants."""

from nortl import All, Any, Const, IfThenElse
from nortl.core.operations import BaseOperation
from nortl.core.signal import Signal


def test_int_const() -> None:
    """Test creating constants from integers."""
    # Integer constants will have no width unless specified
    a = Const(0x3)
    b = Const(0x6)

    c = Const(0x9)

    assert (a + b).render() == c.render()

    assert c.value == 9


def test_arithmethics() -> None:
    """Test all arithmetic operations."""

    a = Const(5)

    # Addition
    assert (a + 1).render() == '6'
    assert (1 + a).render() == '6'

    # Substraction
    assert (a - 1).render() == '4'
    assert (1 - a).render() == '-4'

    # Multiplication
    assert (a * 2).render() == '10'
    assert (2 * a).render() == '10'

    # Division
    assert (a / 1).render() == '5'
    assert (1 / a).render() == '0'

    # Modulo
    assert (a % 1).render() == '0'
    assert (1 % a).render() == '1'


def test_logic() -> None:
    """Test all logic operations."""

    a = Const(0x0F)
    # And
    assert (a & 1).render() == '1'
    assert (1 & a).render() == '1'

    # Or
    assert (a | 0x10).render() == '31'
    assert (0x10 | a).render() == '31'

    # ExclusiveOr
    assert (a ^ 1).render() == '14'
    assert (1 ^ a).render() == '14'

    # LeftShift
    assert (a << 1).render() == str(0xF << 1)
    assert (1 << a).render() == str(1 << 0xF)

    # RightShift
    assert (a >> 1).render() == str(0xF >> 1)
    assert (1 >> a).render() == str(1 >> 0xF)


def test_comparison() -> None:
    """Test all comparison operations.

    There are some details in how comparison behaves, if the left value is not already a Renderable.
    """

    a = Const(1)
    b = Const(0, 1)

    # Equality
    assert (a == 1).render() == "1'h1"
    assert (Const(1) == a).render() == "1'h1"  # (Non-)Equality only works with Const or Signal on left hand side
    assert (b == 0).render() == "1'h1"

    # Unequality
    assert (a != 1).render() == "1'h0"
    assert (Const(1) != a).render() == "1'h0"

    # Less
    assert (a < 1).render() == "1'h0"
    assert (1 < a).render() == "1'h0"  # Comparison with integer on left hand side gets reordered by Python
    assert (Const(1) < a).render() == "1'h0"  # With a Const, the order stays at is is

    # Less Or Equal
    assert (a <= 1).render() == "1'h1"
    assert (1 <= a).render() == "1'h1"
    assert (Const(1) <= a).render() == "1'h1"

    # Greater
    assert (a > 1).render() == "1'h0"
    assert (1 > a).render() == "1'h0"
    assert (Const(1) > a).render() == "1'h0"

    # Greater Or Equal
    assert (a >= 1).render() == "1'h1"
    assert (1 >= a).render() == "1'h1"
    assert (Const(1) >= a).render() == "1'h1"


def test_misc() -> None:
    """Test all miscellaneous operations."""
    a = Const(0x1, 4)

    # Negative
    assert (-a).render() == "4'hF"

    # Positive
    assert (+a).render() == "4'h1"

    # Inversion
    assert (~a).render() == "4'hE"


def test_any_all(a: Signal, b: Signal, c: Signal) -> None:
    """Test Any and All operations on 1 bit wide signals."""

    c0 = Const(0, width=1)
    c1 = Const(1, width=1)

    val: BaseOperation = Any(a, b, c0)
    assert val.operand_width == 1
    assert not val.is_constant
    assert val.render() == "(a || b || 1'h0)"

    val = Any(a, b, c1)
    assert val.operand_width == 1
    assert val.is_constant
    assert val.render() == "1'h1"

    val = Any(c0, c0, c0)
    assert val.operand_width == 1
    assert val.is_constant
    assert val.render() == "1'h0"

    val = Any(c1, c1, c1)
    assert val.operand_width == 1
    assert val.is_constant
    assert val.render() == "1'h1"

    val = All(a, b, c1)
    assert val.operand_width == 1
    assert not val.is_constant
    assert val.render() == "(a && b && 1'h1)"

    val = All(a, b, c0)
    assert val.operand_width == 1
    assert val.is_constant
    assert val.render() == "1'h0"

    val = All(c0, c0, c0)
    assert val.operand_width == 1
    assert val.is_constant
    assert val.render() == "1'h0"

    val = All(c1, c0, c1)
    assert val.operand_width == 1
    assert val.is_constant
    assert val.render() == "1'h0"

    val = All(c1, c1, c1)
    assert val.operand_width == 1
    assert val.is_constant
    assert val.render() == "1'h1"


def test_if_then_else(a: Signal, b: Signal) -> None:
    c0 = Const(0, width=1)
    c1 = Const(1, width=4)
    c2 = Const(2, width=4)

    val = IfThenElse(c0 == 0, c1, c2)
    assert val.is_constant
    assert val.render() == "4'h1"

    val = IfThenElse(c0 == 1, c1, c2)
    assert val.is_constant
    assert val.render() == "4'h2"

    val = IfThenElse(c0 == 0, a, b)
    assert not val.is_constant
    assert val.render() == 'a'

    val = IfThenElse(c0 == 1, a, b)
    assert not val.is_constant
    assert val.render() == 'b'
