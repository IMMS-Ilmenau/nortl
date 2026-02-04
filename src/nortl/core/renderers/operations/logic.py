"""Logic operations."""

from typing import Optional

from nortl.core.renderers.operations.base import TwoSideRenderer

__all__ = [
    'And',
    'ExclusiveOr',
    'LeftShift',
    'Or',
    'RightShift',
]


class And(TwoSideRenderer):
    def __call__(self, target: Optional[str] = None) -> str:
        return f'({self.left} & {self.right})'


class Or(TwoSideRenderer):
    def __call__(self, target: Optional[str] = None) -> str:
        return f'({self.left} | {self.right})'


class ExclusiveOr(TwoSideRenderer):
    def __call__(self, target: Optional[str] = None) -> str:
        return f'({self.left} ^ {self.right})'


class LeftShift(TwoSideRenderer):
    def __call__(self, target: Optional[str] = None) -> str:
        return f'({self.left} << {self.right})'


class RightShift(TwoSideRenderer):
    def __call__(self, target: Optional[str] = None) -> str:
        return f'({self.left} >> {self.right})'
