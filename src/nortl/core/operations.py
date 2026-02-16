"""Operations.

This module implements the "magic" operations that can be applied to signals or constants.
The actual rendering (which decides how they are converted to Verilog) is decoupled from this.
"""

from abc import ABCMeta, abstractmethod
from math import ceil, log2
from types import GeneratorType
from typing import (
    Callable,
    ClassVar,
    Dict,
    Final,
    Generator,
    Generic,
    Iterable,
    List,
    Literal,
    Never,
    Optional,
    Protocol,
    Sequence,
    Set,
    Type,
    TypeVar,
    Union,
    overload,
)

from nortl.core.protocols import ACCESS_CHECKS, Renderable
from nortl.core.renderers.operations import (
    Addition,
    And,
    Division,
    Equality,
    ExclusiveOr,
    Greater,
    GreaterOrEqual,
    Inversion,
    LeftShift,
    Less,
    LessOrEqual,
    Modulo,
    Multiplication,
    Negative,
    Or,
    Positive,
    RightShift,
    SingleRenderer,
    Slice,
    SliceRenderer,
    Substraction,
    TwoSideRenderer,
    Unequality,
)
from nortl.core.renderers.operations import All as AllRenderer
from nortl.core.renderers.operations import Any as AnyRenderer
from nortl.core.renderers.operations import Concat as ConcatRenderer
from nortl.core.renderers.operations import IfThenElse as IfThenElseRenderer
from nortl.core.renderers.operations.base import SequenceRenderer, TernaryRenderer
from nortl.utils.parse_utils import parse_int

__all__ = [
    'All',
    'Any',
    'Concat',
    'Const',
    'IfThenElse',
    'OperationTrait',
    'SingleOperation',
    'TwoSideOperation',
    'Var',
]

T_Renderer = TypeVar('T_Renderer', bound='RendererProto')

Operand = Union[Renderable, int, bool]


class RendererProto(Protocol):
    def __init__(self, container: object) -> None: ...
    def __call__(self, target: Optional[str] = None) -> str: ...


def greater_operand_width(a: Renderable, b: Renderable) -> Optional[int]:
    """Determines the result width of a logic operation by choosing the greater of the two operand widths."""
    if a.operand_width is None or b.operand_width is None:
        return None
    return max(a.operand_width, b.operand_width)


class OperationTrait(metaclass=ABCMeta):
    """Trait for signals, constants or statements that allow construction of arithmetic and logic operations."""

    @property
    @abstractmethod
    def is_primitive(self) -> bool:
        """Indicates if this object is a Verilog primitive."""

    @property
    @abstractmethod
    def is_constant(self) -> bool:
        """Indicates if this object has a constant value."""

    @property
    @abstractmethod
    def operand_width(self) -> Optional[int]:
        """Indicates the width when used as an operand.

        A width of None means that the width is not fixed during execution of noRTL.
        This will be the case for [parameters][nortl.core.parameter.Parameter] or [constants][nortl.core.operations.Const] without explicit width.
        """

    @abstractmethod
    def read_access(self, ignore: Set[ACCESS_CHECKS] = set()) -> None:
        """Register read access from the current thread, state and construct depth.

        For signals, this will register an read access from the current thread.
        For scratch signals, this will in addition check if the signal was released, based on the construct depth.
        """

    @abstractmethod
    def render(self, target: Optional[str] = None) -> str: ...

    def __format__(self, format_spec: str) -> str:
        return self.render()

    # Arithemtic Operations
    # TODO all two side operations loose the width
    def __add__(self, value: Operand, /) -> Renderable:
        return TwoSideOperation.create_or_fold_operation(left=self, right=value, renderer=Addition)

    def __sub__(self, value: Operand, /) -> Renderable:
        return TwoSideOperation.create_or_fold_operation(left=self, right=value, renderer=Substraction)

    def __mul__(self, value: Operand, /) -> Renderable:
        return TwoSideOperation.create_or_fold_operation(left=self, right=value, renderer=Multiplication)

    def __truediv__(self, value: Operand, /) -> Renderable:
        return TwoSideOperation.create_or_fold_operation(left=self, right=value, renderer=Division)

    def __mod__(self, value: Operand, /) -> Renderable:
        return TwoSideOperation.create_or_fold_operation(left=self, right=value, renderer=Modulo)

    # Arithmetic Operations (Right-Side)
    def __radd__(self, value: Operand, /) -> Renderable:
        return TwoSideOperation.create_or_fold_operation(left=value, right=self, renderer=Addition)

    def __rsub__(self, value: Operand, /) -> Renderable:
        return TwoSideOperation.create_or_fold_operation(left=value, right=self, renderer=Substraction)

    def __rmul__(self, value: Operand, /) -> Renderable:
        return TwoSideOperation.create_or_fold_operation(left=value, right=self, renderer=Multiplication)

    def __rtruediv__(self, value: Operand, /) -> Renderable:
        return TwoSideOperation.create_or_fold_operation(left=value, right=self, renderer=Division)

    def __rmod__(self, value: Operand, /) -> Renderable:
        return TwoSideOperation.create_or_fold_operation(left=value, right=self, renderer=Modulo)

    # Logic Operations
    def __and__(self, value: Operand, /) -> Renderable:
        return TwoSideOperation.create_or_fold_operation(left=self, right=value, renderer=And, width=greater_operand_width)

    def __or__(self, value: Operand, /) -> Renderable:
        return TwoSideOperation.create_or_fold_operation(left=self, right=value, renderer=Or, width=greater_operand_width)

    def __xor__(self, value: Operand, /) -> Renderable:
        return TwoSideOperation.create_or_fold_operation(left=self, right=value, renderer=ExclusiveOr, width=greater_operand_width)

    def __lshift__(self, value: Operand, /) -> Renderable:
        return TwoSideOperation.create_or_fold_operation(left=self, right=value, renderer=LeftShift)

    def __rshift__(self, value: Operand, /) -> Renderable:
        return TwoSideOperation.create_or_fold_operation(left=self, right=value, renderer=RightShift)

    # Logic Operations (Right Side)
    def __rand__(self, value: Operand, /) -> Renderable:
        return TwoSideOperation.create_or_fold_operation(left=value, right=self, renderer=And, width=greater_operand_width)

    def __ror__(self, value: Operand, /) -> Renderable:
        return TwoSideOperation.create_or_fold_operation(left=value, right=self, renderer=Or, width=greater_operand_width)

    def __rxor__(self, value: Operand, /) -> Renderable:
        return TwoSideOperation.create_or_fold_operation(left=value, right=self, renderer=ExclusiveOr, width=greater_operand_width)

    def __rlshift__(self, value: Operand, /) -> Renderable:
        return TwoSideOperation.create_or_fold_operation(left=value, right=self, renderer=LeftShift)

    def __rrshift__(self, value: Operand, /) -> Renderable:
        return TwoSideOperation.create_or_fold_operation(left=value, right=self, renderer=RightShift)

    # Misc.
    def __neg__(self) -> Renderable:
        return SingleOperation.create_or_fold_operation(value=self, renderer=Negative)

    def __pos__(self) -> 'Renderable':
        return SingleOperation.create_or_fold_operation(value=self, renderer=Positive)

    # Inversion
    def __invert__(self) -> Renderable:
        return SingleOperation.create_or_fold_operation(value=self, renderer=Inversion)

    # Comparison
    def __eq__(self, value: Operand, /) -> Renderable:  # type: ignore[override]
        return TwoSideOperation.create_or_fold_operation(left=self, right=value, renderer=Equality, width=1)

    def __ne__(self, value: Operand, /) -> Renderable:  # type: ignore[override]
        return TwoSideOperation.create_or_fold_operation(left=self, right=value, renderer=Unequality, width=1)

    def __lt__(self, value: Operand, /) -> Renderable:
        return TwoSideOperation.create_or_fold_operation(left=self, right=value, renderer=Less, width=1)

    def __le__(self, value: Operand, /) -> Renderable:
        return TwoSideOperation.create_or_fold_operation(left=self, right=value, renderer=LessOrEqual, width=1)

    def __gt__(self, value: Operand, /) -> Renderable:
        return TwoSideOperation.create_or_fold_operation(left=self, right=value, renderer=Greater, width=1)

    def __ge__(self, value: Operand, /) -> Renderable:
        return TwoSideOperation.create_or_fold_operation(left=self, right=value, renderer=GreaterOrEqual, width=1)

    # Bit Slicing
    def __getitem__(self, index: Union[int, slice]) -> Renderable:
        return SliceOperation(value=self, index=index, renderer=Slice)


@overload
def to_renderable(value: Operand, allow_string_literal: Literal[False] = ...) -> Renderable: ...
@overload
def to_renderable(value: Union[Operand, str], allow_string_literal: Literal[True] = ...) -> Renderable: ...


def to_renderable(value: Union[Operand, str], allow_string_literal: bool = False) -> Renderable:
    """Convert value to renderable object.

    Arguments:
        value: The value that shall be converted into a Renderable.
        allow_string_literal: If string literals are allowed for constants.
    """
    if hasattr(value, 'render'):
        return value  # type: ignore[return-value]
    elif (isinstance(value, str) and allow_string_literal) or isinstance(value, (int, bool)):
        return Const(value)
    else:
        raise TypeError(f'Unable to convert value {value} into a renderable object.')


# Alias for backwards-compatibility
toRenderable = to_renderable  # noqa: N816


# Literal Values
class LiteralValue(OperationTrait):
    """Base class for literal values."""

    is_primitive: Final = False

    def __init__(self, value: Union[int, bool, str], width: Optional[int] = None) -> None:
        """Initialize a literal value wrapper.

        Arguments:
            value: The value of this literal value.
            width: Optional width in bits.
        """
        self._width: Optional[int] = width

        # Parse value and try to parse width
        if isinstance(value, str):
            value, parsed_width = parse_int(value)
        elif isinstance(value, bool):
            value, parsed_width = int(value), 1
        else:
            value, parsed_width = int(value), None

        # Check required width
        required_width = parsed_width if parsed_width is not None else ceil(log2(max(1, value)))
        if self.width is not None and required_width > self.width:
            raise ValueError(f'Unable to create {self.__class__}: Value {value} exceeds width with {required_width} > {self.width}.')

        self._value = value
        self._width = width if width is not None else parsed_width

    @property
    def value(self) -> int:
        """Value."""
        return self._value

    @property
    def width(self) -> Optional[int]:
        """Width in bits.

        A width of None means that the width is not fixed during execution of noRTL.
        """
        return self._width

    # Implement OperationTrait
    @property
    def operand_width(self) -> Optional[int]:
        """Indicates the width when used as an operand.

        A width of None means that the width is not fixed during execution of noRTL.
        """
        return self.width

    def read_access(self, ignore: Set[ACCESS_CHECKS] = set()) -> None:
        """Register read access from the current thread, state and construct depth.

        Does not invoke any checks for this object.
        """

    def render(self, target: Optional[str] = None) -> str:
        """Render constant value to target language.

        Arguments:
            target: Target language.
        """
        if self.width is not None:
            return f"{self.width}'h{self.value:0{ceil(self.width / 4)}X}"
        else:
            return f'{self.value}'


class Const(LiteralValue):
    """Constant value, representing an integer.

    Constants can optionally be initialized with a fixed width.
    This is relevant, when the constant is used within a [Concat][nortl.core.operations.Concat].

    Constants can be created from integers, bools, or parsed from strings.
    When parsing the value from a string in binary, octal or hexadecimal representation, the width can be automatically inferred.

    For hexadecimal numbers, the width will be a multiple of 4. For octal numbers, the width will be a multiple of 3.
    If the width argument is provided, it will override the inferred with.

    !!! note

        If you need to create constants with a fixed width, that is not a multiple of whole bytes, it is recommended to use binary representation.

    Examples:
        `Const('0b001')` will be parsed as value 1, width 3.

        `Const('0o70')` will be parsed as value 56, width 6.

        `Const('0x00')` will be parsed as value 0, width 8.

        `Const('0x00', 6)` will be parsed as value 0, width 6, due to explicit width. Alternatively, `Const(0, 6)` could be used.
    """

    is_constant: Final = True


class Var(LiteralValue):
    """Variable value, representing an integer.

    This class behaves similar to a [Const][nortl.core.operations.Const], but can be updated.
    This makes it useful to resize the width of signals.

    !!! danger

        Variables allow lazily determining the final value for a "constant" in the resulting Verilog code.
        Internally, they are used to define the width of the scratch pad signal for the [ScratchManager][nortl.core.manager.scratch_manager.ScratchManager], allowing the scratch manager to increase it over time.

        Variables can be used in all places, that accept Renderables, but must be used carefully.
        It is recommended to use a Variable only in a single place.
    """

    is_constant: Final = False

    def update(self, value: Union[int, str, bool]) -> None:
        """Update variable value."""
        # Parse value and try to parse width
        if isinstance(value, str):
            value, parsed_width = parse_int(value)
        elif isinstance(value, bool):
            value, parsed_width = int(value), 1
        else:
            value, parsed_width = int(value), None

        # Check required width
        required_width = parsed_width if parsed_width is not None else ceil(log2(max(1, value)))
        if self.width is not None and required_width > self.width:
            raise ValueError(f'Unable to update value: New value {value} exceeds variable width with {required_width} > {self.width}.')
        self._value = value


class RawText(OperationTrait):
    """Wrapper for raw text.

    !!! danger

        This class is meant for internal purposes. It will forward the raw text value to any rendering output.
        It can cause syntax errors or create risky code, if you refer to any signals (bypassing the access checker).
    """

    is_primitive: Final = True
    is_constant: Final = False

    def __init__(self, value: str) -> None:
        """Initialize a primitive value wrapper.

        Arguments:
            value: The value of this primitive value.
        """
        self.value = value

    # Implement OperationTrait
    @property
    def operand_width(self) -> Never:
        """Indicates the width when used as an operand."""
        raise AttributeError('Width attribute of RawText must not be processed as an operand.')

    def read_access(self, ignore: Set[ACCESS_CHECKS] = set()) -> None:
        """Register read access from the current thread, state and construct depth.

        Does not invoke any checks for this object.
        """

    def render(self, target: Optional[str] = None) -> str:
        """Render constant value to target language.

        Arguments:
            target: Target language.
        """
        return self.value


# Operation Wrappers
class BaseOperation(OperationTrait):
    """Base class for operations."""

    _renderer: RendererProto

    cache_enabled: ClassVar = True

    def __init__(self) -> None:
        super().__init__()
        self._cache: Dict[Optional[str], str] = {}

    @property
    @abstractmethod
    def operands(self) -> Sequence[Renderable]:
        """All operands of the operation."""

    # Implement OperationTrait
    def read_access(self, ignore: Set[ACCESS_CHECKS] = set()) -> None:
        """Register read access from the current thread, state and construct depth.

        Recursively registers an read access for all operands.
        """
        for operand in self.operands:
            operand.read_access(ignore=ignore)

        self._read = True

    def render(self, target: Optional[str] = None) -> str:
        """Render operation to target language.

        Arguments:
            target: Target language.
        """
        if self.cache_enabled and target not in self._cache:
            self._cache[target] = self._renderer(target)
        if not self.cache_enabled:
            self._cache = {}
            return self._renderer(target)

        return self._cache[target]


class SingleOperation(BaseOperation):
    """Operation wrapper for single-value operations.

    This object holds the value (can be an integer, signal name or another operation wrapper).
    It also instantiates a renderer that determines what specific kind of operation this represents.
    """

    is_primitive: Final = False
    is_constant: Final = False

    @classmethod
    def create_or_fold_operation(cls, value: Renderable, renderer: Type[SingleRenderer]) -> Renderable:
        """Either create a SingleOperation, or fold it into constant value.

        If the expression evaluates to a single integer, returns a Const.
        If the expression evaluates to a single Renderable, it is returned directly.
        """
        if (eval_result := renderer.eval(value)) is not None:
            if isinstance(eval_result, int):
                # Return a Const

                # For bitwise inversion or negation, the value can go negative.
                # It is treated like a unsigned integer, so must be overflowed.
                if eval_result < 0:
                    if value.operand_width is None:
                        # If the operand width is not determined at runtime, the overflow needs to happen in Verilog
                        return cls(value, renderer)
                    # Turn value positive
                    eval_result += 2**value.operand_width
                return Const(eval_result, width=value.operand_width)
            else:
                # Return the single Renderable returned by evaluation
                return eval_result
        else:
            return cls(value, renderer)

    def __init__(self, value: Union[Renderable, int, bool], renderer: Type[SingleRenderer]) -> None:
        """Initialize a single operation wrapper.

        Arguments:
            value: The value of this wrapper.
            renderer: Type of renderer to use. The renderer decides how the value is represented.
        """
        super().__init__()
        self._value = to_renderable(value)

        self._renderer = renderer(self)

    @property
    def value(self) -> Renderable:
        """Value to which the operation is applied."""
        return self._value

    @property
    def operands(self) -> Sequence[Renderable]:
        """All operands of the operation."""
        return (self.value,)

    # Implement OperationTrait
    @property
    def operand_width(self) -> Optional[int]:
        """Indicates the width when used as an operand, equal to the width of the input value.

        A width of None means that the width is not fixed during execution of noRTL.
        """
        return self.value.operand_width


class TwoSideOperation(BaseOperation):
    """Operation wrapper for operations based on two sides or values.

    This object holds the two values (can be integers, signal names or operation wrappers).
    It also instantiates a renderer that determines what specific kind of operation this represents.
    """

    is_primitive: Final = False
    is_constant: Final = False

    @classmethod
    def create_or_fold_operation(
        cls,
        left: Operand,
        right: Operand,
        renderer: Type[TwoSideRenderer],
        width: Optional[Union[int, Callable[[Renderable, Renderable], Optional[int]]]] = None,
    ) -> Renderable:
        """Either create a TwoSideOperation, or fold it into constant value.

        If the expression evaluates to a single integer, returns a Const.
        If the expression evaluates to a single Renderable, it is returned directly.
        """
        if (eval_result := renderer.eval(left, right)) is not None:
            if isinstance(eval_result, int):
                # Return a Const
                width = cls.determine_width(to_renderable(left), to_renderable(right), width)
                return Const(eval_result, width=width)
            else:
                # Return the single Renderable returned by evaluation
                return eval_result
        else:
            return cls(left, right, renderer, width=width)

    def __init__(
        self,
        left: Union[Renderable, int, bool],
        right: Union[Renderable, int, bool],
        renderer: Type[TwoSideRenderer],
        width: Optional[Union[int, Callable[[Renderable, Renderable], Optional[int]]]] = None,
    ) -> None:
        """Initialize a two-side operation wrapper.

        Arguments:
            left: The first of the two values.
            right: The second of the two values.
            renderer: Type of renderer to use. The renderer decides how the value is represented.
            width: Width of the operation result.
                Can be an integer, None, or a function that determines it from 2 Renderables.
        """
        super().__init__()
        self._left = to_renderable(left)
        self._right = to_renderable(right)

        self._renderer = renderer(self)
        self._operand_width = self.determine_width(self.left, self.right, width)

    @property
    def left(self) -> Renderable:
        """Left or first value for the operation."""
        return self._left

    @property
    def right(self) -> Renderable:
        """Right or second value for the operation."""
        return self._right

    @property
    def operands(self) -> Sequence[Renderable]:
        """All operands of the operation."""
        return (self.left, self.right)

    # Implement OperationTrait
    @property
    def operand_width(self) -> Optional[int]:
        """Indicates the width when used as an operand.

        A width of None means that the width is not fixed during execution of noRTL.
        """
        return self._operand_width

    @staticmethod
    def determine_width(
        left: Renderable, right: Renderable, width: Optional[Union[int, Callable[[Renderable, Renderable], Optional[int]]]]
    ) -> Optional[int]:
        """Determine width of operation, based on operands and optional explicit width."""
        if isinstance(width, int) or width is None:
            return width
        else:
            return width(left, right)


class SliceOperation(BaseOperation):
    """Operation wrapper for slicing operations.

    This object holds an values (can be an integer, signal name or operation wrapper) and an index.
    """

    is_primitive: Final = False
    is_constant: Final = False

    def __init__(self, value: Union[Renderable, int, bool], index: Union[int, slice], renderer: Type[SliceRenderer] = Slice) -> None:
        """Initialize a slicing operation wrapper.

        Arguments:
            value: The value of this wrapper.
            index: The slicing index. Can be a single integer or slice. Note that the stop value is inclusive, as it is in Verilog.
                   This differs from typical behavior in Python. The step size must be 1.
            renderer: Type of renderer to use. The renderer decides how the value is represented.
        """
        super().__init__()
        self._value = to_renderable(value)
        self._renderer = renderer(self)

        if isinstance(index, slice):
            if index.start is None:
                raise ValueError('Slice start must be defined.')
            elif index.stop is None:
                raise ValueError('Slice stop must be defined.')
            elif index.step is not None and index.step != 1:
                raise ValueError('Slice step size must be 1.')
            self._operand_width: int = max(index.start, index.stop) - min(index.start, index.stop) + 1
        else:
            self._operand_width = 1

        self._index = index

    @property
    def value(self) -> Renderable:
        """Value to which the operation is applied."""
        return self._value

    @property
    def operands(self) -> Sequence[Renderable]:
        """All operands of the operation."""
        return (self.value,)

    @property
    def index(self) -> Union[int, slice]:
        """Slicing index."""
        return self._index

    # Implement OperationTrait
    @property
    def operand_width(self) -> Optional[int]:
        """Indicates the width when used as an operand.

        A width of None means that the width is not fixed during execution of noRTL.
        """
        return self._operand_width


# Explicit Operations
class ExplicitOperation(Generic[T_Renderer], BaseOperation):
    """Baseclass for explicit operation classes."""

    is_primitive: Final = False

    @property
    @abstractmethod
    def _renderer_type(self) -> Type[T_Renderer]:
        """Class for renderer."""

    @property
    def is_constant(self) -> bool:
        """Indicates if this object has a constant value."""
        return self._is_constant

    def __init__(self) -> None:
        super().__init__()
        self._renderer: T_Renderer = self._renderer_type(self)
        self._is_constant = False


Part = Union[Renderable, str]


class SequenceOperation(ExplicitOperation[SequenceRenderer]):
    """Baseclass for operations taking a sequence of inputs."""

    @overload
    def __init__(self, arg: Generator[Part, None, None], /) -> None: ...

    @overload
    def __init__(self, arg: Part, /, *extra_args: Part) -> None: ...

    def __init__(self, arg: Union[Part, Generator[Part, None, None]], /, *extra_args: Part) -> None:
        """Initialize a sequence operation.

        Arguments:
            arg: First renderable item or generator expression.
            extra_args: More more renderable items.

        All arguments must have a fixed width. Supports constant values as string literals.
        """
        super().__init__()
        self._parts = self._extract_args(arg, extra_args)

        # Absorb operations of the same kind into one large operation
        self._unpack_sequence_operands()

    @property
    def parts(self) -> Sequence[Renderable]:
        """Parts of the sequence."""
        return self._parts

    @property
    def operands(self) -> Sequence[Renderable]:
        """All operands of the operation."""
        return self.parts

    # Helper methods
    @classmethod
    def _extract_args(cls, arg: Union[Part, Generator[Part, None, None]], extra_args: Sequence[Part]) -> Sequence[Renderable]:
        """Extract sequence of parts and convert to Renderables."""
        if isinstance(arg, GeneratorType):
            args: Iterable[Part] = arg
            if len(extra_args) > 0:
                raise ValueError(f'{cls.__name__} can either be created from a generator expression or multiple Renderables.')
        else:
            args = (arg, *extra_args)  # type: ignore[arg-type]

        return tuple(to_renderable(arg, allow_string_literal=True) for arg in args)

    def _unpack_sequence_operands(self) -> None:
        """Unpack sequence operands of the same kind."""
        new_parts: List[Renderable] = []
        operand_type = type(self)

        for part in self.parts:
            if isinstance(part, operand_type):
                new_parts.extend(part.parts)
            else:
                new_parts.append(part)

        self._parts = new_parts

    def _fold_constants(self) -> None:
        """Fold constants and short-circuit expressions.

        Subclasses can call this, after they have initialized the operand_width.
        Because the instance cannot be turned into a Const, its content is pruned and it is advertised as constant.
        """
        if (eval_result := self._renderer.eval(*self.parts)) is not None:
            if isinstance(eval_result, int):
                self._is_constant = True
                self._parts = (Const(eval_result, self.operand_width),)
            else:
                self._parts = (eval_result,)

    # Support unpacking of constants
    @property
    def value(self) -> int:
        """Value of content, if the object has a constant value."""
        if self.is_constant:
            return self.parts[0].value  # type: ignore[attr-defined, no-any-return]
        else:
            raise RuntimeError(f"Content of {self.__class__} is not constant. It's value must not be accessed.")


class Concat(SequenceOperation):
    """Concatenation expression.

    This class is used to model a concatenation of signals (or constants) in Verilog, e.g. `data = {arg2, arg1, arg0};`.

    The order of arguments passed into the Concat is translated as-is to Verilog.

    The concatenation supports constant values as strings, to simplify defining the width of constants.
    Instead of needing to write `Concat(Const('0b000'), ...)` you can use `Concat('0b000', ...)`.

    !!! example

        The following example:

        ```python
        response = engine.define_output('response', width=8)
        status = engine.define_local('status', width=3)

        # ...
        engine.set(response, Concat('0b0000', status, '0b0'))
        ```

        Will be translated as such:

        ```verilog
        module my_engine (
            // ...
            output logic [7:0] response
        );
        logic [2:0] status;

            // ... somewhere in the state machine
            response <= {4'b0000, status, 1'b0};
        ```
    """

    _renderer_type: Final = ConcatRenderer

    @overload
    def __init__(self, arg: Generator[Part, None, None], /) -> None: ...

    @overload
    def __init__(self, arg: Part, /, *extra_args: Part) -> None: ...

    def __init__(self, arg: Union[Part, Generator[Part, None, None]], /, *extra_args: Part) -> None:
        """Initialize a concatentation expression.

        Arguments:
            arg: First renderable item or generator expression.
            extra_args: More renderable items.

        All arguments must have a fixed width. Supports constant values as string literals.
        """
        super().__init__(arg, *extra_args)

        # Calculate and validate width
        self._operand_width: int = 0
        for part in self.parts:
            if part.operand_width is None:
                raise ValueError(f'Argument {part} for concatenation does not have a fixed width. This can lead to unpredictable results.')
            self._operand_width += part.operand_width

        # Fold constants
        self._fold_constants()

    # Implement OperationTrait
    @property
    def operand_width(self) -> int:
        """Indicates the width when used as an operand."""
        return self._operand_width


class IfThenElse(ExplicitOperation[TernaryRenderer]):
    """Ternary If-Then-Else expression.

    This class is used to model the `condition ? true_value : false_value` operator in Verilog.
    """

    _renderer_type: Final = IfThenElseRenderer

    def __init__(self, condition: Renderable, true_value: Operand, false_value: Operand) -> None:
        """Initialize a new If-Then-Else expression.

        Arguments:
            condition: Condition, selecting between `true_value` and `false_value`
            true_value: Operand that is selected if `cond` is True.
            false_value: Operand that is selected if `cond` is False.
        """
        super().__init__()
        self._condition = to_renderable(condition)
        self._true_value = to_renderable(true_value)
        self._false_value = to_renderable(false_value)

        # Validate widths and determine result width
        if (cond_width := self._condition.operand_width) != 1:
            raise ValueError(f'Condition for ternary expression has a width of {cond_width}. It should have a width of 1.')

        # Use larger of operand widths
        operand_width = -1
        if (true_width := self.true_value.operand_width) is not None:
            operand_width = max(operand_width, true_width)
        if (false_width := self.false_value.operand_width) is not None:
            operand_width = max(operand_width, false_width)
        self._operand_width = operand_width if operand_width > 0 else None

        # Fold constants
        self._fold_constants()

    @property
    def condition(self) -> Renderable:
        """Condition, selecting between `true_value` and `fals_value`."""
        return self._condition

    @property
    def true_value(self) -> Renderable:
        """Operand that is selected if `cond` is True."""
        return self._true_value

    @property
    def false_value(self) -> Renderable:
        """Operand that is selected if `cond` is False."""
        return self._false_value

    @property
    def operands(self) -> Sequence[Renderable]:
        """All operands of the operation."""
        return (self.condition, self.true_value, self.false_value)

    # Helper methods
    def _fold_constants(self) -> None:
        """Fold constants and short-circuit expressions.

        Because the instance cannot be turned into a Const, the two branches are set to the same value and it is advertised as constant.
        """
        if (eval_result := self._renderer.eval(self.condition, self.true_value, self.false_value)) is not None:
            self._condition = Const(True)  # Explicitely mark condition as True
            if isinstance(eval_result, int):
                # Constant value, mark entire operation as constant
                self._is_constant = True
                self._true_value = self._false_value = Const(eval_result, self.operand_width)
            else:
                # Single operand, set it for both branches
                self._true_value = self._false_value = eval_result

    # Implement OperationTrait
    @property
    def operand_width(self) -> Optional[int]:
        """Indicates the width when used as an operand.

        A width of None means that the width is not fixed during execution of noRTL.
        """
        return self._operand_width

    # Support unpacking of constants
    @property
    def value(self) -> int:
        """Value of content, if the object has a constant value."""
        if self.is_constant:
            return self.true_value.value  # type: ignore[attr-defined, no-any-return]
        else:
            raise RuntimeError(f"Content of {self.__class__} is not constant. It's value must not be accessed.")


class LogicalOperation(SequenceOperation):
    """Intermediate class for logical operations.

    These operations take a flexible number of inputs and result in a single-bit output.
    """

    @overload
    def __init__(self, arg: Generator[Part, None, None], /) -> None: ...

    @overload
    def __init__(self, arg: Part, /, *extra_args: Part) -> None: ...

    def __init__(self, arg: Union[Part, Generator[Part, None, None]], /, *extra_args: Part) -> None:
        """Initialize a logical operation.

        Arguments:
            arg: First renderable item or generator expression.
            extra_args: More renderable items.

        All arguments must have a fixed width. Supports constant values as string literals.
        """
        super().__init__(arg, *extra_args)

        # Validate width
        for part in self.operands:
            if part.operand_width != 1:
                raise ValueError(f'Argument {part} for logical operation does not have a fixed width of 1. This is not allowed.')

        # Fold constants
        self._fold_constants()

    # Implement OperationTrait
    @property
    def operand_width(self) -> Literal[1]:
        """Indicates the width when used as an operand."""
        return 1


class Any(LogicalOperation):
    """Any operation. Will be logic high, if any of the arguments is logic high.

    It will be rendered as a "Logical Or" (`||`) in Verilog.
    All arguments in the operation must have a fixed with of 1.

    The operation can be created from one or more Renderable arguments.
    It's also possible to directly pass in a generator expression.

    Examples:
        ```python
        Any(a, b, c)

        Any(signal > 0 for signal in signals)
        ```
    """

    _renderer_type: Final = AnyRenderer


class All(LogicalOperation):
    """All operation. Will be logic high, if all of the arguments is logic high.

    It will be rendered as a "Logical And" (`&&`) in Verilog.
    All arguments in the operation must have a fixed with of 1.

    The operation can be created from one or more Renderable arguments.
    It's also possible to directly pass in a generator expression.

    Examples:
        ```python
        All(a, b, c)

        All(signal > 0 for signal in signals)
        ```
    """

    _renderer_type: Final = AllRenderer
