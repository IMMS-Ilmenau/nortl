"""Modifiers can be applied to Renderables."""

from abc import abstractmethod
from contextlib import ExitStack
from typing import Generic, Literal, Never, Optional, Self, Set, TypeVar, Union

from nortl.core.exceptions import WriteViolationError
from nortl.core.operations import OperationTrait
from nortl.core.protocols import (
    ACCESS_CHECKS,
    SIGNAL_ACCESS_CHECKS,
    AnySignal,
    AssignmentTarget,
    EngineProto,
    PermanentSignal,
    Renderable,
)

__all__ = [
    'UnregisteredRead',
    'Volatile',
    'WeakReference',
]

T_Content = TypeVar('T_Content', bound=Renderable)
T_Signal = TypeVar('T_Signal', bound=AnySignal)
T_PermanentSignal = TypeVar('T_PermanentSignal', bound=PermanentSignal)


# Modifiers
class BaseModifier(Generic[T_Content], OperationTrait, ExitStack):
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

    @abstractmethod
    def copy(self, content: T_Content) -> Self:
        """Copy modifier to new content."""

    # Implement OperationTrait
    @property
    def is_primitive(self) -> bool:
        """Indicates if this object is a Verilog primitive."""
        return self.content.is_primitive

    @property
    def is_constant(self) -> bool:
        """Indicates if this object has a constant value."""
        return self.content.is_constant

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

    # Support unpacking of constants
    @property
    def value(self) -> int:
        """Value of content, if the object has a constant value."""
        if self.is_constant:
            return self.content.value  # type: ignore[attr-defined, no-any-return]
        else:
            raise RuntimeError("Content of modifier is not constant. It's value must not be accessed.")


class UnregisteredRead(Generic[T_Content], BaseModifier[T_Content]):
    """Modifier for signals or operations, that hides them from read accesses.

    Any read access to signals inside a UnregisteredRead modifier is not registered.
    Note that this does not permanently disable the access checks, when acessing the signals normally.

    !!! danger
        This modifier is meant for internal purposes. For example, it is used in the noRTL test wrapper for assertions.
        It must not be used in production code!
    """

    def copy(self, content: T_Content) -> 'UnregisteredRead[T_Content]':
        """Copy modifier to new content."""
        return UnregisteredRead(content)

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

    def copy(self, content: T_Signal) -> 'Volatile[T_Signal]':
        """Copy modifier to new content."""
        return Volatile(content, *self.ignore)

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


class ReadOnly(Generic[T_Signal], BaseModifier[T_Signal]):
    """Modifier for signals to mark them as read-only.

    Writing to a noRTL signal that is wrapped in a ReadOnly modifier will throw an Access Violation.
    """

    def copy(self, content: T_Signal) -> 'ReadOnly[T_Signal]':
        """Copy modifier to new content."""
        return ReadOnly(content)

    # Implement OperationTrait
    def read_access(self, ignore: Set[ACCESS_CHECKS] = set()) -> None:
        """Register read access from the current thread, state and construct depth."""
        self.content.read_access(ignore=ignore)

    # Implement AssignmentTarget
    @property
    def name(self) -> str:
        """Just return name."""
        return self.content.name

    @property
    def engine(self) -> EngineProto:
        """NoRTL engine that the signal belongs to."""
        return self.content.engine

    def write_access(self, ignore: Set[ACCESS_CHECKS] = set()) -> Never:
        """Register write access from the current thread."""
        raise WriteViolationError(f'Signal {self.name} is marked as read-only.')

    def overlaps_with(self, other: AssignmentTarget) -> Union[bool, Literal['partial']]:
        """Check if signal overlaps with other signal or signal slice."""
        return self.content.overlaps_with(other)

    # Emulate Scratch Signal
    def __enter__(self) -> Self:
        if hasattr(self.content, '__enter__'):
            self.enter_context(self.content)  # type: ignore
        return self


class WeakReference(Generic[T_PermanentSignal], BaseModifier[T_PermanentSignal]):
    """Modifier for signals to mark them as weak references to the underlying signal.

    The reference can be expired at any time.
    """

    def __init__(self, content: T_PermanentSignal):
        super().__init__(content)
        self._expired = False

    def copy(self, content: T_PermanentSignal) -> 'WeakReference[T_PermanentSignal]':
        """Copy modifier to new content."""
        return WeakReference(self.content)

    @property
    def expired(self) -> bool:
        """Indicates if this signal is expired."""
        return self._expired

    def expire(self) -> None:
        """Marks this signal as expired. Any further access is forbidden."""
        self._expired = True

    # Implement OperationTrait
    def read_access(self, ignore: Set[ACCESS_CHECKS] = set()) -> None:
        """Register read access from the current thread, state and construct depth."""
        if self.expired:
            raise RuntimeError(
                f'Signal {self.name} is expired.\nThis can happen, if the signal was returned from a segment and the segment was called again, making this reference to the signal invalid.'
            )
        self.content.read_access(ignore=ignore)

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
        if self.expired:
            raise RuntimeError(f'Signal {self.name} is expired.')
        self.content.write_access(ignore=ignore)

    def overlaps_with(self, other: AssignmentTarget) -> Union[bool, Literal['partial']]:
        """Check if signal overlaps with other signal or signal slice."""
        return self.content.overlaps_with(other)
