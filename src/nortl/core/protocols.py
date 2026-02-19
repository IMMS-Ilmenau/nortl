from contextlib import contextmanager
from inspect import FrameInfo
from typing import (
    Any,
    ClassVar,
    ContextManager,
    Dict,
    Generic,
    Iterator,
    List,
    Literal,
    Mapping,
    Optional,
    Protocol,
    Sequence,
    Set,
    Tuple,
    TypeVar,
    Union,
)

from typing_extensions import Self

from nortl.utils.type_aliases import IntSlice

__all__ = [
    'AnySignal',
    'Operand',
    'PermanentSignal',
]

Operand = Union['Renderable', int, bool]
PermanentSignal = Union['SignalProto', 'SignalSliceProto']
AnySignal = Union['SignalProto', 'SignalSliceProto', 'ScratchSignalProto']

SIGNAL_TYPES = Literal['input', 'output', 'interface', 'internal', 'local']
EVENT_TYPES = Literal['edge', 'delay', 'sync']
BIT_ORDER = Literal['H:L', 'L:H']

# Access Check Definitions
SIGNAL_ACCESS_CHECKS = Literal['exclusive_read', 'exclusive_write', 'identical_rw']
ACCESS_CHECKS = SIGNAL_ACCESS_CHECKS

T_Signal = TypeVar('T_Signal', 'SignalProto', 'SignalSliceProto', covariant=True)


class NamedEntityProto(Protocol):
    @property
    def name(self) -> str: ...

    def get_metadata(self, key: str, default: Any = None) -> Any: ...

    def set_metadata(self, key: str, value: Any) -> None: ...

    def has_metadata(self, key: str) -> bool: ...


class OperationTraitProto(Protocol):
    """Trait for signals, constants or statements that allow construction of arithmetic and logic operations."""

    @property
    def is_primitive(self) -> bool: ...

    @property
    def is_constant(self) -> bool: ...

    @property
    def operand_width(self) -> Optional[int]: ...

    def read_access(self, ignore: Set[ACCESS_CHECKS] = ...) -> None: ...

    def render(self, target: Optional[str] = None) -> str: ...

    # Arithemtic Operations
    def __add__(self, value: Operand, /) -> 'Renderable': ...

    def __sub__(self, value: Operand, /) -> 'Renderable': ...

    def __mul__(self, value: Operand, /) -> 'Renderable': ...

    def __truediv__(self, value: Operand, /) -> 'Renderable': ...

    def __mod__(self, value: Operand, /) -> 'Renderable': ...

    # Arithmetic Operations (Right-Side)
    def __radd__(self, value: Operand, /) -> 'Renderable': ...

    def __rsub__(self, value: Operand, /) -> 'Renderable': ...

    def __rmul__(self, value: Operand, /) -> 'Renderable': ...

    def __rtruediv__(self, value: Operand, /) -> 'Renderable': ...

    def __rmod__(self, value: Operand, /) -> 'Renderable': ...

    # Logic Operations
    def __and__(self, value: Operand, /) -> 'Renderable': ...

    def __or__(self, value: Operand, /) -> 'Renderable': ...

    def __xor__(self, value: Operand, /) -> 'Renderable': ...

    def __lshift__(self, value: Operand, /) -> 'Renderable': ...

    def __rshift__(self, value: Operand, /) -> 'Renderable': ...

    # Logic Operations (Right Side)
    def __rand__(self, value: Operand, /) -> 'Renderable': ...

    def __ror__(self, value: Operand, /) -> 'Renderable': ...

    def __rxor__(self, value: Operand, /) -> 'Renderable': ...

    def __rlshift__(self, value: Operand, /) -> 'Renderable': ...

    def __rrshift__(self, value: Operand, /) -> 'Renderable': ...

    # Misc.
    def __neg__(self) -> 'Renderable': ...

    def __pos__(self) -> 'Renderable': ...

    # Inversion
    def __invert__(self) -> 'Renderable': ...

    # Comparison
    def __eq__(self, value: Operand, /) -> 'Renderable': ...  # type: ignore[override]

    def __ne__(self, value: Operand, /) -> 'Renderable': ...  # type: ignore[override]

    def __lt__(self, value: Operand, /) -> 'Renderable': ...

    def __le__(self, value: Operand, /) -> 'Renderable': ...

    def __gt__(self, value: Operand, /) -> 'Renderable': ...

    def __ge__(self, value: Operand, /) -> 'Renderable': ...

    # Bit Slicing
    def __getitem__(self, index: Union[int, slice]) -> 'OperationTraitProto': ...


class OperationProto(OperationTraitProto, Protocol):
    """Wrapper object that represents an operation."""

    @property
    def operands(self) -> Sequence['Renderable']: ...


class Renderable(OperationTraitProto, Protocol):
    """Renderable signal or operation that can be used as an condition."""


class AssignmentTarget(OperationTraitProto, Protocol):
    """Object that can be used as assignment target."""

    @property
    def name(self) -> str: ...

    @property
    def engine(self) -> 'EngineProto': ...

    def write_access(self, ignore: Set[ACCESS_CHECKS] = ...) -> None: ...

    def overlaps_with(self, other: 'AssignmentTarget') -> Union[bool, Literal['partial']]: ...


class ConstProto(Renderable, Protocol):
    pass


class VarProto(ConstProto, Protocol):
    def update(self, value: Union[int, bool, str]) -> None: ...


class ModuleInstanceProto(Protocol):
    _clock_gating: bool

    @property
    def module(self) -> 'ModuleProto': ...

    @property
    def name(self) -> str: ...

    @property
    def port_connections(self) -> Dict[str, 'PermanentSignal']: ...

    @property
    def parameter_overrides(self) -> Dict[str, Union[ConstProto, 'ParameterProto', Renderable]]: ...

    def connect_port(self, port_name: str, signal: 'PermanentSignal') -> None: ...

    def get_connected_signal(self, port_name: str) -> 'PermanentSignal': ...

    def override_parameter(self, name: str, value: Union[int, 'ParameterProto', Renderable]) -> None: ...


class StateProto(NamedEntityProto, Protocol):
    _prints: List[Tuple[str, Tuple[Renderable, ...]]]
    _printfs: Dict[str, List[Tuple[str, Tuple[Renderable, ...]]]]

    active_scratch_signals: List['ScratchSignalProto']

    @property
    def engine(self) -> 'EngineProto': ...

    @property
    def worker(self) -> 'WorkerProto': ...

    # Assignment Management
    @property
    def allow_assignments(self) -> bool: ...

    @property
    def assignments(self) -> Sequence[Tuple[AssignmentTarget, Renderable, Renderable]]: ...

    def add_assignment(self, signal: AssignmentTarget, value: Renderable, condition: Optional[Renderable] = None) -> None: ...

    def get_assignment(self, signal: AssignmentTarget) -> Optional[Tuple[AssignmentTarget, Renderable, Renderable]]: ...

    # Transition Management
    @property
    def transitions(self) -> Sequence[Tuple[Renderable, Self]]: ...

    def _add_transition(self, condition: Renderable, state: Self) -> None: ...

    def _restrict_transition(self, state: Self) -> None: ...

    def _lock_transitions(self) -> None: ...

    # Misc.
    def render(self, target: Optional[str] = None) -> str: ...

    def print(self, line: str, *args: Renderable) -> None: ...

    def printf(self, fname: str, line: str, *args: Renderable) -> None: ...

    @property
    def signature(self) -> str: ...


class ScratchManagerProto(Protocol):
    @property
    def engine(self) -> 'EngineProto': ...

    # Scratch signal management
    def create_signal(self, width: int) -> 'ScratchSignalProto': ...

    # Context managememt
    def enter_context(self) -> None: ...

    def exit_context(self) -> None: ...

    def force_release_signals_by_thread(self, thread: 'ThreadProto') -> None: ...

    def free_accesses_from_thread(self, thread: 'ThreadProto') -> None: ...

    # Memory zone managment
    @property
    def zones(self) -> Sequence['MemoryZoneProto']: ...

    @property
    def main_zone(self) -> 'MemoryZoneProto': ...

    @property
    def active_zone(self) -> 'MemoryZoneProto': ...

    @property
    def suspended_zones(self) -> Sequence['MemoryZoneProto']: ...

    def create_zone(self, name: Optional[str] = None) -> 'MemoryZoneProto': ...


class MemoryZoneProto(ContextManager['MemoryViewProto'], Protocol):
    @property
    def manager(self) -> ScratchManagerProto: ...

    @property
    def name(self) -> str: ...

    @property
    def id(self) -> int: ...

    # Scratch pad
    width: int

    @property
    def scratchpad(self) -> 'SignalProto': ...

    @property
    def scratch_map(self) -> Sequence[bool]: ...

    def alloc(self, width: int) -> Optional[int]: ...

    # Scratch signal management
    @property
    def scratch_signals(self) -> Sequence['ScratchSignalProto']: ...

    def create_signal(self, width: int) -> 'ScratchSignalProto': ...

    # Activation and view management
    @property
    def active(self) -> bool: ...

    @property
    def suspended(self) -> bool: ...

    @property
    def active_view(self) -> 'MemoryViewProto': ...

    @property
    def views(self) -> Sequence['MemoryViewProto']: ...

    @contextmanager
    def recover(self, view: 'MemoryViewProto') -> Iterator[None]: ...


class MemoryViewProto(Protocol):
    @property
    def zone(self) -> MemoryZoneProto: ...

    @property
    def scratch_signals(self) -> Sequence['ScratchSignalProto']: ...

    def create_signal(self, width: int) -> 'ScratchSignalProto': ...

    def _register_signal(self, signal: 'ScratchSignalProto') -> None: ...


class SignalManagerProto(Protocol):
    @property
    def signals(self) -> Mapping[str, 'SignalProto']: ...

    @property
    def combinationals(self) -> Sequence[Tuple['SignalProto', Renderable]]: ...

    def get_signal(self, name: str) -> 'SignalProto': ...

    def create_signal(
        self,
        type: SIGNAL_TYPES,
        name: str,
        width: Union[int, 'ParameterProto', Renderable] = 1,
        data_type: str = 'logic',
        is_synchronized: bool = False,
        pulsing: bool = False,
    ) -> 'SignalProto': ...

    def free_accesses_from_thread(self, thread: 'ThreadProto') -> None: ...


# Protocol mixin, used by Engine and Worker
class _StateManager(Protocol):
    @property
    def state_names(self) -> Set[str]: ...

    def create_state(self, name: Optional[str] = None, allow_assignments: bool = True, metadata: Dict[str, Any] = {}) -> 'StateProto': ...

    @property
    def current_state(self) -> 'StateProto': ...

    @current_state.setter
    def current_state(self, state: 'StateProto') -> None: ...

    @property
    def next_state(self) -> 'StateProto': ...

    @property
    def reset_state(self) -> 'StateProto': ...


class EngineProto(_StateManager, Protocol):
    MAIN_WORKER_NAME: ClassVar[str]
    MAIN_THREAD_NAME: ClassVar[str]

    module_name: str
    state_metadata_template: Dict[str, Any]

    # Tracing
    @property
    def tracer(self) -> 'TracerProto': ...

    # State manegement (+_StateManager)
    @property
    def states(self) -> Mapping[str, Sequence[StateProto]]: ...

    # Worker Managment
    @property
    def workers(self) -> Mapping[str, 'WorkerProto']: ...

    def create_worker(self, name: Optional[str] = None) -> 'WorkerProto': ...

    @property
    def current_worker(self) -> 'WorkerProto': ...

    @current_worker.setter
    def current_worker(self, worker: 'WorkerProto') -> None: ...

    @property
    def main_worker(self) -> 'WorkerProto': ...

    # Thread Managment
    @property
    def current_thread(self) -> 'ThreadProto': ...

    @property
    def main_thread(self) -> 'ThreadProto': ...

    # Signal Managment
    @property
    def signal_manager(self) -> SignalManagerProto: ...

    @property
    def scratch_manager(self) -> ScratchManagerProto: ...

    @property
    def signals(self) -> Mapping[str, 'SignalProto']: ...

    @property
    def combinationals(self) -> Sequence[Tuple['SignalProto', Renderable]]: ...

    def define_input(
        self, name: str, width: Union[int, 'ParameterProto', Renderable] = 1, data_type: str = 'logic', is_synchronized: bool = False
    ) -> 'SignalProto': ...

    def define_output(
        self,
        name: str,
        width: Union[int, 'ParameterProto', Renderable] = 1,
        reset_value: int = 0,
        data_type: str = 'logic',
        value: Union[Renderable, None] = None,
    ) -> 'SignalProto': ...

    def define_local(
        self,
        name: str,
        width: Union[int, 'ParameterProto', Renderable] = 1,
        reset_value: int | None = None,
        data_type: str = 'logic',
        pulsing: bool = False,
        value: Union[Renderable, None] = None,
    ) -> 'SignalProto': ...

    def define_scratch(self, width: int) -> 'ScratchSignalProto': ...

    # Parameter Managment
    @property
    def parameters(self) -> Mapping[str, 'ParameterProto']: ...

    def define_parameter(self, name: str, default_value: int = 0, width: Optional[int] = None) -> 'ParameterProto': ...

    # Setting outputs
    def set(self, signal: AssignmentTarget, level: Union[Renderable, int, bool]) -> None: ...

    def set_once(self, signal: AssignmentTarget, level: Union[Renderable, int, bool], reset_level: Union[Renderable, int, bool] = False) -> None: ...

    def sync(self) -> None: ...

    def wait_for(self, condition: Renderable) -> None: ...

    def jump_if(self, condition: Renderable, true_state: StateProto, false_state: Optional[StateProto] = None) -> None: ...

    # Debugging Prints

    def print(self, line: str, *args: Renderable) -> None: ...

    def printf(self, fname: str, line: str, *args: Renderable) -> None: ...

    # Module Managment
    @property
    def modules(self) -> Mapping[str, 'ModuleProto']: ...

    @property
    def module_instances(self) -> Mapping[str, ModuleInstanceProto]: ...

    def define_module(self, name: str) -> 'ModuleProto': ...

    def add_module(self, module: 'ModuleProto') -> None: ...

    def create_module_instance(self, module_name: str, instance_name: str, clock_gating: bool = False) -> 'ModuleInstanceProto': ...

    def connect_module_port(self, instance_name: str, port_name: str, signal: 'PermanentSignal') -> None: ...

    def override_module_parameter(self, instance_name: str, parameter_name: str, value: Union[int, 'ParameterProto', Renderable]) -> None: ...


class ModuleProto(Protocol):
    _ignore_clk_rst_connection: bool

    @property
    def name(self) -> str: ...

    @property
    def ports(self) -> List[str]: ...
    @property
    def parameters(self) -> Dict[str, int]: ...

    @property
    def hdl_code(self) -> str: ...

    def add_port(self, port_name: str) -> None: ...

    def has_port(self, port_name: str) -> bool: ...

    def add_parameter(self, name: str, value: int) -> None: ...

    def set_clk_request(self, port_name: str) -> None: ...

    @property
    def clk_request_port(self) -> Optional[str]: ...


# Access checks
class StaticAccessProto(Protocol):
    thread: 'ThreadProto'
    active: bool

    def disable(self) -> None: ...


class StaticAccessCheckerProto(Protocol):
    @property
    def reading_thread_names(self) -> Set[str]: ...

    @property
    def writing_thread_names(self) -> Set[str]: ...

    @property
    def all_checks_enabled(self) -> bool: ...

    def disable_check(self, check: SIGNAL_ACCESS_CHECKS) -> None: ...

    def check(self, ignore: Set[ACCESS_CHECKS] = set()) -> None: ...


# Signals
class _BaseSignalProto(AssignmentTarget, Protocol):
    @property
    def _is_synchronized(self) -> bool: ...

    @property
    def type(self) -> SIGNAL_TYPES: ...

    @property
    def pulsing(self) -> bool: ...

    @property
    def escaped_name(self) -> str: ...

    @property
    def width(self) -> Union[int, 'ParameterProto', Renderable]: ...

    @property
    def data_type(self) -> str: ...

    # Access Control
    @property
    def read_accesses(self) -> Set[StaticAccessProto]: ...

    @property
    def write_accesses(self) -> Set[StaticAccessProto]: ...

    @property
    def last_read_access_thread(self) -> Optional['ThreadProto']: ...

    @last_read_access_thread.setter
    def last_read_access_thread(self, value: 'ThreadProto') -> None: ...

    @property
    def last_write_access_thread(self) -> Optional['ThreadProto']: ...

    @last_write_access_thread.setter
    def last_write_access_thread(self, value: 'ThreadProto') -> None: ...

    @property
    def access_checker(self) -> StaticAccessCheckerProto: ...

    def free_access_from_thread(self, thread: 'ThreadProto') -> None: ...


class _EventSourceSignalProto(Generic[T_Signal], Protocol):
    def rising(self) -> T_Signal: ...

    def falling(self) -> T_Signal: ...

    def delayed(self, cycles: Union[int, 'ParameterProto'] = 1) -> T_Signal: ...

    def synchronized(self) -> T_Signal: ...


class _BaseSliceProto(_BaseSignalProto, Protocol):
    @property
    def base_signal(self) -> 'SignalProto': ...

    @property
    def index(self) -> Union[int, IntSlice]: ...

    def __getitem__(self, index: Union[int, IntSlice]) -> Self: ...


class SignalProto(_EventSourceSignalProto['SignalProto'], _BaseSignalProto, Protocol):
    def __getitem__(self, index: Union[int, IntSlice]) -> 'SignalSliceProto': ...


class SignalSliceProto(_BaseSliceProto, _EventSourceSignalProto['SignalSliceProto'], Protocol):
    def as_scratch_signal(self, zone: Optional[MemoryZoneProto] = None) -> 'ScratchSignalProto': ...


class ScratchSignalProto(_BaseSliceProto, ContextManager['ScratchSignalProto'], Protocol):
    creator_frames: Sequence[FrameInfo]

    @property
    def owner(self) -> 'ThreadProto': ...

    @property
    def zone(self) -> MemoryZoneProto: ...

    def enter_context(self) -> None: ...

    def exit_context(self) -> None: ...

    @property
    def released(self) -> bool: ...

    def release(self, force: bool = False) -> None: ...

    def reclaim(self) -> None: ...

    def states_disjoint(self, other: Self) -> bool: ...

    def call_stack_similarity(self, other: Self) -> int: ...


# Parameters
class ParameterProto(Renderable, Protocol):
    @property
    def engine(self) -> EngineProto: ...

    @property
    def name(self) -> str: ...

    @property
    def default_value(self) -> int: ...

    @property
    def width(self) -> Optional[int]: ...


# Parallel processing
class WorkerProto(_StateManager, NamedEntityProto, Protocol):
    @property
    def engine(self) -> EngineProto: ...

    @property
    def is_main_worker(self) -> bool: ...

    def create_scoped_name(self, name: str) -> str: ...

    @property
    def sync_reset(self) -> Renderable: ...

    @sync_reset.setter
    def sync_reset(self, value: Renderable) -> None: ...

    # Control Signals for Threads
    @property
    def reset(self) -> SignalProto: ...

    @property
    def start(self) -> SignalProto: ...

    @property
    def select(self) -> SignalProto: ...

    @property
    def idle(self) -> SignalProto: ...

    # State Management
    @property
    def states(self) -> Sequence[StateProto]: ...

    def leave_foreground(self) -> None: ...

    # Thread Management
    @property
    def threads(self) -> Sequence['ThreadProto']: ...

    def create_thread(self, name: Optional[str] = None) -> 'ThreadProto': ...

    @property
    def working(self) -> bool: ...

    @property
    def current_thread(self) -> 'ThreadProto': ...

    # Misc.
    def raise_reset(self) -> None: ...

    def clear_reset(self) -> None: ...


class ThreadProto(NamedEntityProto, Protocol):
    @property
    def engine(self) -> EngineProto: ...

    @property
    def worker(self) -> WorkerProto: ...

    @property
    def is_main_thread(self) -> bool: ...

    @property
    def active(self) -> bool: ...
    @active.setter
    def active(self, value: bool) -> None: ...

    _spawned_threads: List[Self]
    parent_thread: Optional[Self]

    def join(self) -> None: ...

    @property
    def finished(self) -> Renderable: ...

    @property
    def running(self) -> bool: ...

    def cancel(self) -> None: ...

    def finish(self) -> None: ...

    @property
    def call_stack(self) -> List[Self]: ...


class TracerProto(Protocol):
    def add_metadata(self, target: NamedEntityProto, key: str, profile: bool = False) -> None: ...

    def format_metadata(self, target: NamedEntityProto, key: str) -> str: ...

    @property
    def current_trace(self) -> Sequence[FrameInfo]: ...
