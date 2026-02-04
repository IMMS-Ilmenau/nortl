"""Comparison operations."""

from typing import Optional

from nortl.core.renderers.operations.base import TwoSideRenderer

__all__ = [
    'Equality',
    'Greater',
    'GreaterOrEqual',
    'Less',
    'LessOrEqual',
    'Unequality',
]


class Equality(TwoSideRenderer):
    def __call__(self, target: Optional[str] = None) -> str:
        return f'({self.left} == {self.right})'


class Unequality(TwoSideRenderer):
    def __call__(self, target: Optional[str] = None) -> str:
        return f'({self.left} != {self.right})'


class Less(TwoSideRenderer):
    def __call__(self, target: Optional[str] = None) -> str:
        return f'({self.left} < {self.right})'


class LessOrEqual(TwoSideRenderer):
    def __call__(self, target: Optional[str] = None) -> str:
        return f'({self.left} <= {self.right})'


class Greater(TwoSideRenderer):
    def __call__(self, target: Optional[str] = None) -> str:
        return f'({self.left} > {self.right})'


class GreaterOrEqual(TwoSideRenderer):
    def __call__(self, target: Optional[str] = None) -> str:
        return f'({self.left} >= {self.right})'
