"""Sequence operations."""

from typing import Optional, Union

from nortl.core.protocols import Operand, Renderable
from nortl.core.renderers.operations.base import SequenceRenderer, const_unpack

__all__ = [
    'All',
    'Any',
    'Concat',
]


class Concat(SequenceRenderer):
    def __call__(self, target: Optional[str] = None) -> str:
        rendered_parts = [p.render(target) for p in self.parts]
        if len(rendered_parts) == 1:
            return rendered_parts[0]
        return f'{{{", ".join(rendered_parts)}}}'

    @staticmethod
    def eval(*args: Operand) -> Optional[Union[Renderable, int]]:
        """Evaluate operation into constant value or single operand.

        Unpacks the concatenation, if it consists of a single value.
        """
        args_ = tuple(const_unpack(arg) for arg in args)

        # Unpack single entry
        if len(args_) == 1:
            if (arg := args_[0]) is not None:
                return arg  # Constant value
            return args[0]  # Single renderable

        return None


class Any(SequenceRenderer):
    def __call__(self, target: Optional[str] = None) -> str:
        rendered_parts = [p.render(target) for p in self.parts]
        if len(rendered_parts) == 1:
            return rendered_parts[0]
        return f'({" || ".join(rendered_parts)})'

    @staticmethod
    def eval(*args: Operand) -> Optional[Union[Renderable, int]]:
        """Evaluate operation into constant value or single operand.

        Unpacks the Any, if it consists of a single value.
        Short circuits, if any element is > 0 or all are 0.
        """
        args_ = tuple(const_unpack(arg) for arg in args)

        # Unpack single entry
        if len(args_) == 1:
            if (arg := args_[0]) is not None:
                return arg  # Constant value
            return args[0]  # Single renderable

        # Short circuiting: any argument is > 0
        if any(arg is not None and arg > 0 for arg in args_):
            return 1

        # Short circuiting: all arguments are == 0
        if all(arg is not None and arg == 0 for arg in args_):
            return 0
        return None


class All(SequenceRenderer):
    def __call__(self, target: Optional[str] = None) -> str:
        rendered_parts = [p.render(target) for p in self.parts]
        if len(rendered_parts) == 1:
            return rendered_parts[0]
        return f'({" && ".join(rendered_parts)})'

    @staticmethod
    def eval(*args: Operand) -> Optional[Union[Renderable, int]]:
        """Evaluate operation into constant value or single operand.

        Unpacks the All, if it consists of a single value.
        Short circuits, if any element is 0 or all are > 0.
        """
        args_ = tuple(const_unpack(arg) for arg in args)

        # Unpack single entry
        if len(args_) == 1:
            if (arg := args_[0]) is not None:
                return arg  # Constant value
            return args[0]  # Single renderable

        # Short circuiting: any argument is == 0
        if any(arg is not None and arg == 0 for arg in args_):
            return 0

        # Short circuiting: all arguments are > 0
        if all(arg is not None and arg > 0 for arg in args_):
            return 1
        return None
