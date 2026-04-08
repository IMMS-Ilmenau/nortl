"""Ternary operation."""

from typing import Optional, Union

from nortl.core.protocols import Operand, Renderable
from nortl.core.renderers.operations.base import TernaryRenderer, const_unpack

__all__ = [
    'IfThenElse',
]


class IfThenElse(TernaryRenderer):
    def __call__(self, target: Optional[str] = None) -> str:
        # If the expression was folded, both values will be identical
        if (result := self.true_value.render(target=target)) == self.false_value.render(target=target):
            return result
        else:
            return f'({self.condition} ? {self.true_value} : {self.false_value})'

    @staticmethod
    def eval(condition: Operand, true_value: Operand, false_value: Operand) -> Optional[Union[Renderable, int]]:
        """Evaluate operation into constant value or single operand.

        If the condition is constantly True or False, will return the corresponding branch.
        """
        condition_ = const_unpack(condition)
        true_value_ = const_unpack(true_value)
        false_value_ = const_unpack(false_value)

        if condition_ is None:
            return None

        if condition_ > 0:
            if true_value_ is not None:
                return true_value_  # Constant value
            return true_value  # Single Renderable
        else:
            if false_value_ is not None:
                return false_value_  # Constant value
            return false_value  # Single renderable
