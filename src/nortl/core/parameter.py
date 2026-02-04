"""HDL Parameters."""

from typing import Final, Optional, Set

from .operations import OperationTrait
from .protocols import ACCESS_CHECKS, EngineProto

__all__ = [
    'Parameter',
]


class Parameter(OperationTrait):
    """Parameter definition, representing a Verilog parameter.

    The parameters are to be considered of data type int.

    Attributes:
        engine: Finite state machine associated with this Parameter.
        name: Name of the Parameter.
        default_value: Default value of the Parameter.

    """

    is_primitive: Final = True

    def __init__(self, engine: EngineProto, name: str, default_value: int, width: Optional[int] = None) -> None:
        """Initialize a Parameter object.

        Arguments:
            engine: State machine container object.
            name: Parameter name.
            default_value:  Default value of the parameter
            width: Width of the parameter.
        """
        if name.startswith('_'):
            raise ValueError('Parameter names must not start with an underscore!')

        self._engine = engine
        self._name = name
        self._default_value = default_value
        self._width = width

    @property
    def engine(self) -> EngineProto:
        """Finite state machine."""
        return self._engine

    @property
    def name(self) -> str:
        """Parameter name."""
        return self._name

    @property
    def default_value(self) -> int:
        """Default value."""
        return self._default_value

    @property
    def width(self) -> Optional[int]:
        """Indicates the width of the parameter in bits.

        Parameters with a fixed width will be rendered as `parameter [<width>-1:0] <name>`.
        """
        return self._width

    # Implement OperationTrait
    @property
    def operand_width(self) -> Optional[int]:
        """Indicates the width when used as an operand.

        A width of None means that the width is not fixed during execution of noRTL.
        """
        return self.width

    def read_access(self, ignore: Set[ACCESS_CHECKS] = set()) -> None:
        """Register read access from the current thread, state and construct depth.

        Does not invoke any checks for this object.
        """

    def render(self, target: Optional[str] = None) -> str:
        """Render value to target language.

        Arguments:
            target: Target language.
        """
        return self.name
