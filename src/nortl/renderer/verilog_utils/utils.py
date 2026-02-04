from typing import Protocol, Union

from nortl.core.operations import RawText


class VerilogRenderable(Protocol):
    """Protocol for Verilog Renderable.

    Compared to the [nortl.core.Renderable][nortl.core.operations.Renderable], it doesn't require the [OperationTrait Mixin][nortl.core.operations.OperationTrait] and `target` argument for `render()`.
    """

    def render(self) -> str: ...


def to_verilog_renderable(value: Union[str, VerilogRenderable]) -> VerilogRenderable:
    """Convert value to Verilog Renderable.

    Compared to [nortl.core.to_renderable][nortl.core.operations.to_renderable], this also supports strings.
    """
    if isinstance(value, str):
        return RawText(value)
    else:
        return value
