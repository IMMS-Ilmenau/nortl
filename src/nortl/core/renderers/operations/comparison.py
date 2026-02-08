"""Comparison operations."""

from typing import Optional

from nortl.core.protocols import Operand
from nortl.core.renderers.operations.base import TwoSideRenderer, const_unpack

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

    @staticmethod
    def eval(left: Operand, right: Operand) -> Optional[int]:
        """Evaluate operation into constant value."""
        if (left_ := const_unpack(left)) is not None and (right_ := const_unpack(right)) is not None:
            return left_ == right_
        return None


class Unequality(TwoSideRenderer):
    def __call__(self, target: Optional[str] = None) -> str:
        return f'({self.left} != {self.right})'

    @staticmethod
    def eval(left: Operand, right: Operand) -> Optional[int]:
        """Evaluate operation into constant value."""
        if (left_ := const_unpack(left)) is not None and (right_ := const_unpack(right)) is not None:
            return left_ != right_
        return None


class Less(TwoSideRenderer):
    def __call__(self, target: Optional[str] = None) -> str:
        return f'({self.left} < {self.right})'

    @staticmethod
    def eval(left: Operand, right: Operand) -> Optional[int]:
        """Evaluate operation into constant value."""
        if (left_ := const_unpack(left)) is not None and (right_ := const_unpack(right)) is not None:
            return left_ < right_
        return None


class LessOrEqual(TwoSideRenderer):
    def __call__(self, target: Optional[str] = None) -> str:
        return f'({self.left} <= {self.right})'

    @staticmethod
    def eval(left: Operand, right: Operand) -> Optional[int]:
        """Evaluate operation into constant value."""
        if (left_ := const_unpack(left)) is not None and (right_ := const_unpack(right)) is not None:
            return left_ <= right_
        return None


class Greater(TwoSideRenderer):
    def __call__(self, target: Optional[str] = None) -> str:
        return f'({self.left} > {self.right})'

    @staticmethod
    def eval(left: Operand, right: Operand) -> Optional[int]:
        """Evaluate operation into constant value."""
        if (left_ := const_unpack(left)) is not None and (right_ := const_unpack(right)) is not None:
            return left_ > right_
        return None


class GreaterOrEqual(TwoSideRenderer):
    def __call__(self, target: Optional[str] = None) -> str:
        return f'({self.left} >= {self.right})'

    @staticmethod
    def eval(left: Operand, right: Operand) -> Optional[int]:
        """Evaluate operation into constant value."""
        if (left_ := const_unpack(left)) is not None and (right_ := const_unpack(right)) is not None:
            return left_ >= right_
        return None
