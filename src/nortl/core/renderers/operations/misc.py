"""Miscellaneous operations."""

from typing import Optional

from nortl.core.renderers.operations.base import SingleRenderer

__all__ = [
    'Inversion',
    'Negative',
    'Positive',
]


class Negative(SingleRenderer):
    def __call__(self, target: Optional[str] = None) -> str:
        return f'-{self.value}'


class Positive(SingleRenderer):
    def __call__(self, target: Optional[str] = None) -> str:
        return f'+{self.value}'


class Inversion(SingleRenderer):
    def __call__(self, target: Optional[str] = None) -> str:
        return f'~({self.value})'
