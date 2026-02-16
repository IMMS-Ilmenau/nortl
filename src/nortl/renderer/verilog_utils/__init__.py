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

from .structural import VerilogDeclaration, VerilogModule

__all__ = [
    'VerilogDeclaration',
    'VerilogModule',
]
