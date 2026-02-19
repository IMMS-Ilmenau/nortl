"""Verilog utility classes for rendering Verilog code.

This module provides classes for constructing Verilog declarations, modules, and
other structural elements with proper formatting.

Example:
    >>> from nortl.renderer.verilog_utils import VerilogModule, VerilogPortDeclaration, VerilogDeclaration
    >>>
    >>> # Create a module with ports and signals
    >>> module = VerilogModule("counter")
    >>> module.ports.append(VerilogPortDeclaration("input", "clk"))
    >>> module.ports.append(VerilogPortDeclaration("input", "reset"))
    >>> module.ports.append(VerilogPortDeclaration("output", "count", 4))
    >>> module.signals.append(VerilogDeclaration("reg", "count", 4))
    >>>
    >>> print(module.render())
    module counter (
        input clk,
        input reset,
        output [3:0] count
    );
    reg [3:0] count;
    endmodule
"""

from typing import Literal, Union, overload

from nortl.core.protocols import WorkerProto

from .abstractions import MultiHotEncodedStateRegister, OneHotEncodedStateRegister, StateRegister
from .structural import VerilogDeclaration, VerilogModule

__all__ = [
    'MultiHotEncodedStateRegister',
    'OneHotEncodedStateRegister',
    'StateRegister',
    'VerilogDeclaration',
    'VerilogModule',
]

ENCODINGS = Literal['binary', 'one-hot', 'multi-hot']


@overload
def create_state_var(worker: WorkerProto, encoding: Literal['binary'] = 'binary') -> StateRegister: ...
@overload
def create_state_var(worker: WorkerProto, encoding: Literal['one-hot'] = 'one-hot') -> OneHotEncodedStateRegister: ...
@overload
def create_state_var(worker: WorkerProto, encoding: Literal['multi-hot'] = 'multi-hot') -> MultiHotEncodedStateRegister: ...
def create_state_var(
    worker: WorkerProto, encoding: ENCODINGS = 'binary'
) -> Union[StateRegister, OneHotEncodedStateRegister, MultiHotEncodedStateRegister]:
    """Create state register."""
    if encoding == 'binary':
        return StateRegister(worker)
    if encoding == 'one-hot':
        return OneHotEncodedStateRegister(worker)
    if encoding == 'multi-hot':
        return MultiHotEncodedStateRegister(worker)
    raise ValueError(f'Unknown encoding: {encoding}')
