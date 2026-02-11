"""Signal definition."""

from abc import ABCMeta, abstractmethod
from collections import OrderedDict
from types import TracebackType
from typing import Dict, Final, Generic, Literal, Mapping, Optional, Sequence, Set, Tuple, Type, TypeVar, Union

from typing_extensions import Self

from nortl.core.checker import StaticAccessChecker
from nortl.core.common import NamedEntity, StaticAccess
from nortl.core.exceptions import AccessAfterReleaseError, WriteViolationError
from nortl.core.modifiers import BaseModifier
from nortl.core.operations import OperationTrait
from nortl.core.protocols import (
    ACCESS_CHECKS,
    BIT_ORDER,
    EVENT_TYPES,
    SIGNAL_TYPES,
    AssignmentTarget,
    EngineProto,
    ModuleInstanceProto,
    ParameterProto,
    Renderable,
    SignalProto,
    SignalSliceProto,
    StaticAccessCheckerProto,
    StaticAccessProto,
    ThreadProto,
)
from nortl.utils.type_aliases import IntSlice

__all__ = [
    'ScratchSignal',
    'Signal',
    'SignalSlice',
]

T_Signal = TypeVar('T_Signal', SignalProto, SignalSliceProto)


class ParameterizedEvent:
    """Wrapper object for a parametrized event."""

    def __init__(self, event: EVENT_TYPES):
        self._parameter_dict: OrderedDict[str, Union[int, str, ParameterProto]] = OrderedDict()
        self._event = event

    def __repr__(self) -> str:
        ret = str(self._event)
        for k, v in self._parameter_dict.items():
            ret += f'{k} {v}'

        return ret

    def __hash__(self) -> int:
        return hash(repr(self))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ParameterizedEvent):
            raise NotImplementedError('Can not compare parameterized Events to other types!')
        return repr(self) == repr(other)

    def add_parameter(self, param: str, value: Union[int, str, ParameterProto]) -> None:
        self._parameter_dict[param] = value

    def get_parameter(self, param: str) -> Union[int, str, ParameterProto]:
        return self._parameter_dict[param]


def pick_indexes(all_indexes: Sequence[int], index: Union[int, IntSlice]) -> Sequence[int]:
    """Pick indexes covered by this slice."""
    if isinstance(index, slice):
        # noRTL supports reversed indexes, to better match Verilog. They must be flipped here.
        # In addition, the stop index is treated as inclusive
        start = min(index.start, index.stop)  # type: ignore[type-var]
        stop = max(index.start, index.stop) + 1  # type: ignore[type-var, operator]
        return all_indexes[start:stop]
    else:
        return (all_indexes[index],)


def list_indexes(index: Union[int, IntSlice]) -> Sequence[int]:
    """List all indexes covered by a slice."""
    if isinstance(index, slice):
        # noRTL supports reversed indexes, to better match Verilog. They must be flipped here.
        # In addition, the stop index is treated as inclusive
        start: int = min(index.start, index.stop)  # type: ignore[assignment, type-var]
        stop: int = max(index.start, index.stop)  # type: ignore[assignment, type-var]
        return tuple(range(start, stop + 1))
    else:
        return (index,)


def validate_slice(index: IntSlice) -> Tuple[int, int, BIT_ORDER]:
    """Validate a slice and return start and stop values sorted by size."""
    # The stop value for the Python slice is treated as inclusive
    start, stop, step = index.start, index.stop, index.step

    if start is None:
        raise ValueError('Missing start position for signal slice operation!')
    if stop is None:
        raise ValueError('Missing stop position for signal slice operation!')
    if step is not None:
        raise ValueError('Providing a step size is not supported for signal slice operation!')

    return min(start, stop), max(start, stop), 'L:H' if stop > start else 'H:L'


class _BaseSignal(OperationTrait, NamedEntity, metaclass=ABCMeta):
    """Abstract base class for signals."""

    is_primitive: Final = True
    is_constant: Final = False

    def __init__(self, name: str):
        super().__init__(name)

    @property
    def name(self) -> str:
        """Signal name."""
        return self._name

    # Abstract properties required by base methods
    @property
    @abstractmethod
    def engine(self) -> EngineProto:
        """NoRTL engine that this signal belongs to."""

    @property
    @abstractmethod
    def width(self) -> Union[int, ParameterProto, Renderable]:
        """Signal width in bits."""

    @property
    @abstractmethod
    def escaped_name(self) -> str:
        """Name of signal with any special characters escaped."""

    # Access control
    @property
    @abstractmethod
    def read_accesses(self) -> Set[StaticAccessProto]:
        """Mutable set of read accesses to this signal."""

    @property
    @abstractmethod
    def write_accesses(self) -> Set[StaticAccessProto]:
        """Mutable set of write accesses to this signal."""

    @property
    @abstractmethod
    def last_read_access_thread(self) -> Optional[ThreadProto]:
        """Thread performing the last read access."""

    @last_read_access_thread.setter
    @abstractmethod
    def last_read_access_thread(self, value: ThreadProto) -> None:
        """Thread performing the last read access."""

    @property
    @abstractmethod
    def last_write_access_thread(self) -> Optional[ThreadProto]:
        """Thread performing the last write access."""

    @last_write_access_thread.setter
    @abstractmethod
    def last_write_access_thread(self, value: ThreadProto) -> None:
        """Thread performing the last write access."""

    @property
    @abstractmethod
    def access_checker(self) -> StaticAccessCheckerProto:
        """Static access checker."""

    def write_access(self, ignore: Set[ACCESS_CHECKS] = set()) -> None:
        """Register write access from the current thread.

        If the current thread differs from the last write acess, will invoke the access checker.

        Raises:
            ExclusiveWriteError: If the signals was written by more than one thread.
            NonIdenticalRWError: If the signals was written by one, and read from another thread.
        """
        self.write_accesses.add(StaticAccess(self.engine.current_thread))

        if self.engine.current_thread is not self.last_write_access_thread:
            # Slow check is only executed, if the thread has changed.
            self.access_checker.check(ignore=ignore)

        self.last_write_access_thread = self.engine.current_thread

    def read_access(self, ignore: Set[ACCESS_CHECKS] = set()) -> None:
        """Register read access from the current thread.

        If the current thread differs from the last write acess, will invoke the access checker.

        Raises:
            ExclusiveReadError: If the signal was read from more than one thread.
            NonIdenticalRWError: If the signals was written by one, and read from another thread.
        """
        self.read_accesses.add(StaticAccess(self.engine.current_thread))

        if self.engine.current_thread is not self.last_read_access_thread:
            # Slow check is only executed, if the thread has changed.
            self.access_checker.check(ignore=ignore)

        self.last_read_access_thread = self.engine.current_thread

    def free_access_from_thread(self, thread: ThreadProto) -> None:
        """This function disables all access checks that have their origin in the given thread.

        It is to be used during fork for passing signals to a forked thread. In this case, the signal
        is accessed (written) by the origin thread and handed off to the spawned thread.

        Since parallel running behavior is described below the actual fork context, a colliding access will
        happen after the fork-block has been executed. The collision will be shown once the origin thread
        will access the signal while the forked thread has not ended.
        """
        for access in self.write_accesses | self.read_accesses:
            if access.thread == thread:
                access.disable()


class _AccessControlledSignal(_BaseSignal):
    """Intermediary class for signals that keep track their own access control.

    This is used for signals and scratch signals.
    """

    def __init__(self, name: str) -> None:
        super().__init__(name)

        self._write_accesses: Set[StaticAccessProto] = set()
        self._read_accesses: Set[StaticAccessProto] = set()
        self._last_read_access_thread: Optional[ThreadProto] = None
        self._last_write_access_thread: Optional[ThreadProto] = None
        self._access_checker = StaticAccessChecker(self)

    @property
    def read_accesses(self) -> Set[StaticAccessProto]:
        """Mutable set of read accesses to this signal."""
        return self._read_accesses

    @property
    def write_accesses(self) -> Set[StaticAccessProto]:
        """Mutable set of write accesses to this signal."""
        return self._write_accesses

    @property
    def last_read_access_thread(self) -> Optional[ThreadProto]:
        """Thread performing the last read access."""
        return self._last_read_access_thread

    @last_read_access_thread.setter
    def last_read_access_thread(self, value: ThreadProto) -> None:
        """Thread performing the last read access."""
        self._last_read_access_thread = value

    @property
    def last_write_access_thread(self) -> Optional[ThreadProto]:
        """Thread performing the last write access."""
        return self._last_write_access_thread

    @last_write_access_thread.setter
    def last_write_access_thread(self, value: ThreadProto) -> None:
        """Thread performing the last write access."""
        self._last_write_access_thread = value

    @property
    def access_checker(self) -> StaticAccessCheckerProto:
        """Static access checker."""
        return self._access_checker


class _EventSourceSignal(Generic[T_Signal], _BaseSignal):
    """Class for signals that can be used as the source for a event.

    This is only the case for signals and slice signals, but not for scratch signals, due to their ephemeral nature.
    """

    def __init__(self, name: str) -> None:
        super().__init__(name)

        self._events: Dict[ParameterizedEvent, ModuleInstanceProto] = {}

    @property
    def events(self) -> Mapping[ParameterizedEvent, ModuleInstanceProto]:
        """Events for this signal."""
        return self._events

    def rising(self) -> T_Signal:
        """Create rising edge event."""
        return self._create_edge_detector().get_connected_signal('RISING')  # type: ignore[return-value]

    def falling(self) -> T_Signal:
        """Create falling edge event."""
        return self._create_edge_detector().get_connected_signal('FALLING')  # type: ignore[return-value]

    def delayed(self, cycles: Union[int, ParameterProto] = 1) -> T_Signal:
        """Create event for delayed signal."""
        return self._create_delay(cycles).get_connected_signal('OUT')  # type: ignore[return-value]

    def synchronized(self) -> T_Signal:
        """Create event for synchronized signal."""
        return self._create_synchronized().get_connected_signal('OUT')  # type: ignore[return-value]

    def _create_edge_detector(self) -> ModuleInstanceProto:
        """Creates the edge detector for the signal if it does not exist.

        If the signal has more than one bit, this results in ValueError.
        """
        if self.width != 1:
            raise ValueError('Edge dectors can only be used in 1-bit signals!')

        if (event := ParameterizedEvent('edge')) not in self.events:
            instance_name = f'I_EVENT_EDGE_DETECTOR_{self.escaped_name}'
            instance = self.engine.create_module_instance(module_name='nortl_edge_detector', instance_name=instance_name)
            self._events[ParameterizedEvent('edge')] = instance

            signal_rising = self.engine.define_local(f'EVENT_{self.escaped_name}_rising')
            signal_falling = self.engine.define_local(f'EVENT_{self.escaped_name}_falling')

            self.engine.connect_module_port(instance_name, 'SIGNAL', self)  # type: ignore[arg-type]
            self.engine.connect_module_port(instance_name, 'RISING', signal_rising)
            self.engine.connect_module_port(instance_name, 'FALLING', signal_falling)

            return instance
        else:
            return self.events[event]

    def _create_delay(self, cycles: Union[int, ParameterProto] = 1) -> ModuleInstanceProto:
        """Create a delay for the signal if it does not exist."""
        event = ParameterizedEvent('delay')
        event.add_parameter('cycles', cycles)

        if event not in self.events:
            instance_name = f'I_DELAY_BY_{cycles}_{self.escaped_name}'
            instance = self.engine.create_module_instance(module_name='nortl_delay', instance_name=instance_name)
            self.engine.override_module_parameter(instance_name, 'DELAY_STEPS', cycles)
            self.engine.override_module_parameter(instance_name, 'DATA_WIDTH', self.width)

            self._events[event] = instance

            delayed_signal = self.engine.define_local(f'EVENT_{self.escaped_name}_DELAY_BY_{cycles}', self.width)

            self.engine.connect_module_port(instance_name, 'IN', self)  # type: ignore[arg-type]
            self.engine.connect_module_port(instance_name, 'OUT', delayed_signal)

            return instance
        else:
            return self.events[event]

    def _create_synchronized(self) -> ModuleInstanceProto:
        """Create sync module for this signal if it does not exist."""
        if (event := ParameterizedEvent('sync')) not in self.events:
            instance_name = f'I_SYNC_{self.escaped_name}'
            instance = self.engine.create_module_instance(module_name='nortl_sync', instance_name=instance_name)
            self.engine.override_module_parameter(instance_name, 'DATA_WIDTH', self.width)

            self._events[event] = instance

            delayed_signal = self.engine.define_local(f'EVENT_{self.escaped_name}_SYNCED')

            self.engine.connect_module_port(instance_name, 'IN', self)  # type: ignore[arg-type]
            self.engine.connect_module_port(instance_name, 'OUT', delayed_signal)

            return instance
        else:
            return self.events[event]


class Signal(_AccessControlledSignal, _EventSourceSignal[SignalProto]):
    """Signal definition, representing a Verilog signal.

    Attributes:
        engine: Finite state machine associated with this signal.
        type: The role of the signal (input, output, interface, internal, local).
        name: Name of the signal.
        width: Width in bits of the signal.
        data_type: Data type of the signal. Defaults to 'logic'.

    The signal types are defined as follows:
    * input, output: Port of the module
    * interface: Use a system verilog interface
    * local: A local register used that is not passed to the outside
    * internal: a signal created by internal data structures, not necessarily visible for the user
    """

    def __init__(
        self,
        engine: EngineProto,
        type: SIGNAL_TYPES,
        name: str,
        width: Union[int, ParameterProto, Renderable] = 1,
        data_type: str = 'logic',
        is_synchronized: bool = False,
        pulsing: bool = False,
        assignment: Optional[Renderable] = None,
    ) -> None:
        """Initialize a signal.

        Arguments:
            engine: State machine container object.
            name: Signal name.
            type: Signal type.
            width: Width in bits (default=1).
            data_type: Data type of the signal (default='logic').
            is_synchronized: Indicates, if the signal is synchronous to the local clock domain.
            pulsing: Wether the signal resets automatically to 0 if not written in current state
            assignment: Source expression for combinational assignment.
        """
        if type != 'internal' and name.startswith('_'):
            raise ValueError('Signal names must not start with an underscore!')
        if assignment is not None:
            if type == 'input':
                raise ValueError('Input signals must not have a combinational assignment.')
            if pulsing:
                raise ValueError('Signals with a combinational assignment cannot be pulsing.')

        super().__init__(name)

        self._engine = engine
        self._type = type
        self._width = width
        self._operand_width = width if isinstance(width, int) else None
        self._data_type = data_type
        self._is_synchronized = is_synchronized
        self._pulsing = pulsing
        self._assignment = assignment

    @property
    def engine(self) -> EngineProto:
        """NoRTL engine for this signal."""
        return self._engine

    @property
    def type(self) -> SIGNAL_TYPES:
        """Signal type."""
        return self._type

    @property
    def pulsing(self) -> bool:
        """Shows, if the signal is self-resetting to zero after one cycle."""
        return self._pulsing

    @property
    def assignment(self) -> Optional[Renderable]:
        """Source expression for combination assignment."""
        return self._assignment

    @property
    def escaped_name(self) -> str:
        """Name of signal with any special characters escaped.

        For regular signals, this is equal to their name. For slice signals, it contains the position.
        """
        return self.name

    @property
    def width(self) -> Union[int, ParameterProto, Renderable]:
        """Signal width in bits."""
        return self._width

    @property
    def operand_width(self) -> Optional[int]:
        """Indicates the width when used as an operand.

        A width of None means that the width is not fixed during execution of noRTL.
        This is the case, if the signal width is based on a parameter.
        """
        return self._operand_width

    @property
    def data_type(self) -> str:
        """Data type of the signal (e.g., 'logic', 'reg', etc.)."""
        return self._data_type

    def render(self, target: Optional[str] = None) -> str:
        """Render value to target language.

        Arguments:
            target: Target language.
        """
        return self.name

    def __getitem__(self, index: Union[int, IntSlice]) -> 'SignalSlice':
        return SignalSlice(self, index)

    def overlaps_with(self, other: AssignmentTarget) -> Union[bool, Literal['partial']]:
        """Check if signal overlaps with other signal or signal slice."""
        return self.name == other.name

    def read_access(self, ignore: Set[ACCESS_CHECKS] = set()) -> None:
        """Register read access from the current thread.

        If the current thread differs from the last write acess, will invoke the access checker.

        Raises:
            ExclusiveReadError: If the signal was read from more than one thread.
            NonIdenticalRWError: If the signals was written by one, and read from another thread.
        """
        if self.assignment is not None:
            # Trigger read access on the assignment expression
            self.assignment.read_access(ignore=ignore)
        else:
            super().read_access(ignore=ignore)

    def write_access(self, ignore: Set[ACCESS_CHECKS] = set()) -> None:
        """Register write access from the current thread.

        If the current thread differs from the last write acess, will invoke the access checker.

        Raises:
            ExclusiveWriteError: If the signals was written by more than one thread.
            NonIdenticalRWError: If the signals was written by one, and read from another thread.
            WriteViolationError: If the signal is read-only.
        """
        if self.type == 'input':
            raise WriteViolationError(f'Input signal {self.name} is read-only.')
        if self.assignment is not None:
            raise WriteViolationError(f'Signal {self.name} is assigned to the expression {self.assignment}. It is read-only.')
        else:
            super().write_access(ignore=ignore)


class _BaseSlice(_BaseSignal):
    """Intermediate class for signal slices."""

    def __init__(self, signal: SignalProto, index: Union[int, IntSlice]) -> None:
        super().__init__(signal.name)

        self._base_signal = signal
        self._index = index

        if isinstance(signal.width, int):
            if signal.width <= 1:
                raise IndexError(f'Unable to slice signal with width {signal.width}!')

        if isinstance(index, int):
            if index < 0:
                raise IndexError(f'Index {index} is out of bounds for signal {signal.name} with width {signal.width}')
            if isinstance(signal.width, int) and index not in range(0, signal.width):
                raise IndexError(f'Index {index} is out of bounds for signal {signal.name} with width {signal.width}')

            self._width: int = 1
            self._bitorder: Optional[BIT_ORDER] = None
        else:
            start, stop, bitorder = validate_slice(index)
            self._width = stop - start + 1
            self._bitorder = bitorder

    @property
    def base_signal(self) -> SignalProto:
        """Full-width signal of this slice."""
        return self._base_signal

    @property
    def index(self) -> Union[int, IntSlice]:
        """Index of the signal."""
        return self._index

    # Properties forwarded to full-width signal
    @property
    def engine(self) -> EngineProto:
        """Finite state machine."""
        return self.base_signal.engine

    @property
    def type(self) -> SIGNAL_TYPES:
        """Signal type."""
        return self.base_signal.type

    @property
    def pulsing(self) -> bool:
        """Shows, if the signal is self-resetting to zero after one cycle."""
        return self.base_signal.pulsing

    @property
    def escaped_name(self) -> str:
        """Name of signal with any special characters escaped.

        For regular signals, this is equal to their name. For slice signals, it contains the position.
        """
        if isinstance(self.index, int):
            return f'{self.name}_{self.index}'
        else:
            return f'{self.name}_{self.index.start}to{self.index.stop}'

    @property
    def data_type(self) -> str:
        """Data type of the signal (e.g., 'logic', 'reg', etc.)."""
        return self.base_signal.data_type

    @property
    def _is_synchronized(self) -> bool:
        """Indicates if the this signal is synchronized to the local clock domain."""
        return self.base_signal._is_synchronized

    # Additional properties
    @property
    def width(self) -> int:
        """Signal width in bits."""
        return self._width

    @property
    def bitorder(self) -> Optional[BIT_ORDER]:
        """Bit order of signal."""
        return self._bitorder

    @property
    def operand_width(self) -> int:
        """Indicates the width when used as an operand.

        A width of None means that the width is not fixed during execution of noRTL.
        This is the case, if the signal width is based on a parameter.
        """
        return self.width

    def overlaps_with(self, other: AssignmentTarget) -> Union[bool, Literal['partial']]:
        """Check if signal slice overlaps with other signal or signal slice."""

        if self.name != other.name:
            return False

        # Unwrap content of modifier
        if isinstance(other, BaseModifier):
            other = other.content

        if isinstance(other, _BaseSlice):
            # Signal slice, check if it overlaps
            if isinstance(self.index, int) and isinstance(other.index, int):
                # Full overlap or none
                return self.index == other.index
            elif isinstance(self.index, slice) and isinstance(other.index, slice) and self.index == other.index:
                # Full overlap, if the slices are exactly the same
                return True

            own_indexes = set(list_indexes(self.index))
            other_indexes = set(list_indexes(other.index))

            if own_indexes.isdisjoint(other_indexes):
                return False
            if own_indexes == other_indexes:
                return True

        # In all other cases (overlap of signal and slice, parametric width, partial overlap), treat overlap as partial
        return 'partial'

    def render(self, target: Optional[str] = None) -> str:
        """Render value to target language.

        Arguments:
            target: Target language.
        """
        if isinstance(self.index, int):
            return f'{self.name}[{self.index}]'
        elif self.index.start == self.index.stop:
            return f'{self.name}[{self.index.start}]'
        else:
            return f'{self.name}[{self.index.start}:{self.index.stop}]'

    def __getitem__(self, index: Union[int, IntSlice]) -> Self:
        if isinstance(self.index, int):
            if index == 0:
                return self  # Allow indexing [0] of a single bit slice again
            else:
                raise IndexError(f'Unable to slice {index} from single-bit signal slice {self.escaped_name}: Only index 0 can be sliced.')
        else:
            # Assemble list of own indexes, with reference to the base signal
            own_indexes = list_indexes(self.index)
            own_start: int = own_indexes[0]
            own_stop: int = own_indexes[-1]

            # Check that the new index doesn't go out of range (this is not caught by pick_indexes)
            if isinstance(index, int):
                if index < 0 or index > (own_stop - own_start):
                    raise IndexError(f'Unable to slice {index} from signal slice {self.escaped_name}: Index is out of range.')
            else:
                start, stop, bitorder = validate_slice(index)
                if start < 0 or stop > (own_stop - own_start):
                    raise IndexError(f'Unable to slice {index} from signal slice {self.escaped_name}: Index is out of range.')
                if bitorder != self.bitorder:
                    raise IndexError(f'Unable to slice {index} from signal slice {self.escaped_name}: Reversing the bit order is not allowed')

            # Pick the indexes for the nested slice, with reference to the base signal
            new_indexes = pick_indexes(own_indexes, index)

            if len(new_indexes) == 0:
                raise IndexError(f'Unable to slice {index} from signal slice {self.escaped_name}: slice result in zero length signal.')
            if len(new_indexes) == 1:
                return type(self)(self.base_signal, new_indexes[0])

            # As we don't support multiple indexes, we only need to find the new minimum and maximum indexes
            if bitorder == 'H:L':
                return type(self)(self.base_signal, slice(max(new_indexes), min(new_indexes)))
            else:
                return type(self)(self.base_signal, slice(min(new_indexes), max(new_indexes)))


class SignalSlice(_BaseSlice, _EventSourceSignal[SignalSliceProto]):
    """Slice of a signal."""

    def __init__(self, signal: SignalProto, index: Union[int, IntSlice]) -> None:
        # if not isinstance(signal.width, int):
        # TODO: Do we need to pass metadata along?
        # TODO: parameters or renderable widths cannot be validated
        # raise NotImplementedError('Only signals with discrete width can be sliced!')  # noqa: ERA001
        super().__init__(signal, index)

    # Forward access control to base signal
    @property
    def access_checker(self) -> StaticAccessCheckerProto:
        """Static access checker."""
        return self.base_signal.access_checker

    @property
    def read_accesses(self) -> Set[StaticAccessProto]:
        """Mutable set of read accesses to this signal."""
        return self.base_signal.read_accesses

    @property
    def write_accesses(self) -> Set[StaticAccessProto]:
        """Mutable set of write accesses to this signal."""
        return self.base_signal.write_accesses

    @property
    def last_read_access_thread(self) -> Optional[ThreadProto]:
        """Thread performing the last read access."""
        return self.base_signal.last_read_access_thread

    @last_read_access_thread.setter
    def last_read_access_thread(self, value: ThreadProto) -> None:
        """Thread performing the last read access."""
        self.base_signal.last_read_access_thread = value

    @property
    def last_write_access_thread(self) -> Optional[ThreadProto]:
        """Thread performing the last write access."""
        return self.base_signal.last_write_access_thread

    @last_write_access_thread.setter
    def last_write_access_thread(self, value: ThreadProto) -> None:
        """Thread performing the last write access."""
        self.base_signal.last_write_access_thread = value

    def as_scratch_signal(self) -> 'ScratchSignal':
        """Turn SignalSlice into ScratchSignal, owned by the current thread."""
        return ScratchSignal(self.base_signal, self.index)


class ScratchSignal(_BaseSlice, _AccessControlledSignal):
    """A scratch signal is a special kind of signal slice, that is only valid for a limited time."""

    def __init__(self, signal: SignalProto, index: Union[int, IntSlice]) -> None:
        super().__init__(signal, index)

        self._owner = signal.engine.current_thread

        # Access control for scratch signals
        self._released: bool = False
        self._context_ctr: int = 0
        self._context_ctr_active: bool = True

        # Remember, where the scratch signal was created
        self.creator_frames = self.engine.tracer.current_trace

    @property
    def owner(self) -> ThreadProto:
        """Owner of this scratch signal."""
        return self._owner

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: Optional[Type[BaseException]], exc_val: Optional[BaseException], exc_tb: Optional[TracebackType]) -> None:
        self.release()

    def enter_context(self) -> None:
        """Context counting method.

        The claim/release logic relies on the concept, that a scratch variable is to be released in the context where it has been created.
        A context is represented by a Condition or a Loop construct. Both are created with context managers and may be nested.
        The idea of this function is to count the 'depth' of context nests that we are currently working with.

        In this way, we can detect, if the user tries to release the signal in a different context than creation. Once the release function is called,
        we stop context counting since the scratch signal is now inactive and the claim/release-control is now realized based on the currently running threads.

        This concept assumes, that each context manager triggers the `enter_context` function during enter and the `exit_context` function during exit.
        The `exit_context` function automatically releases the signal, if we leave the claiming context.
        """
        if self._context_ctr_active:
            self._context_ctr += 1

    def exit_context(self) -> None:
        """Context counting method. Explanation in exit_context function."""
        if self._context_ctr_active:
            self._context_ctr -= 1

            if self._context_ctr == -1 and self.owner == self.engine.current_thread:
                self._context_ctr = 0
                self.release()

    # Access control
    def write_access(self, ignore: Set[ACCESS_CHECKS] = set()) -> None:
        """Register write access from the current thread.

        If the current thread differs from the last write acess, will invoke the access checker.

        Raises:
            ExclusiveWriteError: If the signals was written by more than one thread.
            NonIdenticalRWError: If the signals was written by one, and read from another thread.
            AccessAfterReleaseError: If the scratch signal was released.
        """
        if self.released:
            raise AccessAfterReleaseError('Tried to write to a signal that has been released previously!')
        super().write_access(ignore=ignore)

    def read_access(self, ignore: Set[ACCESS_CHECKS] = set()) -> None:
        """Register read access from the current thread.

        If the current thread differs from the last write acess, will invoke the access checker.

        Raises:
            ExclusiveReadError: If the signal was read from more than one thread.
            NonIdenticalRWError: If the signals was written by one, and read from another thread.
            AccessAfterReleaseError: If the scratch signal was released.
        """
        if self.released:
            raise AccessAfterReleaseError('Tried to read from a signal that has been released previously!')
        super().read_access(ignore=ignore)

    @property
    def released(self) -> bool:
        """Findout, if a signal has been release yet.

        The claim/release control works based on two principles:

        1. A scratch signal may only be claimed and released in a single code block. Example:
        ```python
        f = CoreEngine("my_engine")

        with Condition(f, some_condition):
            s = # new scratch signal

            with ForLoop(...):
                # s may not be released here

            s.release() # s can be released here, since it is the same context

        # After the context has ended, s is automatically released.
        ```

        2. A scratch signal will appear as non-released in parallel threads and will be released once the owner thread ends. Additional access control applies.
        ```python
        f = CoreEngine("my_engine")

        with Fork(f, "my_fork") as f1:
            s = # new scratch_signals
            #...
            s.release()
        with Fork(f, "my_second_fork") as f2:
            assert s.released == False # Parallel running thread the scratch pad location!

        f1.wait_for_finish()

        # s is released automatically once the thread has finished.
        ```

        """
        if self.owner != self.base_signal.engine.current_thread:
            return not self.owner.running
        return self._released

    def release(self, force: bool = False) -> None:
        if self.owner != self.base_signal.engine.current_thread and not force:
            raise ValueError('Scratch register may only be released in owning thread!')
        if self._context_ctr != 0 and not force:
            raise ValueError('Scratch signals need to be released in the context where they were created!')

        self._context_ctr_active = False
        self._released = True

    def states_disjoint(self, other: Self) -> bool:
        """This function calculates if the current scratch signal and the other scratch signal are never active (i.a. non-released) in the same states."""

        def get_active_states(scratch_signal: Self) -> Set[str]:
            ret = set()
            for statelst in self.engine.states.values():
                for state in statelst:
                    for s in state.active_scratch_signals:
                        if scratch_signal is s:  # FIXME: Weird containment, scratch_signal in self.active_scratch signals is always True?
                            ret.add(state.name)
            return ret

        other_active_states = get_active_states(other)
        self_active_states = get_active_states(self)

        return len(self_active_states.intersection(other_active_states)) == 0
