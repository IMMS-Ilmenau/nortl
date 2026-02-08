"""Miscellaneous operations."""

from typing import Optional, TypeVar, Union

from nortl.core.protocols import Operand, Renderable
from nortl.core.renderers.operations.base import SingleRenderer, const_unpack

__all__ = [
    'Inversion',
    'Negative',
    'Positive',
]


class Negative(SingleRenderer):
    def __call__(self, target: Optional[str] = None) -> str:
        return f'-{self.value}'

    @staticmethod
    def eval(value: Operand) -> Optional[int]:
        """Evaluate operation into constant value."""
        if (value_ := const_unpack(value)) is not None:
            return -value_
        return None


T = TypeVar('T', bound=Renderable)


class Positive(SingleRenderer):
    def __call__(self, target: Optional[str] = None) -> str:
        # Positive renderer should never really be used under normal conditions, because the operation does nothing
        return f'+{self.value}'  # pragma: no cover

    @staticmethod
    def eval(value: T) -> Optional[Union[T, int]]:
        """Evaluate operation into constant value or single operand."""
        if (value_ := const_unpack(value)) is not None:
            return value_

        # Always return the input operand, no need to wrap it in a Operation
        return value


class Inversion(SingleRenderer):
    def __call__(self, target: Optional[str] = None) -> str:
        return f'~({self.value})'

    @staticmethod
    def eval(value: Operand) -> Optional[int]:
        """Evaluate operation into constant value."""
        if (value_ := const_unpack(value)) is not None:
            return ~value_
        return None
