from typing import Dict, Final, List, Optional, Union

from .operations import Const
from .protocols import ModuleProto, ParameterProto, PermanentSignal, Renderable


class Module:
    """Representation of a Verilog module."""

    def __init__(self, name: str, hdl_code: str = '') -> None:
        """Initialize a new Verilog module.

        Arguments:
            name: Name of the module.
            hdl_code: Verilog/VHDL code of the module that should be included in the output.
        """
        self._name: str = name
        self._port_names: List[str] = []
        self._parameters: Dict[str, int] = {}
        self._hdl_code: str = hdl_code

        # The following variable is used by the verilog renderer and masks out the connections of clk and reset
        # Should be handled with care! Therefore this will not be exposed
        self._ignore_clk_rst_connection: bool = False

        # This variable is used for synthesizing the clock network in the final module.
        # The verilog renderer will ignore this signal, if it is set to 'None', otherwise, it will
        # create and connect a signal and wire it up to the enable of the clock gate of the top module.
        self._clk_request_port: Union[None, str] = None

    @property
    def name(self) -> str:
        """Module name."""
        return self._name

    @property
    def ports(self) -> List[str]:
        """List of ports for this module."""
        return self._port_names

    @property
    def parameters(self) -> Dict[str, int]:
        """Dictionary of parameter names and their values."""
        return self._parameters

    @property
    def hdl_code(self) -> str:
        """HDL Code of the module."""
        return self._hdl_code

    def add_port(self, port_name: str) -> None:
        """Add a new port to the module.

        Arguments:
            port_name (str): The signal representing the port.
        """
        self._port_names.append(port_name)

    def has_port(self, port_name: str) -> bool:
        """Test, if a given port (identivfied by name) is in this module.

        Arguments:
            port_name (str): Port name to be checked

        Returns:
            bool: True, if port is in module
        """
        return port_name in self._port_names

    def add_parameter(self, name: str, value: int) -> None:
        """Add a new parameter to the module.

        Arguments:
            name: Name of the parameter.
            value: Value of the parameter.
        """
        self._parameters[name] = value

    def set_clk_request(self, port_name: str) -> None:
        """Set the clock request port for the rendering process.

        Arguments:
           port_name (str): The name of the clock request port.

        Note that this method should be called after all ports have been added.
        """
        if port_name in self._port_names:
            self._clk_request_port = port_name
        else:
            raise ValueError(f'Port {port_name} not found in module ports.')

    @property
    def clk_request_port(self) -> Optional[str]:
        """Get the clock request port for the rendering process.

        Returns:
           Optional[str]: The name of the clock request port or None if not set.
        """
        return self._clk_request_port


class ModuleInstance:
    """Representation of an instance of a Verilog module."""

    is_primitive: Final = False

    def __init__(self, module: ModuleProto, name: str, clock_gating: bool = False) -> None:
        """Initialize a new instance of a Verilog module.

        Arguments:
            module: The module to be instantiated.
            name: Name of the instance.
            clock_gating: If the clock is gated if the current state demands it (and clock gating is enabled in renderer)
        """
        self._module = module
        self._name = name
        self._port_connections: Dict[str, PermanentSignal] = {}  # Use signal name as key
        self._parameter_overrides: Dict[str, Union[Const, ParameterProto, Renderable]] = {}
        self._clock_gating = clock_gating

        if self._module.clk_request_port is not None:
            self._clock_gating = True

    @property
    def module(self) -> ModuleProto:
        """The module being instantiated."""
        return self._module

    @property
    def name(self) -> str:
        """Name of the instance."""
        return self._name

    @property
    def port_connections(self) -> Dict[str, PermanentSignal]:
        """Connections between the ports and signals."""
        return self._port_connections

    @property
    def parameter_overrides(self) -> Dict[str, Union[Const, ParameterProto, Renderable]]:
        """Dictionary of overridden parameter names and their values."""
        return self._parameter_overrides

    def connect_port(self, port_name: str, signal: PermanentSignal) -> None:
        """Connect a port of the instance to a signal.

        Arguments:
            port_name: The port being connected.
            signal: The signal it is being connected to.
        """
        if port_name not in self.module.ports:
            raise ValueError(f'Port {port_name} does not exist in module {self.module.name}')

        self._port_connections[port_name] = signal  # Use signal name as key

    def get_connected_signal(self, port_name: str) -> PermanentSignal:
        """Returns the signal that is connected to the given port.

        Arguments:
            port_name (str): The port where the connected signal should be acquired
        """

        if port_name not in self.module.ports:
            raise ValueError(f'Port {port_name} does not exist in module {self.module.name}')

        return self._port_connections[port_name]

    def override_parameter(self, name: str, value: Union[int, ParameterProto, Renderable]) -> None:
        """Override a parameter of the instance.

        Arguments:
            name: Name of the parameter to be overridden.
            value: New value for the parameter.
        """
        if name not in self.module.parameters:
            raise ValueError(f'Parameter {name} does not exist in module {self.module.name}')

        if isinstance(value, int):
            self._parameter_overrides[name] = Const(value)
        else:
            self._parameter_overrides[name] = value
