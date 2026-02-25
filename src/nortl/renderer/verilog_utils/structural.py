"""Verilog structural elements: ports, declarations, and modules.

This module provides classes for constructing Verilog module declarations,
port declarations, signal declarations, and complete modules.

Example:
    >>> from nortl.renderer.verilog_utils import (
    ...     VerilogModule, VerilogPortDeclaration, VerilogDeclaration
    ... )
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

from typing import Dict, List, Optional, Union

from .formatter import VerilogFormatter
from .utils import VerilogRenderable


class VerilogPortDeclaration:
    """Represents a Verilog port declaration.

    Args:
        verilog_type: The port type (e.g., 'input', 'output', 'inout').
        name: The port name or list of port names.
        width: The port width (int for fixed width, str or VerilogRenderable for expression).

    Example:
        >>> port = VerilogPortDeclaration("input", "clk")
        >>> print(port.render())
        input clk
        >>>
        >>> # Port with width
        >>> port_w = VerilogPortDeclaration("output", "data", 8)
        >>> print(port_w.render())
        output [7:0] data
        >>>
        >>> # Multiple ports
        >>> ports = VerilogPortDeclaration("input", ["clk", "reset"])
        >>> print(ports.render())
        input clk, reset
    """

    def __init__(self, verilog_type: str, name: Union[str, List[str]], width: Union[int, str, VerilogRenderable] = 0) -> None:
        """Initialize the port declaration.

        Args:
            verilog_type: The port type.
            name: The port name or list of port names.
            width: The port width.
        """
        self.verilog_type = verilog_type
        self.name = name
        self.width = width

    def render(self) -> str:
        """Render the port declaration.

        Returns:
            The Verilog port declaration string.
        """
        parts: List[str] = []
        parts.append(self.verilog_type)

        if isinstance(self.width, int):
            if self.width > 1:
                parts.append(f'[{self.width - 1}:0]')
        else:
            parts.append(f'[{self.width}-1:0]')

        if isinstance(self.name, list):
            parts.append(', '.join(self.name))
        else:
            parts.append(self.name)
        return ' '.join(parts)


class VerilogDeclaration:
    """Represents a Verilog signal or variable declaration.

    Args:
        verilog_type: The Verilog type (e.g., 'reg', 'wire', 'logic').
        name: The signal name or list of signal names.
        width: The signal width.
        connections: Dictionary of named connections for module instances.
        params: Dictionary of parameters for parameterized declarations.
        members: For enums, either a list of member names or a dict of name->value mappings.

    Example:
        >>> # Simple signal declaration
        >>> signal = VerilogDeclaration("reg", "count", 4)
        >>> print(signal.render())
        reg [3:0] count
        >>>
        >>> # Signal with connections (module instance)
        >>> instance = VerilogDeclaration("counter", "u_counter", None, {
        ...     '.clk(clk)',
        ...     '.reset(reset)'
        ... })
        >>> print(instance.render())
        counter (.clk(clk), .reset(reset))
        >>>
        >>> # Enum declaration
        >>> state_enum = VerilogDeclaration("enum", "state", None, None, None, ["IDLE", "RUNNING", "DONE"])
        >>> print(state_enum.render())
        enum {IDLE, RUNNING, DONE} state
        >>>
        >>> # Enum with values
        >>> state_enum_val = VerilogDeclaration("enum", "state", None, None, None, {"IDLE": 0, "RUNNING": 1, "DONE": 2})
        >>> print(state_enum_val.render())
        enum {IDLE = 0, RUNNING = 1, DONE = 2} state
    """

    def __init__(
        self,
        verilog_type: str,
        name: Union[str, List[str]],
        width: Union[int, str, VerilogRenderable] = 0,
        connections: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, str]] = None,
        members: Optional[Union[List[str], Dict[str, int]]] = None,
    ) -> None:
        """Initialize the declaration.

        Args:
            verilog_type: The Verilog type.
            name: The signal name.
            width: The signal width.
            connections: Named connections for module instances.
            params: Parameters for parameterized declarations.
            members: Enum members.
        """
        self.verilog_type = verilog_type
        self.name = name
        self.connections = connections
        self.params = params
        self.members = members
        self.width = width

    def add_member(self, name: str, value: Optional[Union[int]] = None) -> None:
        """Add an enum member.

        Args:
            name: The member name.
            value: The member value (required for encoded enums).

        Raises:
            RuntimeError: If adding to an enum without proper configuration.
        """
        if self.members is None:
            if value is not None:
                self.members = {}
            else:
                self.members = []

        if isinstance(self.members, list):
            if value is not None:
                raise RuntimeError('Cannot add an encoded member to an enum without all items to be encoded!')
            self.members.append(name)
        else:
            if value is None:
                raise RuntimeError('Cannot add an un-encoded member to an enum where all items are encoded!')
            self.members[name] = value

    def add_parameter(self, name: str, value: Union[str, int]) -> None:
        """Add a parameter.

        Args:
            name: The parameter name.
            value: The parameter value.
        """
        if self.params is None:
            self.params = {}

        if isinstance(value, int):
            self.params[name] = str(value)
        else:
            self.params[name] = value

    def add_connection(self, src: str, tgt: str) -> None:
        """Add a named connection.

        Args:
            src: The source port name.
            tgt: The target signal name.
        """
        if self.connections is None:
            self.connections = {}

        self.connections[src] = tgt

    def render(self) -> str:  # noqa: C901
        """Render the declaration.

        Returns:
            The Verilog declaration string.
        """
        content: List[str] = []
        connection_lst = []
        param_lst = []

        if self.connections is not None:
            connection_lst = [f'.{x}({y})' for x, y in self.connections.items()]
        if self.params is not None:
            param_lst = [f'.{x}({y})' for x, y in self.params.items()]

        name_str = ''

        content.append(self.verilog_type)

        if isinstance(self.name, list):
            name_str = ', '.join(self.name)
        else:
            name_str = self.name

        if isinstance(self.width, int):
            if self.width > 1:
                content.append(f'[{self.width - 1}:0]')
        else:
            content.append(f'[{self.width}-1:0]')

        if self.verilog_type.startswith('enum'):
            if self.members is None:
                raise RuntimeError(f'Tried to create enum {name_str} without any values. Something is wrong here.')

            if isinstance(self.members, List):
                item_str = ', '.join(self.members)
            else:
                item_str = ', '.join([f'{item} = {value}' for item, value in self.members.items()])

            content.append(f'{{{item_str}}}')

        if self.params is not None:
            content.append(f'#({", ".join(param_lst)})')

        content.append(name_str)

        if self.verilog_type not in ('wire', 'logic', 'reg') and not self.verilog_type.startswith('enum'):  # other net types are out of scope for now
            content.append(f'({", ".join(connection_lst)})')

        return ' '.join(content)


class VerilogModule:
    """Represents a complete Verilog module.

    Args:
        name: The module name.

    Example:
        >>> module = VerilogModule("counter")
        >>> module.ports.append(VerilogPortDeclaration("input", "clk"))
        >>> module.ports.append(VerilogPortDeclaration("input", "reset"))
        >>> module.ports.append(VerilogPortDeclaration("output", "count", 4))
        >>> module.signals.append(VerilogDeclaration("reg", "count", 4))
        >>> print(module.render())
        module counter (
            input clk,
            input reset,
            output [3:0] count
        );
        reg [3:0] count;
        endmodule
        >>>
        >>> # Module with parameters
        >>> param_module = VerilogModule("multiplier")
        >>> param_module.parameters = {"WIDTH": 8}
        >>> param_module.ports.append(VerilogPortDeclaration("input", ["a", "b"]))
        >>> param_module.ports.append(VerilogPortDeclaration("output", "result", "WIDTH"))
        >>> print(param_module.render())
        module multiplier #(
            WIDTH
        ) (
            input a,
            input b,
            output [WIDTH-1:0] result
        );
        endmodule
    """

    def __init__(self, name: str) -> None:
        """Initialize the module.

        Args:
            name: The module name.
        """
        self.name = name
        self.ports: List[VerilogPortDeclaration] = []
        self.parameters: Dict[str, Optional[Union[int, str]]] = {}
        self.signals: List[VerilogDeclaration] = []
        self.instances: List[VerilogDeclaration] = []
        self.functionals: List[VerilogRenderable] = []

    def render(self) -> str:
        """Render the module.

        Returns:
            The complete Verilog module string.
        """
        content = []
        line = f'module {self.name} '

        if len(self.parameters) != 0:
            params = []
            for p, val in self.parameters.items():
                if val is None:
                    params.append(f'parameter {p}')
                else:
                    params.append(f'parameter {p} = {val}')

            line = f'{line} #(\n{",\n".join(params)}) '

        ports = [p.render() for p in self.ports]

        line = f'{line} ({",\n".join(ports)});'

        content.append(line)

        content.extend([item.render() + ';' for item in self.signals + self.instances])
        content.extend([item.render() for item in self.functionals])

        content.append('endmodule')

        code = '\n'.join(content)

        return VerilogFormatter(code).format()

    def get_instance(self, name: str) -> VerilogDeclaration:
        """Get a module instance by name.

        Args:
            name: The instance name.

        Returns:
            The VerilogDeclaration for the instance.

        Raises:
            RuntimeError: If the instance is not found.
        """
        for item in self.instances:
            if item.name == name:
                return item
        raise RuntimeError(f'Could not find an instance named {name}.')
