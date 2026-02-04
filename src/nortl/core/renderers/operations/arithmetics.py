"""Arithmetic operations."""

from typing import Optional

from nortl.core.renderers.operations.base import TwoSideRenderer

__all__ = [
    'Addition',
    'Division',
    'Modulo',
    'Multiplication',
    'Substraction',
]


class Addition(TwoSideRenderer):
    def __call__(self, target: Optional[str] = None) -> str:
        return f'({self.left} + {self.right})'


class Substraction(TwoSideRenderer):
    def __call__(self, target: Optional[str] = None) -> str:
        return f'({self.left} - {self.right})'


class Multiplication(TwoSideRenderer):
    def __call__(self, target: Optional[str] = None) -> str:
        return f'({self.left} * {self.right})'


class Division(TwoSideRenderer):
    def __call__(self, target: Optional[str] = None) -> str:
        return f'({self.left} / {self.right})'


class Modulo(TwoSideRenderer):
    def __call__(self, target: Optional[str] = None) -> str:
        return f'({self.left} % {self.right})'
