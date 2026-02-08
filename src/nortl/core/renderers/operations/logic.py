"""Logic operations."""

from typing import Optional, TypeVar, Union

from nortl.core.protocols import Operand, Renderable
from nortl.core.renderers.operations.base import TwoSideRenderer, const_unpack

__all__ = [
    'And',
    'ExclusiveOr',
    'LeftShift',
    'Or',
    'RightShift',
]

T_Left = TypeVar('T_Left', bound=Renderable)
T_Right = TypeVar('T_Right', bound=Renderable)


class And(TwoSideRenderer):
    def __call__(self, target: Optional[str] = None) -> str:
        return f'({self.left} & {self.right})'

    @staticmethod
    def eval(left: Operand, right: Operand) -> Optional[int]:
        """Evaluate operation into constant value or single operand.

        Short circuits for x & 0.
        """
        left_ = const_unpack(left)
        right_ = const_unpack(right)

        # Short circuiting: x & 0 = 0
        if left_ == 0 or right_ == 0:
            return 0
        # FIXME implement short circuiting for: x & 1 (must respect operand widths)

        if left_ is not None and right_ is not None:
            return left_ & right_
        return None


class Or(TwoSideRenderer):
    def __call__(self, target: Optional[str] = None) -> str:
        return f'({self.left} | {self.right})'

    @staticmethod
    def eval(left: Union[T_Left, int, bool], right: Union[T_Right, int, bool]) -> Optional[Union[T_Left, T_Right, int]]:
        """Evaluate operation into constant value.

        Short circuits for x | 0.
        """
        left_ = const_unpack(left)
        right_ = const_unpack(right)

        # Short circuiting: x | 0 = x
        if left_ == 0:
            return right
        if right_ == 0:
            return left
        # FIXME implement short circuiting for: x | 1 (must respect operand widths)

        if left_ is not None and right_ is not None:
            return left_ | right_
        return None


class ExclusiveOr(TwoSideRenderer):
    def __call__(self, target: Optional[str] = None) -> str:
        return f'({self.left} ^ {self.right})'

    @staticmethod
    def eval(left: Operand, right: Operand) -> Optional[int]:
        """Evaluate operation into constant value."""
        if (left_ := const_unpack(left)) is not None and (right_ := const_unpack(right)) is not None:
            return left_ ^ right_
        return None


class LeftShift(TwoSideRenderer):
    def __call__(self, target: Optional[str] = None) -> str:
        return f'({self.left} << {self.right})'

    @staticmethod
    def eval(left: Union[T_Left, int, bool], right: Union[T_Right, int, bool]) -> Optional[Union[T_Left, T_Right, int]]:
        """Evaluate operation into constant value.

        Short circuits for shift of/by 0.
        """
        left_ = const_unpack(left)
        right_ = const_unpack(right)

        # Short circuiting: x << 0 = x and 0 << x = 0
        if left_ == 0:
            return 0
        if right_ == 0:
            return left

        if left_ is not None and right_ is not None:
            return left_ << right_
        return None


class RightShift(TwoSideRenderer):
    def __call__(self, target: Optional[str] = None) -> str:
        return f'({self.left} >> {self.right})'

    @staticmethod
    def eval(left: Union[T_Left, int, bool], right: Union[T_Right, int, bool]) -> Optional[Union[T_Left, T_Right, int]]:
        """Evaluate operation into constant value.

        Short circuits for shift of/by 0.
        """
        left_ = const_unpack(left)
        right_ = const_unpack(right)

        # Short circuiting: x >> 0 = x and 0 >> x = 0
        if left_ == 0:
            return 0
        if right_ == 0:
            return left

        if left_ is not None and right_ is not None:
            return left_ >> right_
        return None
