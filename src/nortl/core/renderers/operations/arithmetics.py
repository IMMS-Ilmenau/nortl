"""Arithmetic operations."""

from typing import Optional, TypeVar, Union

from nortl.core.protocols import Operand, Renderable
from nortl.core.renderers.operations.base import TwoSideRenderer, const_unpack

__all__ = [
    'Addition',
    'Division',
    'Modulo',
    'Multiplication',
    'Substraction',
]

T_Left = TypeVar('T_Left', bound=Renderable)
T_Right = TypeVar('T_Right', bound=Renderable)


class Addition(TwoSideRenderer):
    def __call__(self, target: Optional[str] = None) -> str:
        return f'({self.left} + {self.right})'

    @staticmethod
    def eval(left: Union[T_Left, int, bool], right: Union[T_Right, int, bool]) -> Optional[Union[T_Left, T_Right, int]]:
        """Evaluate operation into constant value or single operand.

        Short circuits for addition of 0.
        """
        left_ = const_unpack(left)
        right_ = const_unpack(right)

        # Short circuiting: x + 0 = x
        if left_ == 0:
            return right
        if right_ == 0:
            return left

        if left_ is not None and right_ is not None:
            return left_ + right_
        return None


class Substraction(TwoSideRenderer):
    def __call__(self, target: Optional[str] = None) -> str:
        return f'({self.left} - {self.right})'

    @staticmethod
    def eval(left: Union[T_Left, int, bool], right: Union[T_Right, int, bool]) -> Optional[Union[T_Left, Renderable, int]]:
        """Evaluate operation into constant value or single operand.

        Short circuits for substraction of 0.
        """
        left_ = const_unpack(left)
        right_ = const_unpack(right)

        # Short circuiting: x - 0 = x
        if right_ == 0:
            return left
        if left_ == 0:
            return -right

        if left_ is not None and right_ is not None:
            return left_ - right_
        return None


class Multiplication(TwoSideRenderer):
    def __call__(self, target: Optional[str] = None) -> str:
        return f'({self.left} * {self.right})'

    @staticmethod
    def eval(left: Union[T_Left, int, bool], right: Union[T_Right, int, bool]) -> Optional[Union[T_Left, T_Right, int]]:
        """Evaluate operation into constant value or single operand.

        Short circuits for multiplication with 0 or 1.
        """
        left_ = const_unpack(left)
        right_ = const_unpack(right)

        # Short circuiting: x * 0 = 0
        if left_ == 0 or right_ == 0:
            return 0
        # Short circuiting: x * 1 = x
        if left_ == 1:
            return right
        if right_ == 1:
            return left

        # Other constants
        if left_ is not None and right_ is not None:
            return left_ * right_
        return None


class Division(TwoSideRenderer):
    def __call__(self, target: Optional[str] = None) -> str:
        return f'({self.left} / {self.right})'

    @staticmethod
    def eval(left: Union[T_Left, int, bool], right: Union[T_Right, int, bool]) -> Optional[Union[T_Left, T_Right, int]]:
        """Evaluate operation into constant value or single operand.

        Short circuits for division by 0 or 1.
        """
        dividend = const_unpack(left)
        divisor = const_unpack(right)

        # Short circuiting: x / 0 is invalid
        if divisor == 0:
            raise ZeroDivisionError(f'Expression {left} / {right} leads to division by zero.')
        # Short circuiting: 0 / x = 0
        if dividend == 0:
            return 0
        # Short circuiting: x / 1 = x
        if divisor == 1:
            return left

        # Other constants
        if dividend is not None and divisor is not None:
            return int(dividend / divisor)
        return None


class Modulo(TwoSideRenderer):
    def __call__(self, target: Optional[str] = None) -> str:
        return f'({self.left} % {self.right})'

    @staticmethod
    def eval(left: Operand, right: Operand) -> Optional[int]:
        """Evaluate operation into constant value."""
        if (left_ := const_unpack(left)) is not None and (right_ := const_unpack(right)) is not None:
            return left_ % right_
        return None
