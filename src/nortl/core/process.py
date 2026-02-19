import math
from typing import Any, Dict, List, Optional, Sequence, Set

from typing_extensions import Self

from nortl.core.exceptions import OwnershipError, UnfinishedForwardDeclarationError

from .common import NamedEntity
from .modifiers import Volatile
from .operations import Const, Var
from .protocols import EngineProto, Renderable, SignalProto, StateProto, WorkerProto
from .state import State


class Worker(NamedEntity):
    """Worker for noRTL engine.

    Each worker represents a state machine, that runs independently from the others.
    The workers store their states. Creating state transitions between different workers is not possible.

    The noRTL engine contains one main worker by default. Additional workers can be created manually.
    The main worker is responsible for managing the reset state for all signals; the other workers do not contain any assignments in the reset state.

    Each worker must have one or more threads.
    """

    def __init__(self, engine: EngineProto, name: str, reset_state_name: str = 'IDLE') -> None:
        """Initialize a new Worker.

        Arguments:
            engine: noRTL engine.
            name: Name of the worker.
            reset_state_name: Name of the reset state for this worker.

        !!! warning

            Workers are not meant to be instantiated manually. Use the [`CoreEngine.create_worker()`][nortl.core.engine.CoreEngine.create_worker] method instead.
        """
        super().__init__(name)

        self._engine = engine
        self._is_main_worker = name == engine.MAIN_WORKER_NAME

        # State tracking
        self._states: List[State] = []
        self._state_names: Set[str] = set()

        # Thread tracking
        self._threads: List['Thread'] = []  # Threads mapped to this worker

        # Create reset state and set to current state
        self._reset_state = self.create_state(reset_state_name, allow_assignments=self.is_main_worker)
        self._current_state = self.reset_state
        self._next_state: Optional[State] = None

        # Internal control signals
        # The main worker does not use these signals
        self._reset_signal: Optional[Volatile[SignalProto]] = None
        self._start_signal: Optional[Volatile[SignalProto]] = None
        self._select_signal: Optional[Volatile[SignalProto]] = None
        self._idle_signal: Optional[Volatile[SignalProto]] = None
        self._select_signal_width: Optional[Var] = None

        # Synchronous reset, inactive by default
        self._sync_reset: Optional[Renderable] = None

    @property
    def engine(self) -> EngineProto:
        """NoRTL engine for this worker."""
        return self._engine

    @property
    def is_main_worker(self) -> bool:
        """If this worker is the main worker of the noRTL engine."""
        return self._is_main_worker

    def create_scoped_name(self, name: str) -> str:
        """Create scoped name for signals or other things.

        If this worker is not the main worker, the name is prefixed with the name of the worker.
        """
        # FIXME decide if worker prefix is omitted for main worker
        if not self.is_main_worker and not name.startswith(self.name):
            name = f'{self.name}_{name}'
        return name

    @property
    def sync_reset(self) -> Renderable:
        """Synchronous reset for worker."""
        if self._sync_reset is None:
            return Const(0)
        return self._sync_reset

    @sync_reset.setter
    def sync_reset(self, value: Renderable) -> None:
        """Synchronous reset for worker."""
        if self._sync_reset is not None:
            raise RuntimeError(f'Synchronous reset for worker {self.name} was already set to {self.sync_reset}.')
        self._sync_reset = value

    # Control Signals for Threads
    # FIXME technically, these signals are only required for Fork/Join management. They serve no purpose for raw Worker + Thread
    @property
    def reset(self) -> SignalProto:
        """Control signal to reset worker.

        If the worker control signal is used, it is automatically added to the synchronous reset.
        """
        if self.is_main_worker:
            raise RuntimeError('Main worker does not use reset signal.')
        elif self._reset_signal is None:
            self._initialize_control_signals()
        return self._reset_signal  # type: ignore[return-value]

    @property
    def start(self) -> SignalProto:
        """Control signal to start worker."""
        if self.is_main_worker:
            raise RuntimeError('Main worker does not use start signal.')
        elif self._start_signal is None:
            self._initialize_control_signals()
        return self._start_signal  # type: ignore[return-value]

    @property
    def select(self) -> SignalProto:
        """Control signal that selects a thread."""
        if self.is_main_worker:
            raise RuntimeError('Main worker does not use select signal.')
        elif self._select_signal is None:
            self._initialize_control_signals()
        return self._select_signal  # type: ignore[return-value]

    @property
    def idle(self) -> SignalProto:
        """Status signal that indicates if the worker is in it's idle state."""
        if self.is_main_worker:
            raise RuntimeError('Main worker does not use idle signal.')
        elif self._idle_signal is None:
            self._initialize_control_signals()
        return self._idle_signal  # type: ignore[return-value]

    def _initialize_control_signals(self) -> None:
        """Initializes built-in signals for the worker."""

        # Local Signals
        self._reset_signal = Volatile(
            self.engine.define_local(self.create_scoped_name('reset'), width=1, reset_value=0, pulsing=True), 'identical_rw', 'exclusive_write'
        )
        self._start_signal = Volatile(
            self.engine.define_local(self.create_scoped_name('start'), width=1, reset_value=0, pulsing=True), 'identical_rw', 'exclusive_write'
        )
        self._select_signal_width = Var(self._get_select_width())
        self._select_signal = Volatile(
            self.engine.define_local(self.create_scoped_name('select'), width=self._select_signal_width, reset_value=0),
            'identical_rw',
            'exclusive_write',
        )

        # the following signal has to be set to zero once a thread is started:
        # FIXME: Set signal to zero and to one after first state
        self._idle_signal = Volatile(self.engine.define_local(self.create_scoped_name('idle'), reset_value=1), 'identical_rw', 'exclusive_write')

        # Tie synchrounous reset to the new reset signal
        self.sync_reset = self.reset

    def _get_select_width(self) -> int:
        """Calculate necessary width for thread select signal."""
        return math.ceil(math.log2(len(self.threads)) + 1)

    def _resize_select_signal(self) -> None:
        """Updates the internal signal width of the select variable."""
        if self._select_signal_width is not None:
            self._select_signal_width.update(self._get_select_width())

    # State management
    @property
    def states(self) -> Sequence[State]:
        """List of states for this worker."""
        return self._states

    @property
    def state_names(self) -> Set[str]:
        """Set of the names of all states for this worker."""
        return self._state_names

    def create_state(self, name: Optional[str] = None, allow_assignments: bool = True, metadata: Dict[str, Any] = {}) -> State:
        """Create a state.

        Arguments:
            name: Optional state name. If no name is provided, it defaults to '<worker_name>_STATE_<id>', where 'id' is the current number of states
                for the worker and 'worker_name' is the name of this worker.

                If this worker is not the main worker, the name of the state must be prefixed with the name of the current worker.
                The prefix is automatically added, if missing.
            allow_assignments: If the state allows assignments. This is used for internal purposes.
            metadata: The metadata that will be added to the newly created state. If not given, the engine's state_metadata_template will be used.

        Returns:
            The created state.
        """
        # Generate default state name
        if name is None:
            name = f'STATE_{len(self.states)}'

        if len(self.states) > 0 and len(self.threads) == 0:
            raise RuntimeError('Worker has no thread, unable to create new states.')

        # Use engine's metadata template if no metadata is provided
        if metadata == {}:
            metadata = self.engine.state_metadata_template

        # State will validate the name
        state = State(self, name, allow_assignments=allow_assignments)

        # Store given metadata in state
        for k, v in metadata.items():
            state.set_metadata(k, v)

        self._states.append(state)
        return state

    @property
    def current_state(self) -> State:
        """Current state.

        Returns:
            The current state.
        """
        return self._current_state

    @current_state.setter
    def current_state(self, state: StateProto) -> None:
        """Current state.

        Arguments:
            state: The new current state.

        Raises:
            UnfinishedForwardDeclarationError: If the next state has been forward-declared and is different from the new current state.
        """
        if state.engine is not self.engine:
            raise OwnershipError('State does not belong to this engine.')
        if state not in self.states:
            raise OwnershipError('State does not belong to this worker.')
        if self._next_state is not None and state is not self._next_state:
            raise UnfinishedForwardDeclarationError(
                'You have forward-declared the next state (by using next_state), but are now trying to set another state as the current one. '
                'This may result in dead-end states and is therefore forbidden. Please switch to the next_state and modify it first.'
            )
        if state is not self.current_state:
            self._next_state = None  # Clear next state
        self._current_state = state  # type: ignore[assignment]

    @property
    def next_state(self) -> State:
        """Forward-declared next state.

        This simplifies the creation of new states for non-branching sections of the state graph (e.g. via sync() or wait_for()).
        When you use next_state you must set it as current_state, before you can set any other state.

        Returns:
            The forward-declared next state.
        """
        if self._next_state is None:
            self._next_state = self.create_state()

        return self._next_state

    @property
    def reset_state(self) -> State:
        """The reset state of the engine.

        This is the initial state from which the engine will start.

        Returns:
            The reset state.
        """
        return self._reset_state

    def leave_foreground(self) -> None:
        """This method must be called when the current worker of the engine is changed.

        Checks if the any forward-declared next-state pending.
        """
        if self._next_state is not None:
            raise UnfinishedForwardDeclarationError(
                'You have forward-declared the next state for the current worker (by using next_state), but are now trying to set another worker as the current one. '
                'This may result in dead-end states and is therefore forbidden. Please finish the current worker first, by switching to the next_state and modifying it.'
            )

    # Thread Management
    @property
    def threads(self) -> Sequence['Thread']:
        """Stack of worker threads."""
        return self._threads

    def create_thread(self, name: Optional[str] = None) -> 'Thread':
        """Create a new thread.

        Arguments:
            name: Name of the thread.

        Returns:
            The created thread.
        """
        # Generate default name
        if name is None:
            if len(self.threads) == 0:
                name = self.engine.MAIN_THREAD_NAME
            else:
                name = f'thread_{len(self.threads)}'

        thread = Thread(self, name)
        self._threads.append(thread)

        if not self.is_main_worker:
            self._resize_select_signal()  # Adjust width of select signal
        return thread

    @property
    def current_thread(self) -> 'Thread':
        """Current thread for this worker."""
        if len(self.threads) == 0:
            raise RuntimeError('Worker has no threads.')
        return self.threads[-1]

    @property
    def working(self) -> bool:
        """If the worker is working."""
        return any([t.running for t in self.threads])

    # Misc.
    # FIXME these helper methods are only used by Fork/Join
    def raise_reset(self) -> None:
        self.engine.set(self.reset, 1)

    def clear_reset(self) -> None:
        self.engine.set(self.reset, 0)
        self.engine.set(self.idle, 1)


class Thread(NamedEntity):
    """Thread for noRTL engine.

    Threads are used to control signal ownership.
    They prevent simultaneous access to signals from two workers, that would cause wrong behavior.
    """

    def __init__(self, worker: WorkerProto, name: str) -> None:
        """Initialize a new thread.

        Arguments:
            worker: Worker for this thread.
            name: Name of the thread.

        !!! warning

            Threads are not meant to be instantiated manually. Use the [`Worker.create_thread()`][nortl.core.process.Worker.create_thread] method instead.
        """
        super().__init__(name)

        self._worker: WorkerProto = worker
        self._is_main_thread = worker.is_main_worker
        self._active: bool = self.is_main_thread  # Main thread is always active

        self._spawned_threads: List[Self] = []

        # Link back the parent thread
        self.parent_thread: Optional[Self] = None
        if name != worker.engine.MAIN_THREAD_NAME:
            self.parent_thread = self.worker.engine.current_thread  # type: ignore[assignment]

    @property
    def engine(self) -> EngineProto:
        """NoRTL engine for this thread."""
        return self.worker.engine

    @property
    def worker(self) -> WorkerProto:
        """Engine worker."""
        return self._worker

    @property
    def is_main_thread(self) -> bool:
        """If this thread is the main thread of the noRTL engine."""
        return self.worker.is_main_worker

    @property
    def active(self) -> bool:
        """If this thread is currently active."""
        # FIXME decide if activity can be tracked automatically
        return self._active

    @active.setter
    def active(self, value: bool) -> None:
        """If this thread is currently active."""
        if self.is_main_thread:
            raise RuntimeError('Main thread cannot be deactivated.')
        self._active = value

    def join(self) -> None:
        """Join a thread.

        This waits for the thread to be finished.
        """
        self.engine.wait_for(self.finished)
        self.active = False
        self.engine.scratch_manager.force_release_signals_by_thread(self)
        self.engine.signal_manager.free_accesses_from_thread(self)

    @property
    def finished(self) -> Renderable:
        return self.worker.idle

    @property
    def running(self) -> bool:
        if self.parent_thread == self.engine.current_thread:
            return self.active

        if self.active:
            return True

        global_call_stack = self.engine.current_thread.call_stack

        for t in self.call_stack:
            if t not in global_call_stack:
                if t.active:
                    return True

        return False

    def cancel(self) -> None:
        """This method sends a synchronous reset to the Thread's worker and recursively to all threads, that are spawned from this thread."""
        for subthread in self._spawned_threads:
            subthread.cancel()

        self.worker.raise_reset()
        self.engine.sync()
        self.worker.clear_reset()
        self.engine.sync()

        self.active = False
        self.engine.scratch_manager.force_release_signals_by_thread(self)
        self.engine.signal_manager.free_accesses_from_thread(self)

    def finish(self) -> None:
        """Finishes a Thread."""
        self.engine.jump_if(Const(1), self.worker.reset_state)
        self.engine.set(self.worker.idle, 1)

    @property
    def call_stack(self) -> List[Self]:
        ret = []

        thread = self

        while thread.parent_thread is not None:
            ret.append(thread.parent_thread)
            thread = thread.parent_thread

        return ret
