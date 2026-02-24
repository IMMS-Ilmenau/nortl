"""Re-usable state segments."""

from contextlib import contextmanager
from functools import partial, update_wrapper
from inspect import BoundArguments, Signature, signature
from math import ceil, log2
from typing import (
    Any,
    Callable,
    ClassVar,
    Concatenate,
    Dict,
    Iterator,
    List,
    Mapping,
    Optional,
    Protocol,
    Self,
    Sequence,
    Tuple,
    Union,
    overload,
)

from nortl.core.constructs.utils import FastForwarder
from nortl.core.modifiers import BaseModifier, WeakReference
from nortl.core.operations import Const, Var, to_renderable
from nortl.core.protocols import (
    AnySignal,
    EngineProto,
    MemoryViewProto,
    MemoryZoneProto,
    PermanentSignal,
    Renderable,
    ScratchSignalProto,
    SignalProto,
    StateProto,
    WorkerProto,
)
from nortl.core.signal import ScratchSignal, Signal, SignalSlice

__all__ = [
    'Segment',
]


class HelperProto(Protocol):
    @property
    def engine(self) -> EngineProto: ...


class Ignore:
    """Marker for ignored call arguments."""

    _inst: ClassVar['Ignore']

    def __new__(cls) -> 'Ignore':
        if not hasattr(cls, '_inst'):
            cls._inst = object.__new__(cls)
        return cls._inst

    def __repr__(self) -> str:
        return '...'


class RenderedSegment:
    """Helper class to store information about a rendered Segment for a specific call signature and worker."""

    def __init__(
        self,
        start_state: StateProto,
        end_state: StateProto,
        input_slots: Mapping[str, ScratchSignalProto],
        output_slot_widths: Sequence[Optional[int]],
        result: object,
        memory_view: MemoryViewProto,
    ) -> None:
        self.start_state = start_state
        self.end_state = end_state
        self.input_slots = input_slots
        self.output_slot_widths = output_slot_widths
        self.result: object = result
        self.memory_view = memory_view
        self.calls: List[Tuple[StateProto, StateProto, Sequence[WeakReference[SignalProto]]]] = []


class EngineContext:
    """Helper class to store information about all segments for a specific engine."""

    def __init__(self, engine: EngineProto) -> None:
        self.engine = engine
        self.return_addresses: Dict[WorkerProto, SignalProto] = {}
        self._segments: List[SegmentImplementation[Any, Any, Any]] = []

    @property
    def current_worker(self) -> WorkerProto:
        """Selected worker."""
        return self.engine.current_worker

    @property
    def return_address(self) -> SignalProto:
        """Return address for current worker."""
        return self.return_addresses[self.current_worker]

    def get_return_address(self, min_calls: int) -> SignalProto:
        """Get signal that stores the return address for the current worker.

        Expands the signal if needed, to fit the minimum number of calls.
        """
        min_width = max(1, ceil(log2(min_calls)))

        if self.current_worker not in self.return_addresses:
            # Create new return address
            name = self.current_worker.create_scoped_name('RETURN_ADDRESS')
            return_address = self.engine.define_local(name, width=Var(min_width), reset_value=0)

            self.return_addresses[self.current_worker] = return_address
        else:
            # Get signal that stores the return address
            return_address = self.return_addresses[self.current_worker]

            # Resize it to support the number of calls for this level, if necessary
            width: Var = return_address.width  # type: ignore[assignment]
            if width.value < min_width:
                width.update(min_width)
        return return_address

    def register_segment[T: Union[EngineProto, HelperProto], **P, R: Optional[Union[AnySignal, Sequence[AnySignal]]]](
        self, segment: 'SegmentImplementation[T, P, R]'
    ) -> None:
        """Register a segment, if it isn't registered yet. All segments belonging to a worker are tracked for debugging."""
        if segment not in self._segments:
            self._segments.append(segment)

    @property
    def segments(self) -> Sequence['SegmentImplementation[Any, Any, Any]']:
        """Sequence of all segments."""
        return self._segments


SlotSize = Union[int, str, bool]


class SlotSpec:
    """Specification for input and output slots."""

    def __init__(self, width: SlotSize) -> None:
        self.width = width

    def __format__(self, format_spec: str) -> str:
        if isinstance(self.width, bool):
            if self.width:
                return 'Automatic detection based on the operand width of the first argument passed into the slot.'
            else:
                return 'Disabled.'
        elif isinstance(self.width, int):
            return f'Fixed width of {self.width} Bit.'
        else:
            return f'Parametric width based on the value of argument {self.width}'

    def __repr__(self) -> str:
        return f'<SlotSpec (width={self.width})>'


class InputCheck:
    """Input check callback."""

    def __init__(self, callback: Callable[[BoundArguments], bool], description: str):
        self.callback = callback
        self.description = description

    def __call__(self, bound_arguments: BoundArguments) -> bool:
        return self.callback(bound_arguments)

    @classmethod
    def from_validator[**P](cls, validator: Callable[P, bool]) -> Self:
        """Create input check from validator callback."""

        def callback(bound_arguments: BoundArguments) -> bool:
            return validator(*bound_arguments.args[1:], **bound_arguments.kwargs)

        return cls(callback, f'Validator callback {validator.__name__}({", ".join(signature(validator).parameters.keys())})')

    @classmethod
    def for_argument[T](cls, name: str, check: Callable[[T], bool]) -> Self:
        """Create input check for a single argument."""

        def callback(bound_arguments: BoundArguments) -> bool:
            value = bound_arguments.arguments[name]
            return check(value)

        return cls(callback, f'Validation for {name}')


class semistaticmethod[T, **P, R]:  # noqa: N801
    """Turns method into a semi-static method.

    It will allow calls both as a instance method, but also as a static method of the class. In the later case, the self-argument will be None.
    """

    def __init__(self, method: Callable[Concatenate[T, P], R]):
        self.__method = method

    def __get__(self, obj: Optional[T], objtype: Optional[type] = None) -> Union[Self, Callable[P, R]]:
        # Non-data descriptor, this allows the decorator to be used on class methods
        if obj is None:
            return self
        else:
            return partial(self.__method, obj)

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
        return partial(self.__method, None)(*args, **kwargs)  # type: ignore[arg-type]


class SegmentFactoryMixin:
    """Helper class to create segments with non-default configuration.

    This is used by both the Segment class itself and the SegmentFactory.
    """

    @semistaticmethod
    def with_input_slots(self, **input_slots: SlotSize) -> 'SegmentFactory':
        """Creates a segment with input slots for the selected inputs.

        Input slots are scratch signals, to which the input arguments are copied, before calling the segment.
        They help, if the same segment is meant to be re-used for many different inputs, without explicitely defining a global signal for the input.

        Arguments:
            input_slots: Keywords mapping the argument names of the decorated function or method to slot sizes.

        Slot sizes can be specified with the following options:

        - If the slot is an integer value, it specifies the width of the input slot in bits.
        - If the slot size is a string, it refers to another argument of the decorated function or method.
            The slot size is set to the value of this argument, when called. This allows defining parametric segments.
        - If the slot size is `True`, the slot size will be automatically determined, when it the segment is called for the first time.
            The input value needs to have an fixed `operand_width`, for this to work.
        - If the slot size is `False`, no slot is added. This is redundant, as no slot is added by default.

        It is recommended to avoid using a slot size of `True`, as the automatic detection will fail, if passing in any dynamic data.

        Example:
            The following example defines an segment with an input argument `data`. A slot with a fixed size of 8 bit is added.

            ```python
            from nortl import Engine, Segment, to_renderable

            # Define signals
            engine = Engine('my_engine')
            output = engine.define_output('output', width=1)

            @Segment.with_input_slots(data=8)
            def send_byte(engine: EngineProto, data: Union[Renderable, int]) -> None:
                data = to_renderable(data)

                for i in range(8):
                    engine.set(output, data[i])
                    engine.sync()
            ```

            Note how the decorated function deserializes the data in a for-loop. The length is currently fixed to 8.

            If the segment should accept dynamic lengths of data, a `width` argument can be added.
            Now, the width of the input slot for `data` needs to match it.
            This is achieved by setting the slot size to `'width'`:

            ```python
            # ...

            @Segment.with_input_slots(data='width')
            def send_dynamic(engine: EngineProto, data: Union[Renderable, int], width: int) -> None:
                data = to_renderable(data)

                for i in range(width):
                    engine.set(output, data[i])
                    engine.sync()
            ```

        Input slots are located inside the memory zone of a segment.
        """
        return SegmentFactory(
            input_checks=getattr(self, '_SegmentFactory__input_checks', (None, {})),
            input_slots=input_slots,
            output_slots=getattr(self, '_SegmentFactory__output_slots', ()),
        )

    @semistaticmethod
    def with_output_slots(self, *output_slots: SlotSize) -> 'SegmentFactory':
        """Creates a segment with output slots for the selected outputs.

        Output slots are scratch signals, to which the result(s) are copied.
        By default, any signals returned from segments point to the same register and are therefore read-only.
        If an output slot is added, the result will be copied into a scratch signal for each call.

        Arguments:
            output_slots: Slot sizes for the output values, in the same order as they are returned.

        Slot sizes can be specified with the following options:

        - If the slot is an integer value, it specifies the width of the output slot in bits.
        - If the slot size is a string, it refers to an argument of the decorated function or method.
            The slot size is set to the value of this argument, when called. This allows defining parametric segments.
        - If the slot size is `True`, the slot size will be automatically determined, when it the segment is called for the first time.
            The result needs to have an fixed `operand_width`, for this to work.
        - If the slot size is `False`, no slot is added. This is redundant, as no slot is added by default.

        It is recommended to avoid using a slot size of `True`, as the automatic detection will fail, if passing in any dynamic data.

        Output slots are located inside the memory zone of the caller.
        """
        return SegmentFactory(
            input_checks=getattr(self, '_SegmentFactory__input_checks', (None, {})),
            input_slots=getattr(self, '_SegmentFactory__input_slots', {}),
            output_slots=output_slots,
        )

    @semistaticmethod
    def with_input_checks[**P](self, input_validator: Optional[Callable[P, bool]] = None, /, **input_checks: Callable[..., bool]) -> 'SegmentFactory':
        """Creates a segment with input checks.

        Input checks are callback functions the validate the arguments passed to a segment.

        If a segment uses input slots, the arguments with input slots can no longer be validated inside the function or methods body, because it will not be called
        for different inputs. Input checks solve the issue.

        Arguments:
            input_validator: A validator callback, that accepts all arguments and keyword arguments of the decorated function or method.
                It doesn't require the self attribute. The validator callback may either return a boolean result, where True means that all arguments
                passed validation. Or it may directly raise an exception.
                As the validator callback receives all arguments at the same time, it can be used for "global" checks.
            input_checks: Keywords mapping the argument names of the decorated function or method to individual validators, e.g. created by lambda
                functions.
                The input checks receives only one argument at a time, so they cannot be used for "global" checks.
                However, they can be written "in-line", by using lambda functions.


        Examples:
            The following segment can send dynamic amounts of data, without using a ForLoop construct. However, only up to 31 bits are supported at a time.
            To validate that the length never exceeds 31, a validator callback is added.

            ```python
            from nortl import Engine, Segment, to_renderable

            # Define signals
            engine = Engine('my_engine')
            output = engine.define_output('output', width=1)

            def validate_length(data: int, length: int = 16) -> bool:
                return length < 32

            @Segment.with_input_slots(data=8, length=5).with_input_checks(validate_length)
            def send_dynamic(engine: EngineProto, data: Union[Renderable, int], length: Union[Renderable, int] = 16) -> None:
                data = to_renderable(data)

                end_state = engine.create_state()

                # Unrolled loop
                for i in range(32):
                    engine.set(output, data[i])
                    if i < 31:
                        engine.jump_if(length == (i + 1), end_state, engine.next_state)  # type: ignore[arg-type]
                        engine.current_state = engine.next_state
                    else:
                        engine.jump_if(Const(1), end_state)
                engine.current_state = end_state
            ```

            As an alternative to defining the `validate_length` function, a single lambda function can be used:

            ```python
            # ...
            @Segment.with_input_slots(data=8, length=5).with_input_checks(length=lambda x: x < 32)
            def send_dynamic(engine: EngineProto, data: Union[Renderable, int], length: Union[Renderable, int] = 16) -> None:
                # ...
            ```
        """
        return SegmentFactory(
            input_checks=(input_validator, input_checks),
            input_slots=getattr(self, '_SegmentFactory__input_slots', {}),
            output_slots=getattr(self, '_SegmentFactory__output_slots', ()),
        )


class SegmentFactory(SegmentFactoryMixin):
    __slots__ = [
        '__input_checks',
        '__input_slots',
        '__output_slots',
    ]

    def __init__(
        self,
        input_checks: Tuple[Optional[Callable[..., bool]], Mapping[str, Callable[..., bool]]] = (None, {}),
        input_slots: Mapping[str, SlotSize] = {},
        output_slots: Sequence[SlotSize] = (),
    ) -> None:
        self.__input_checks = input_checks
        self.__input_slots = input_slots
        self.__output_slots = output_slots

    def __call__[T: Union[EngineProto, HelperProto], **P, R: Optional[Union[AnySignal, Sequence[AnySignal]]]](
        self, method: Callable[Concatenate[T, P], R]
    ) -> 'Segment[T, P, R]':
        return Segment(method, input_checks=self.__input_checks, input_slots=self.__input_slots, output_slots=self.__output_slots)


class Segment[T: Union[EngineProto, HelperProto], **P, R: Optional[Union[AnySignal, Sequence[AnySignal]]]](SegmentFactoryMixin):
    """Decorates a function or method as a segment.

    This decorator must either be applied to one of these options:

    1. The method of a noRTL engine.
    2. A function receiving the engine as it's argument.
    3. The method of a helper class having a noRTL engine as it's attribute `engine`.

    The method may receive input arguments. The segment will be re-created for every call with different arguments by default.

    It is possible to automatically copy all or selected inputs into the segment.
    This must be enabled by using a [@Segment.with_input_slots()][nortl.core.constructs.segment.Segment.with_input_slots] decorator.
    In this case, different inputs for the copied signals are ignored.

    Note that the method must not access any Python variables that change over time.

    Effectively, the body of the segment will be executed only once for each different call signature, to define the segment of states.
    Afterwards, the engine will add transitions to the start of the segment, and back from its end, while remembering the return address.

    Examples:
        Decorate a method of an custom engine:

        ```python
        from nortl import Engine, Segment

        class MyEngine(Engine):
            # ...

            @Segment
            def send_data(self) -> None:
                self.set(self.OUTPUT, self.INPUT)
                self.sync()

            def build(self) -> None:
                # The segment can be called as usual
                self.send_data()

                # Multiple invocations of the segment will re-use the same part (segment) of the state machine.
                self.send_data()
        ```

        Decorate a function:

        ```python
        from nortl import Engine, Segment

        engine = Engine()
        # ...

        @Segment
        def send_data(engine) -> None:
            engine.sync()
        ```

        Decorate a method of a helper class:

        ```python
        from nortl import Segment
        from nortl.core.protocols import EngineProto

        class Command:
            def __init__(self, engine: EngineProto) -> None:
                self.engine = engine

            @Segment
            def send_data(self) -> None:
                self.engine.set(self.OUTPUT, self.INPUT)
                self.engine.sync()
        ```
    """

    DEBUG_PRINT: ClassVar[bool] = False
    """Enable debug prints."""

    _engine_contexts: ClassVar[Dict[EngineProto, EngineContext]] = {}

    def __init__(
        self,
        method: Callable[Concatenate[T, P], R],
        input_slots: Mapping[str, SlotSize] = {},
        output_slots: Sequence[SlotSize] = (),
        input_checks: Tuple[Optional[Callable[P, bool]], Mapping[str, Callable[[object], bool]]] = (None, {}),
    ):
        self.__method = method
        self.__signature = signature(method)
        self.__bindings: Dict[T, Union[SegmentImplementation[T, P, R], BoundSegment[T, P, R]]] = {}
        self._input_slot_specs: Mapping[str, SlotSpec] = self._create_input_slot_specs(input_slots)
        self._output_slot_specs: Sequence[SlotSpec] = self._create_output_slot_specs(output_slots)
        self._input_checks: Sequence[InputCheck] = self._create_input_checks(*input_checks)

    def _create_input_slot_specs(self, input_slots: Mapping[str, SlotSize]) -> Mapping[str, SlotSpec]:
        """Create input slot specifications."""
        input_slot_specs = {}
        for name, width in input_slots.items():
            if name not in self.__signature.parameters:
                raise KeyError(f'{name} is not a valid argument name of the decorated function or method.')

            if isinstance(width, str):
                # Copy width from other input value
                if width not in self.__signature.parameters:
                    raise ValueError(
                        f'{width} is not a valid argument name of the decorated function or method.'
                        f'It is specified to determine the width for the input slot of argument {name}.'
                    )
            elif isinstance(width, bool) and not width:
                continue  # skip False slots
            elif isinstance(width, int):
                pass
            else:
                raise TypeError(f'Width specifier {width} for input slot of argument {name} is not of a valid type.')

            input_slot_specs[name] = SlotSpec(width)
        return input_slot_specs

    def _create_output_slot_specs(self, output_slots: Sequence[SlotSize]) -> Sequence[SlotSpec]:
        """Create output slot specifications."""
        output_slot_specs: List[SlotSpec] = []

        for pos, width in enumerate(output_slots):
            if isinstance(width, str):
                # Copy width from input value
                if width not in self.__signature.parameters:
                    raise ValueError(
                        f'{width} is not a valid argument name of the decorated function or method.'
                        f'It is specified to determine the width for the output slot at position {pos}.'
                    )
                elif (input_slot_spec := self._input_slot_specs.get(width, None)) is not None:
                    width = input_slot_spec.width  # Copy input slot specifier
            elif isinstance(width, bool) and not width:
                continue  # skip False slots
            elif isinstance(width, int):
                pass
            else:
                raise TypeError(f'Width specifier {width} for output slot at position {pos} is not of a valid type.')

            output_slot_specs.append(SlotSpec(width))

        return output_slot_specs

    def _create_input_checks(
        self, input_validator: Optional[Callable[P, bool]], input_checks: Mapping[str, Callable[..., bool]]
    ) -> Sequence[InputCheck]:
        """Create input checks."""
        callbacks: List[InputCheck] = []
        if input_validator is not None:
            callbacks.append(InputCheck.from_validator(input_validator))

        for name, callback in input_checks.items():
            callbacks.append(InputCheck.for_argument(name, callback))
        return callbacks

    # Public methods
    def __call__(self, engine: T, *args: P.args, **kwargs: P.kwargs) -> R:
        """Calls the decorated function as a segment."""
        __tracebackhide__ = True

        if engine not in self.__bindings:
            method = update_wrapper(partial(self.__method, engine), self.__method)
            self.__bindings[engine] = SegmentImplementation(self, engine, method)

        return self.__bindings[engine](*args, **kwargs)

    def inline(self, engine: T, *args: P.args, **kwargs: P.kwargs) -> R:
        """Calls the decorated function as an inlined function."""
        __tracebackhide__ = True
        return self.__method(engine, *args, **kwargs)

    @overload
    def __get__(self, obj: T, objtype: Optional[type] = ...) -> 'BoundSegment[T, P, R]': ...
    @overload
    def __get__(self, obj: None, objtype: None = ...) -> Self: ...

    def __get__(self, obj: Optional[T], objtype: Optional[type] = None) -> Union[Self, 'BoundSegment[T, P, R]']:
        # Non-data descriptor, this allows the decorator to be used on class methods
        if obj is None:
            return self
        else:
            if obj not in self.__bindings:
                self.__bindings[obj] = BoundSegment(self, obj, self.__method)
            return self.__bindings[obj]  # type: ignore[return-value]

    # Utilities
    @staticmethod
    def get_engine_context(engine: EngineProto) -> 'EngineContext':
        """Get the engine context for a specific engine.

        The engine context holds an overview of all segments.
        """
        if engine not in Segment._engine_contexts:
            Segment._engine_contexts[engine] = EngineContext(engine)
        return Segment._engine_contexts[engine]


class BoundSegment[T: Union[EngineProto, HelperProto], **P, R: Optional[Union[AnySignal, Sequence[AnySignal]]]]:
    """Segment bound to a method of an object."""

    def __init__(self, segment: Segment[T, P, R], obj: T, method: Callable[Concatenate[T, P], R]) -> None:
        self.__segment: Segment[T, P, R] = segment
        self.__obj: T = obj
        self.__method: Callable[P, R] = update_wrapper(partial(method, obj), method)
        self.__implementation: SegmentImplementation[T, P, R] = SegmentImplementation(segment, obj, self.__method, is_partial=True)

    # Mimic attributes of function segment
    @property
    def _input_slot_specs(self) -> Mapping[str, SlotSpec]:
        return self.__segment._input_slot_specs

    @property
    def _output_slot_specs(self) -> Sequence[SlotSpec]:
        return self.__segment._output_slot_specs

    @property
    def _input_checks(self) -> Sequence[InputCheck]:
        return self.__segment._input_checks

    # Public methods
    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
        """Calls the decorated method as a segment."""
        __tracebackhide__ = True
        return self.__implementation(*args, **kwargs)

    def inline(self, *args: P.args, **kwargs: P.kwargs) -> R:
        """Calls the decorated method as an inlined function."""
        __tracebackhide__ = True
        return self.__method(*args, **kwargs)


class SegmentImplementation[T: Union[EngineProto, HelperProto], **P, R: Optional[Union[AnySignal, Sequence[AnySignal]]]]:
    def __init__(self, segment: Union[Segment[T, P, R], BoundSegment[T, P, R]], engine: T, method: Callable[P, R], is_partial: bool = False) -> None:
        self.segment: Union[Segment[T, P, R], BoundSegment[T, P, R]] = segment
        self.engine: EngineProto = self._unpack_engine(engine)
        self.method: Callable[P, R] = method
        self.signature: Signature = signature(method)
        self.is_partial = is_partial

        # Get engine context
        self.engine_context = Segment.get_engine_context(self.engine)
        self._memory_zone: Optional[MemoryZoneProto] = None
        self.backup_addresses: Dict[WorkerProto, SignalProto] = {}
        self.rendered_segments: Dict[Tuple[WorkerProto, str], RenderedSegment] = {}
        self._active_key: Optional[Tuple[WorkerProto, str]] = None

    def _unpack_engine(self, obj: T) -> EngineProto:
        """Unpack engine from helper class instance object."""
        if hasattr(obj, 'engine'):
            return obj.engine
        else:
            return obj  # type: ignore

    @property
    def input_slot_specs(self) -> Mapping[str, SlotSpec]:
        return self.segment._input_slot_specs

    @property
    def output_slot_specs(self) -> Sequence[SlotSpec]:
        return self.segment._output_slot_specs

    @property
    def input_checks(self) -> Sequence[InputCheck]:
        return self.segment._input_checks

    # Call
    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
        __tracebackhide__ = True

        # Check inputs
        self.check_inputs(args, kwargs)

        if Segment.DEBUG_PRINT:
            self.engine.print(f'Calling {self.format_call(args, kwargs)}')

        with self.select_active_key(self.engine.current_worker, self.extract_signature(*args, **kwargs)) as key:
            try:
                # Check if segment with signature exists for the current worker and if not, render it
                if key not in self.rendered_segments:
                    self.render_segment(*args, **kwargs)

                # Then, call the segment
                return self.call_segment(*args, **kwargs)
            except Exception as e:
                e.add_note(f'This exception occured while calling segment {self.format_call(args, kwargs)} in {self.method.__module__}')
                raise

    # Selection of rendered segment
    @contextmanager
    def select_active_key(self, worker: WorkerProto, signature: str) -> Iterator[Tuple[WorkerProto, str]]:
        """Select active key, based on the worker and the call signature.

        The Segment will create individual rendered segments for each key.
        """
        __tracebackhide__ = True

        if self._active_key is not None:
            raise RuntimeError(f'Detected recursive call of Segment {self.method.__name__} in {self.method.__module__}. This is not supported.')

        self._active_key = key = worker, signature
        yield key
        self._active_key = None

    @property
    def active_key(self) -> Tuple[WorkerProto, str]:
        """Active key, based on the worker and the call signature."""
        if self._active_key is None:
            raise RuntimeError('Segment has no active rendered segment.')
        return self._active_key

    @property
    def active_rendered_segment(self) -> RenderedSegment:
        """Rendered segment for active key."""
        return self.rendered_segments[self.active_key]

    @active_rendered_segment.setter
    def active_rendered_segment(self, value: RenderedSegment) -> None:
        """Rendered segment for active key."""
        self.rendered_segments[self.active_key] = value

    # Check inputs
    def check_inputs[A: Sequence[object], B: Mapping[str, object]](self, args: A, kwargs: B) -> None:
        """Check inputs."""
        bound_arguments = self.bind_arguments(args=args, kwargs=kwargs)

        failed_checks: List[InputCheck] = []
        try:
            for check in self.input_checks:
                if not check(bound_arguments):
                    failed_checks.append(check)
        except Exception as e:
            raise ValueError(
                f'Failed calling segment {self.format_call(args, kwargs)}.\nInput check {check.description} raised an exception (see above).'
            ) from e

        if failed_checks:
            raise ValueError(
                f'Failed calling segment {self.format_call(args, kwargs)}.\nThe following input check(s) returned False:\n'
                + '\n'.join(f'{i + 1}. {check.description}' for i, check in enumerate(failed_checks))
            )

    # Render/call of segment
    def render_segment(self, *args: P.args, **kwargs: P.kwargs) -> None:
        """Render new segment into the noRTL engine."""

        # Save state from where the segment will be called, before adding the segment
        call_state = self.engine.current_state

        # Enter new memory zone of scratch manager
        # The input slots must be located inside the memory zone
        with self.memory_zone as memory_view:
            # Replace input arguments that need to be copied with "slot" signals
            input_slots, args, kwargs = self.add_input_slots(args, kwargs)

            # Create floating state, the transition(s) to it are added by _call_segment
            start_state = self.engine.current_state = self.engine.next_state

            # Call the decorated method to render it into the segment
            result = self.method(*args, **kwargs)

        # Prepare output slots and check if the result is safe
        output_slot_widths = self.prepare_output_slots(args, kwargs, result)

        # Save the rendered segment
        self.active_rendered_segment = RenderedSegment(
            start_state=start_state,
            end_state=self.engine.current_state,
            input_slots=input_slots,
            output_slot_widths=output_slot_widths,
            result=result,
            memory_view=memory_view,
        )

        # Return to the call state
        self.engine.current_state = call_state

        # Register the segment (once)
        self.engine_context.register_segment(self)

    def call_segment(self, *args: P.args, **kwargs: P.kwargs) -> R:
        """Call segment."""

        rendered_segment = self.active_rendered_segment

        # Generate new call ID and save it to return address
        # Call IDs are unique for each rendered segment, regardless of the call depth
        call_id = len(rendered_segment.calls)
        return_address = self.engine_context.get_return_address(min_calls=call_id + 1)
        self.push_return_address(return_address, call_id)

        # Copy the selected inputs into the input slots of the segment
        self.copy_inputs_in(args, kwargs)

        # Create output slots
        # The slot signals must be defined outside of the memory zone for the segment
        output_slots = self.create_output_slots(rendered_segment.output_slot_widths)

        # Add transition to segment
        self.engine.jump_if(Const(1), rendered_segment.start_state)

        # Expire all previous results
        for _, _, weak_references in rendered_segment.calls:
            for ref in weak_references:
                ref.expire()

        call_state = self.engine.current_state

        # Add new transition from end state for this call to return state (or the copy-out state)
        self.engine.current_state = rendered_segment.end_state
        self.engine.jump_if(return_address == call_id, self.engine.next_state)

        # Copy the selected results out of the segment and write-protect signals that are not copied
        # This will insert a sync if necessary
        result, weak_references = self.copy_result_out(rendered_segment.result, output_slots, return_address, call_id)  # type: ignore[arg-type]

        # Restore old return address
        self.engine.set(return_address, self.backup_address)

        # Switch to return state and save the calls start and return state (for debugging)
        return_state = self.engine.current_state
        rendered_segment.calls.append((call_state, return_state, weak_references))

        return result

    # Return address
    def push_return_address(self, return_address: SignalProto, call_id: int) -> None:
        """Push new call ID to return address while backing up the previous return address.

        If two calls are chained directly after each other, the assignments to the return address is changed.
        """
        # Find if the return address is already assigned in the current state
        # This happens, if two segment calls start directly after each other
        for assignment in self.engine.current_state.get_assignments(return_address):
            if not assignment.unconditional:
                raise RuntimeError(f'Return address {return_address.name} was used in a conditional assignment, indicating that it was tampered with')

            # If an assignment is found, the value will be replaced with the call ID.
            # The restored backup address is pushed to the own backup address instead. If it already belongs to the same segment, this is not needed.
            if assignment.value is not self.backup_address:
                self.engine.set(self.backup_address, assignment.value)
            assignment.value = to_renderable(call_id)
            return

        # If no assignment was found, save the call ID in the return address as usual
        self.engine.set(return_address, call_id)
        self.engine.set(self.backup_address, return_address)

    def get_fast_forward_return_address(self, return_address: SignalProto) -> SignalProto:
        """Get the return address signal for fast-forwarding copy-out."""
        # Find if the return address is already assigned in the current state
        # This happens, if two segment calls end directly after each other
        for assignment in self.engine.current_state.get_assignments(return_address):
            if not assignment.unconditional:
                raise RuntimeError(f'Return address {return_address.name} was used in a conditional assignment, indicating that it was tampered with')

            return assignment.value  # type: ignore[return-value]
        # If no assignment was found, use the return address directly
        return return_address

    # Input and output slots
    def add_input_slots[A: Sequence[object], B: Mapping[str, object]](self, args: A, kwargs: B) -> Tuple[Mapping[str, ScratchSignalProto], A, B]:
        """Add slot signals for input signals that need to be copied and replace them in the arguments."""
        new_arguments: Dict[str, object] = {}
        slot_signals: Dict[str, ScratchSignalProto] = {}

        bound_arguments = self.bind_arguments(args=args, kwargs=kwargs)
        for name, input_value in self.iter_bound_arguments(args=args, kwargs=kwargs):
            if (slot_spec := self.input_slot_specs.get(name, None)) is not None:
                # Determine width of input slot
                if isinstance(slot_spec.width, str):
                    # Dynamic width based on other input argument
                    width = bound_arguments.arguments[slot_spec.width]
                elif not isinstance(slot_spec.width, bool):
                    # Fixed integer width
                    width = slot_spec.width
                elif slot_spec.width and hasattr(input_value, 'operand_width') and input_value.operand_width is not None:
                    # Copy operand width
                    width = input_value.operand_width
                else:
                    raise ValueError(
                        f'Unable to determine the width of the input slot for argument {name}. The value {input_value} for this argument has no fixed operand_width.\n'
                        f'The slot has the following specification: {slot_spec}\n'
                    )
                new_arguments[name] = slot_signals[name] = self.engine.define_scratch(width)

            else:
                new_arguments[name] = input_value

        bound_arguments = self.signature.bind(**new_arguments)
        return slot_signals, bound_arguments.args[1:], bound_arguments.kwargs  # type: ignore[return-value]

    def copy_inputs_in[A: Sequence[object], B: Mapping[str, object]](self, args: A, kwargs: B) -> None:
        """Copy signals into the segment."""

        # Process the input values to check if they have been assigned in the current state
        # If possible, fast-forwards the values
        fast_forwarder = FastForwarder(self.engine)
        inputs: Dict[ScratchSignalProto, Renderable] = {}
        fast_forward_inputs: Dict[ScratchSignalProto, Renderable] = {}
        for name, input_value in self.iter_bound_arguments(args=args, kwargs=kwargs):
            if (input_slot := self.active_rendered_segment.input_slots.get(name, None)) is not None:
                # Attempt to convert value into renderable and check its width
                input_value = to_renderable(input_value)  # type: ignore[call-overload]
                if input_value.operand_width is not None and input_value.operand_width > (input_slot_width := input_slot.operand_width):
                    raise ValueError(
                        f'Width of input value {input_value} for argument {name} exceeds width of the input slot with '
                        f'{input_value.operand_width} vs. {input_slot_width} Bit.'
                    )
                inputs[input_slot] = input_value

                # Attempt to fast forward the value
                if (fast_forward_value := fast_forwarder(input_value)) is not None:
                    fast_forward_inputs[input_slot] = fast_forward_value

        # Add sync if needed
        if fast_forwarder.needs_sync:
            self.engine.sync()
            fast_forward_inputs = {}  # Discard all fast-forward inputs, if a sync is needed anyways

        # Recover memory view to re-enable access to the input slots and assign the input values
        with self.recover_memory_zone():
            for input_slot, input_value in inputs.items():
                input_slot.reclaim()
                self.engine.set(input_slot, fast_forward_inputs.get(input_slot, input_value))

    def prepare_output_slots[A: Sequence[object], B: Mapping[str, object]](self, args: A, kwargs: B, result: R) -> Sequence[Optional[int]]:
        """Prepare slot signals for output signals that need to be copied and return widths of the slots."""
        if result is None:
            return []

        # Pack results into iterable
        if hasattr(result, '__iter__'):
            results: Sequence[AnySignal] = result  # type: ignore
        else:
            results = (result,)  # type: ignore

        bound_arguments = self.bind_arguments(args=args, kwargs=kwargs)
        widths: List[Optional[int]] = []
        for pos, signal in enumerate(results):
            # Unwrap content of modifier
            if isinstance(signal, BaseModifier):
                signal = signal.content

            if not isinstance(signal, (Signal, SignalSlice, ScratchSignal)):
                raise TypeError(
                    f'Results of a method decorated with @Segment must be signals, got: {signal}\n'
                    'Returning any other object may lead to broken code and is therefore forbidden.'
                )

            if pos < len(self.output_slot_specs):
                slot_spec = self.output_slot_specs[pos]

                # Determine width of output slot
                if isinstance(slot_spec.width, str):
                    # Dynamic width based on input argument
                    width = bound_arguments.arguments[slot_spec.width]
                elif not isinstance(slot_spec.width, bool):
                    # Fixed integer width
                    width = slot_spec.width
                elif slot_spec.width and hasattr(signal, 'operand_width') and signal.operand_width is not None:
                    # Copy operand width
                    width = signal.operand_width
                else:
                    raise ValueError(
                        f'Unable to determine the width of the output slot for the output value at position {pos}. The output signal {signal.name} for this result has no fixed operand width.\n'
                        f'The slot has the following specification: {slot_spec}'
                    )
            else:
                width = None
            widths.append(width)
        return widths

    def create_output_slots(self, widths: Sequence[Optional[int]]) -> Sequence[Optional[ScratchSignalProto]]:
        """Create output slots for results."""
        output_slots: List[Optional[ScratchSignalProto]] = []
        for width in widths:
            if width is not None:
                # Create signals
                output_slots.append(self.engine.define_scratch(width))
            else:
                output_slots.append(None)
        return output_slots

    def copy_result_out(  # noqa: C901
        self, result: R, output_slots: Sequence[Optional[ScratchSignalProto]], return_address: SignalProto, call_id: int
    ) -> Tuple[R, Sequence[WeakReference[SignalProto]]]:
        """Copy any scratch signals in the results out of the segment body.

        This ensures that the scratch signals can be released like normal.
        """
        if result is None:
            self.engine.current_state = self.engine.next_state
            return result, ()

        # Pack results into iterable
        if is_iterable := hasattr(result, '__iter__'):
            results: Sequence[AnySignal] = result  # type: ignore
        else:
            results = (result,)  # type: ignore

        # Process the output values for output slots to check if they have been assigned in the current state
        # If possible, fast-forwards the values
        fast_forwarder = FastForwarder(self.engine)
        fast_forward_results: List[Optional[AnySignal]] = []
        for signal, output_slot in zip(results, output_slots):
            # Fast-forwarding is only needed for output slots, not signals that are directly returned
            if output_slot is not None:
                fast_forward_results.append(fast_forwarder(signal))
            else:
                fast_forward_results.append(None)

        # If fast-forwarding is impossible, everything needs to happen in an intermediary state
        if fast_forwarder.needs_sync:
            self.engine.current_state = self.engine.next_state
            fast_forward_results = [None] * len(fast_forward_results)  # Discard all fast-forward results, if a sync is needed anyways
        else:
            fast_forward_condition = self.get_fast_forward_return_address(return_address) == call_id

        new_results: List[object] = []
        weak_references: List[WeakReference[SignalProto]] = []
        # Recover memory view to re-enable access to the results
        with self.recover_memory_zone():
            for signal, fast_forward_signal, output_slot in zip(results, fast_forward_results, output_slots):
                if output_slot is not None:
                    if fast_forward_signal is not None:
                        # Reclaim all parts of an fast-forwarded expression and add or update selector assignment
                        fast_forwarder.reclaim(fast_forward_signal)
                        fast_forwarder.add_assignment_case(output_slot, fast_forward_signal, fast_forward_condition)
                    else:
                        # Reclaim the output signal
                        if isinstance(signal, ScratchSignal) and signal.released:
                            signal.reclaim()
                        self.engine.set(output_slot, signal)

                    new_results.append(output_slot)
                else:
                    ref: WeakReference[PermanentSignal] = WeakReference(signal)  # type: ignore[arg-type]
                    weak_references.append(ref)
                    new_results.append(ref)

        if fast_forwarder.needs_sync:
            self.engine.sync()
        else:
            self.engine.current_state = self.engine.next_state

        # Unpack results from iterable
        if is_iterable:
            return tuple(new_results), weak_references  # type: ignore[arg-type, return-value]
        else:
            return new_results[0], weak_references  # type: ignore[return-value]

    # Memory zone management
    @property
    def memory_zone(self) -> MemoryZoneProto:
        """Memory zone within scratch manager.

        The zone is re-used among all calls to this segment.
        """
        if self._memory_zone is None:
            self._memory_zone = self.engine.scratch_manager.create_zone(self.method.__name__)
        return self._memory_zone

    @contextmanager
    def recover_memory_zone(self) -> Iterator[None]:
        """Recover memory zone and view for the active rendered segment."""
        view = self.active_rendered_segment.memory_view
        zone = view.zone
        with zone.recover(view):
            yield

    # Return adress storage
    @property
    def backup_address(self) -> SignalProto:
        """Signal to backup previous return address during calls, for the current worker."""
        if self.engine.current_worker not in self.backup_addresses:
            # Create new backup signal
            # The name is unique for the worker and the memory zone ID (which is unique across segments)
            # The width is tied to the variable width of the return address (which is unique accross workers)
            name = self.engine.current_worker.create_scoped_name(f'BACKUP_ADDRESS_ZONE{self.memory_zone.id}')
            self.backup_addresses[self.engine.current_worker] = self.engine.define_local(
                name, width=self.engine_context.return_address.width, reset_value=0
            )
        return self.backup_addresses[self.engine.current_worker]

    # Signature binding
    def extract_signature(self, *args: P.args, **kwargs: P.kwargs) -> str:
        """Extract call signature and return it's representation as a string.

        The call signature is used as a key to distinguish if new calls of the segment can re-use an existing segment, or render a new one.
        """
        bound_arguments = self.bind_arguments(Ignore(), args=args, kwargs=kwargs)  # type: ignore[arg-type]

        # Redact arguments hidden behind input slots
        for name in self.input_slot_specs:
            bound_arguments.arguments[name] = Ignore()
        return repr(bound_arguments)

    def bind_arguments(self, obj: Optional[T] = None, /, args: Sequence[object] = (), kwargs: Mapping[str, object] = dict()) -> BoundArguments:
        """Bind arguments to signature."""
        bound_arguments = self.signature.bind(obj, *args, **kwargs)
        bound_arguments.apply_defaults()
        return bound_arguments

    def iter_bound_arguments(
        self, obj: Optional[T] = None, /, args: Sequence[object] = (), kwargs: Mapping[str, object] = dict()
    ) -> Iterator[Tuple[str, object]]:
        """Bind arguments to signature and iter over them."""
        yield from tuple(self.bind_arguments(obj, args=args, kwargs=kwargs).arguments.items())

    def format_call(self, args: Sequence[object] = (), kwargs: Mapping[str, object] = dict()) -> str:
        """Format call to method."""
        args_ = list(self.signature.parameters.keys())[0:1] if not self.is_partial else []
        args_ += [f'{arg}' for arg in args]
        args_ += [f'{key}={value}' for key, value in kwargs.items()]

        return f'{self.method.__name__}({", ".join(args_)})'
