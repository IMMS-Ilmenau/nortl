"""Base classes for renderers."""

from abc import ABCMeta, abstractmethod
from typing import Generic, Optional, Protocol, Sequence, TypeVar, Union

from nortl.core.protocols import Operand, Renderable

__all__ = [
    'SequenceRenderer',
    'SingleRenderer',
    'SliceRenderer',
    'TwoSideRenderer',
    'const_unpack',
]

T = TypeVar('T', bound=Renderable)
T_Left = TypeVar('T_Left', bound=Renderable)
T_Right = TypeVar('T_Right', bound=Renderable)
T_Container = TypeVar('T_Container')


class SingleContainerProto(Protocol):
    @property
    def value(self) -> Renderable: ...


class TwoSideContainerProto(Protocol):
    @property
    def left(self) -> Renderable: ...

    @property
    def right(self) -> Renderable: ...


class SliceContainerProto(Protocol):
    @property
    def value(self) -> Renderable: ...

    @property
    def index(self) -> Union[int, slice]: ...


class SequenceContainerProto(Protocol):
    @property
    def parts(self) -> Sequence[Renderable]: ...


class TernaryContainerProto(Protocol):
    @property
    def condition(self) -> Renderable: ...

    @property
    def true_value(self) -> Renderable: ...

    @property
    def false_value(self) -> Renderable: ...


class RendererABC(Generic[T_Container], metaclass=ABCMeta):
    """Abstract baseclass for renderers."""

    def __init__(self, container: T_Container) -> None:
        """Initialize the renderer.

        Arguments:
            container: Operation wrapper container for the renderer.
        """
        self.container = container

    @abstractmethod
    def __call__(self, target: Optional[str] = None) -> str:
        """Render value to target language.

        Arguments:
            target: Target language.
        """


class SingleRenderer(RendererABC[SingleContainerProto]):
    """Base class for renderers for operations with a single value."""

    @property
    def value(self) -> Renderable:
        """Value to which the operation is applied."""
        return self.container.value

    @staticmethod
    @abstractmethod
    def eval(
        value: T,
    ) -> Optional[Union[T, Renderable, int]]:
        """Evaluate operation into constant value or single operand."""


class TwoSideRenderer(RendererABC[TwoSideContainerProto]):
    """Base class for renderers for operations with two values."""

    @property
    def left(self) -> Renderable:
        """Left or first value for the operation."""
        return self.container.left

    @property
    def right(self) -> Renderable:
        """Right or second value for the operation."""
        return self.container.right

    @staticmethod
    @abstractmethod
    def eval(left: Union[T_Left, int, bool], right: Union[T_Right, int, bool]) -> Optional[Union[T_Left, T_Right, Renderable, int]]:
        """Evaluate operation into constant value or single operand."""


class SliceRenderer(RendererABC[SliceContainerProto]):
    """Base class for renderers for slicing operations."""

    @property
    def value(self) -> Renderable:
        """Value to which the slice is applied."""
        return self.container.value

    @property
    def index(self) -> Union[int, slice]:
        """Slicing index."""
        return self.container.index


class SequenceRenderer(RendererABC[SequenceContainerProto]):
    """Base class for operations with a sequence of elements."""

    @property
    def parts(self) -> Sequence[Renderable]:
        """Parts of the sequence."""
        return self.container.parts

    @staticmethod
    @abstractmethod
    def eval(*args: Operand) -> Optional[Union[Renderable, int]]:
        """Evaluate operation into constant value or single operand."""


class TernaryRenderer(RendererABC[TernaryContainerProto]):
    """Base class for ternary operations."""

    @property
    def condition(self) -> Renderable:
        """Condition, selecting between `true_value` and `fals_value`."""
        return self.container.condition

    @property
    def true_value(self) -> Renderable:
        """Operand that is selected if `cond` is True."""
        return self.container.true_value

    @property
    def false_value(self) -> Renderable:
        """Operand that is selected if `cond` is False."""
        return self.container.false_value

    @staticmethod
    @abstractmethod
    def eval(condition: Operand, true_value: Operand, false_value: Operand) -> Optional[Union[Renderable, int]]:
        """Evaluate operation into constant value or single operand."""


def const_unpack(operand: Operand) -> Optional[int]:
    """Unpack value of the operand, if it is constant.

    Arguments:
        operand: Constant or other Renderable.

    Returns:
        The value of the constant or None, if the operand has a dynamic value.
    """
    if isinstance(operand, (int, bool)):
        return int(operand)
    if hasattr(operand, 'is_constant') and operand.is_constant:
        return operand.value  # type: ignore[attr-defined, no-any-return]
    return None
