"""Test concatenation."""

import pytest

from nortl import Concat, Const
from nortl.core.signal import Signal


def test_concat_signal(byte: Signal) -> None:
    """Test concatenating signals."""

    # A signal and constant(s) with fixed width can be concatenated.
    val = Concat(Const('0b0000'), byte, Const('0b0000'))
    assert val.operand_width == 16
    assert val.render() == "{4'h0, byte, 4'h0}"

    # Trying to concatenate constants without fixed width will raise a ValueError
    with pytest.raises(ValueError):
        Concat(Const(0), byte, Const('0b0000'))

    # Signals without fixed width cannot be concatenated
    param = byte.engine.define_parameter('param')
    dyn_signal = byte.engine.define_local('dyn_signal', param)
    with pytest.raises(ValueError):
        Concat(Const('0b1010'), dyn_signal)

    # A workaround is to explicitely slice the signal
    val = Concat(Const('0b1010'), dyn_signal[7:0])
    assert val.operand_width == 12
    assert val.render() == "{4'hA, dyn_signal[7:0]}"


def test_concat_string_literal(byte: Signal) -> None:
    """Test using string literals."""

    # To make it easier to write constants with fixed length, the Concat also supports the same string literals, as the Const() class does.
    val = Concat('0b0000', byte, '0xCAFE', '0o7653')
    assert val.operand_width == 4 + 8 + 16 + 12
    assert val.render() == "{4'h0, byte, 16'hCAFE, 12'hFAB}"

    # String literals in decimal form will be parsed without a fixed width and will therefore raise a ValueError
    with pytest.raises(ValueError):
        Concat('120', byte)


def test_concat_parameter(byte: Signal) -> None:
    """Test concatenating constants and parameter."""
    DESIGN_ID0 = byte.engine.define_parameter('DESIGN_ID0', width=8)  # noqa: N806

    # Parameters with fixed width can be concatenated
    design_id = Concat('0x0815', DESIGN_ID0)
    assert design_id.operand_width == 24
    assert design_id.render() == "{16'h0815, DESIGN_ID0}"

    # Parameters without fixed widtth don't work
    N_COUNTERS = byte.engine.define_parameter('N_COUNTERS')  # noqa: N806
    with pytest.raises(ValueError):
        Concat(N_COUNTERS)
