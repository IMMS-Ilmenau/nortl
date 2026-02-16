"""Utility types and helpers for Verilog rendering.

This module provides the VerilogRenderable protocol and helper functions
for converting values to Verilog renderable objects.

Example:
    >>> from nortl.renderer.verilog_utils.utils import VerilogRenderable, to_verilog_renderable
    >>>
    >>> # String values are automatically converted
    >>> renderable = to_verilog_renderable("clk")
    >>> print(renderable.render())
    clk
    >>>
    >>> # VerilogRenderable objects are passed through
    >>> class MyRenderable(VerilogRenderable):
    ...     def render(self) -> str:
    ...         return "my_signal"
    >>>
    >>> renderable2 = to_verilog_renderable(MyRenderable())
    >>> print(renderable2.render())
    my_signal
"""

from typing import Protocol, Union

from nortl.core.operations import RawText


class VerilogRenderable(Protocol):
    """Protocol for Verilog Renderable.

    Compared to the [nortl.core.Renderable][nortl.core.operations.Renderable], it doesn't require the
    [OperationTrait Mixin][nortl.core.operations.OperationTrait] and `target` argument for `render()`.

    Example:
        >>> class SimpleSignal(VerilogRenderable):
        ...     def render(self) -> str:
        ...         return "simple_signal"
        >>>
        >>> signal = SimpleSignal()
        >>> print(signal.render())
        simple_signal
    """

    def render(self) -> str: ...


def to_verilog_renderable(value: Union[str, VerilogRenderable]) -> VerilogRenderable:
    """Convert value to Verilog Renderable.

    Compared to [nortl.core.to_renderable][nortl.core.operations.to_renderable], this also supports strings.

    Args:
        value: The value to convert. Can be a string or a VerilogRenderable.

    Returns:
        A VerilogRenderable instance.

    Example:
        >>> # String input
        >>> renderable = to_verilog_renderable("clk")
        >>> print(renderable.render())
        clk
        >>>
        >>> # VerilogRenderable input
        >>> class MyRenderable(VerilogRenderable):
        ...     def render(self) -> str:
        ...         return "my_signal"
        >>>
        >>> result = to_verilog_renderable(MyRenderable())
        >>> print(result.render())
        my_signal
    """
    if isinstance(value, str):
        return RawText(value)
    else:
        return value
