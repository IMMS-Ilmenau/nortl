"""Modifiers can be applied to Renderables."""

from typing import Generic, Literal, Optional, Set, TypeVar, Union

from nortl.core.operations import OperationTrait
from nortl.core.protocols import ACCESS_CHECKS, SIGNAL_ACCESS_CHECKS, AnySignal, AssignmentTarget, EngineProto, Renderable

__all__ = [
    'UnregisteredRead',
    'Volatile',
]
T_Content = TypeVar('T_Content', bound=Renderable)
T_Signal = TypeVar('T_Signal', bound=AnySignal)


# Modifiers
class BaseModifier(Generic[T_Content], OperationTrait):
    """Baseclass for Modifiers."""

    def __init__(self, content: T_Content) -> None:
        """Initialize an alias.

        Arguments:
            content: An operation result.
        """
        self._content = content
        super().__init__()

    @property
    def content(self) -> T_Content:
        """Content of the alias."""
        return self._content

    # Implement OperationTrait
    @property
    def is_primitive(self) -> bool:
        """Indicates if this object is a Verilog primitive."""
        return self.content.is_primitive

    @property
    def operand_width(self) -> Optional[int]:
        """Indicates the width when used as an operand, equal to the width of the alias operation.

        A width of None means that the width is not fixed during execution of noRTL.
        """
        return self.content.operand_width

    def render(self, target: Optional[str] = None) -> str:
        """Render operation to target language.

        Arguments:
            target: Target language.
        """
        return self.content.render(target=target)

    def __format__(self, format_spec: str) -> str:
        return self.render()

    # TODO Modifier must only be valid within current construct


class UnregisteredRead(Generic[T_Content], BaseModifier[T_Content]):
    """Modifier for signals or operations, that hides them from read accesses.

    Any read access to signals inside a UnregisteredRead modifier is not registered.
    Note that this does not permanently disable the access checks, when acessing the signals normally.

    !!! danger
        This modifier is meant for internal purposes. For example, it is used in the noRTL test wrapper for assertions.
        It must not be used in production code!
    """

    def read_access(self, ignore: Set[ACCESS_CHECKS] = set()) -> None:
        """Register read access from the current thread, state and construct depth.

        Does nothing for UnregisteredRead.
        """


class Volatile(Generic[T_Signal], BaseModifier[T_Signal]):
    """Modifier for signals, allowing them to be shared between threads.

    Wrapping a noRTL signal will temporarily ignore the following checks by default:

    - Exclusive Read Check ([ExclusiveReadError][nortl.core.exceptions.ExclusiveReadError]): The modified object can be read from multiple threads.
    - Non-Identical Read/Write Check ([NonIdenticalRWError][nortl.core.exceptions.NonIdenticalRWError]): The modified object can be read/written from different threads.

    It's possible to select other checks to ignore, by listing their names, e.g.:

    ```python
    # Ignore a set of checks
    unsafe_signal = Volatile(signal, 'identical_rw', 'exclusive_write')

    # Ignore a single check
    unsafe_signal = Volatile(signal, 'identical_rw')
    ```

    Note that this does not permanently disable the access checks. The read or write access to the signal is still registered.
    If the same signal is used in other places, it may still cause access violations exceptions.
    """

    def __init__(self, content: T_Signal, *ignore: SIGNAL_ACCESS_CHECKS) -> None:
        super().__init__(content)
        if len(ignore) > 0:
            self._ignore: Set[SIGNAL_ACCESS_CHECKS] = set(ignore)
        else:
            self._ignore = {'exclusive_read', 'identical_rw'}

    @property
    def ignore(self) -> Set[SIGNAL_ACCESS_CHECKS]:
        """Set of ignored access checks."""
        return self._ignore

    # Implement OperationTrait
    def read_access(self, ignore: Set[ACCESS_CHECKS] = set()) -> None:
        """Register read access from the current thread, state and construct depth."""
        self.content.read_access(ignore=ignore | self.ignore)

    # Implement AssignmentTarget
    @property
    def name(self) -> str:
        """Just return name."""
        return self.content.name

    @property
    def engine(self) -> EngineProto:
        """NoRTL engine that the signal belongs to."""
        return self.content.engine

    def write_access(self, ignore: Set[ACCESS_CHECKS] = set()) -> None:
        """Register write access from the current thread."""
        self.content.write_access(ignore=ignore | self.ignore)

    def overlaps_with(self, other: AssignmentTarget) -> Union[bool, Literal['partial']]:
        """Check if signal overlaps with other signal or signal slice."""
        return self.content.overlaps_with(other)
