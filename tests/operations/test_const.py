"""Test constants."""

import pytest

from nortl import Const


def test_int_const() -> None:
    """Test creating constants from integers."""
    # Integer constants will have no width unless specified
    var = Const(0xFF)
    assert var.value == 0xFF
    assert var.width is None
    assert var.render() == '255'

    var = Const(0, 3)
    assert var.value == 0
    assert var.width == 3
    assert var.render() == "3'h0"


def test_bool_const() -> None:
    """Test creating constants from boolean values."""
    # Boolean constants will have a width of 1 and 0 or 1 as value
    var = Const(True)
    assert var.value == 1
    assert var.width == 1
    assert var.render() == "1'h1"

    var = Const(False)
    assert var.value == 0
    assert var.width == 1
    assert var.render() == "1'h0"

    # If an explicit width is provided, the value is padded
    var = Const(True, 16)
    assert var.value == 1
    assert var.width == 16
    assert var.render() == "16'h0001"


def test_string_const() -> None:
    """Test creating constants from strings."""
    # Constants can be parsed from binary, octal or hexadecimal numbers
    var = Const('0b101')
    assert var.value == 5
    assert var.width == 3
    assert var.render() == "3'h5"

    # The width of hexadecimal numbers will be a multiplier of 4
    var = Const('0x301')
    assert var.value == 0x301
    assert var.width == 12
    assert var.render() == "12'h301"

    # Width can be explicitely set
    var = Const('0x301', 13)
    assert var.value == 0x301
    assert var.width == 13
    assert var.render() == "13'h0301"

    # Width must be large enough to fit the value
    with pytest.raises(ValueError):
        Const('0x301', 10)

    # The width of octal numbers will be a mulitplier of 3
    var = Const('0o1')
    assert var.value == 1
    assert var.width == 3
    assert var.render() == "3'h1"

    # Constants can also be parsed from decimal numbers
    var = Const('123')
    assert var.value == 123
    assert var.width is None
    assert var.render() == '123'

    # The width of decimal numbers must be set explicitely
    var = Const('123', 32)
    assert var.value == 0x7B
    assert var.width == 32
    assert var.render() == "32'h0000007B"

    # Trying to create a constant from a non-integer string will fail
    with pytest.raises(ValueError):
        Const('miau')
