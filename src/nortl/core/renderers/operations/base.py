"""Base classes for renderers."""

from abc import ABCMeta, abstractmethod
from typing import Optional, Protocol, Union

__all__ = [
    'SingleRenderer',
    'SliceRenderer',
    'TwoSideRenderer',
]


class Renderable(Protocol):
    @property
    def is_primitive(self) -> bool: ...

    def render(self, target: Optional[str] = None) -> str: ...


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


class RendererABC(metaclass=ABCMeta):
    """Abstract baseclass for renderers."""

    @abstractmethod
    def __call__(self, target: Optional[str] = None) -> str:
        """Render value to target language.

        Arguments:
            target: Target language.
        """


class SingleRenderer(RendererABC):
    """Base class for renderers for operations with a single value."""

    def __init__(self, container: SingleContainerProto) -> None:
        """Initialize the renderer.

        Arguments:
            container: Operation wrapper container for the renderer.
        """
        self.container = container

    @property
    def value(self) -> Renderable:
        """Value to which the operation is applied."""
        return self.container.value


class TwoSideRenderer(RendererABC):
    """Base class for renderers for operations with two values."""

    def __init__(self, container: TwoSideContainerProto) -> None:
        """Initialize the renderer.

        Arguments:
            container: Operation wrapper container for the renderer.
        """
        self.container = container

    @property
    def left(self) -> Renderable:
        """Left or first value for the operation."""
        return self.container.left

    @property
    def right(self) -> Renderable:
        """Right or second value for the operation."""
        return self.container.right


class SliceRenderer(RendererABC):
    """Base class for renderers for slicing operations."""

    def __init__(self, container: SliceContainerProto) -> None:
        """Initialize the renderer.

        Arguments:
            container: Operation wrapper container for the renderer.
        """
        self.container = container

    @property
    def value(self) -> Renderable:
        """Value to which the slice is applied."""
        return self.container.value

    @property
    def index(self) -> Union[int, slice]:
        """Slicing index."""
        return self.container.index
