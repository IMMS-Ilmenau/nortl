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

from typing import Literal

from nortl.core.protocols import WorkerProto

from .abstractions import MultiHotEncodedStateRegister, OneHotEncodedStateRegister, StateRegister, StateRegisterBase
from .structural import VerilogDeclaration, VerilogModule

__all__ = [
    'MultiHotEncodedStateRegister',
    'OneHotEncodedStateRegister',
    'StateRegister',
    'VerilogDeclaration',
    'VerilogModule',
]

ENCODINGS = Literal['binary', 'one-hot', 'multi-hot']


def create_state_var(worker: WorkerProto, encoding: ENCODINGS = 'binary') -> StateRegisterBase:
    if encoding == 'binary':
        return StateRegister(worker)
    if encoding == 'one-hot':
        return OneHotEncodedStateRegister(worker)
    if encoding == 'multi-hot':
        return MultiHotEncodedStateRegister(worker)
    raise ValueError(f'Unknown encoding: {encoding}')
