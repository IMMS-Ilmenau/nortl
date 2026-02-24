"""Core Engine."""

from typing import Any, ClassVar, Dict, Mapping, Optional, Sequence, Set, Tuple, Union

from nortl.core.exceptions import OwnershipError, TransitionLockError, read_access, write_access
from nortl.core.manager import ScratchManager, SignalManager
from nortl.core.module import Module, ModuleInstance
from nortl.core.operations import Const, to_renderable
from nortl.core.parameter import Parameter
from nortl.core.process import Thread, Worker
from nortl.core.protocols import AssignmentTarget, ModuleProto, PermanentSignal, Renderable, Selector, StateProto, WorkerProto
from nortl.core.signal import ScratchSignal, Signal, SignalSlice
from nortl.core.state import State, selector_to_renderable
from nortl.core.tracing import Tracer

__all__ = [
    'CoreEngine',
]


class CoreEngine:
    """This class represents a Verilog module that realizes a noRTL engine.

    The construction idea of this class is, that a noRTL engine can be described using the following lists:

    * A set of ports, signals, parameters and submodules
    * A set of states
    * Each state has
        * a set of assignments of the form "<signal> = <statement>"
        * a set of conditions that describe the transition next states

    Since we want to also enable parallel running engines, it is necessary to organize the states in a dictionary.
    The dictionaries keys represent the thread and the state lists represent the states of the realized engine.
    By default, we start with a main thread.

    This class only realizes the features needed to create state machines. Events on signals have to be handled on the next level of abstraction.
    """

    MAIN_WORKER_NAME: ClassVar[str] = 'main'
    MAIN_THREAD_NAME: ClassVar[str] = 'main'

    def __init__(self, module_name: str, reset_state_name: str = 'IDLE'):
        """Initialize a engine.

        Arguments:
            module_name: Verilog module name.
            reset_state_name: Name of the reset state.
        """
        self.module_name = module_name
        self._reset_state_name = reset_state_name

        # Create tracer
        self._tracer = Tracer(self)

        # Parameters, signals and scratch signals
        self._parameters: Dict[str, Parameter] = dict()
        self._signal_manager = SignalManager(self)
        self._scratch_manager = ScratchManager(self)
        self._modules: Dict[str, Module] = {}
        self._module_instances: Dict[str, ModuleInstance] = {}
        self.state_metadata_template: Dict[str, Any] = {}

        # Workers
        self._workers: Dict[str, Worker] = {}

        # Create main worker
        self._main_worker = self.create_worker(self.MAIN_WORKER_NAME)
        self._current_worker = self.main_worker

        # Create main thread
        self._main_thread = self.main_worker.create_thread(self.MAIN_THREAD_NAME)

    # Tracing
    @property
    def tracer(self) -> Tracer:
        """Tracer for diagnostic information."""
        return self._tracer

    # State management
    @property
    def states(self) -> Mapping[str, Sequence[State]]:
        """All states of the engine.

        Contains a list of the states for each worker. They are stored in a dictionary and indexed with the worker name.
        """
        return {name: worker.states for name, worker in self.workers.items()}

    @property
    def state_names(self) -> Set[str]:
        """Set of the names of all states for this engine."""
        return set().union(*(worker.state_names for worker in self.workers.values()))

    def create_state(self, name: Optional[str] = None, allow_assignments: bool = True, metadata: Dict[str, Any] = {}) -> State:
        """Create a new state for the current worker.

        Arguments:
            name: Optional state name. If no name is provided, it defaults to '<current_worker>_STATE_x', where 'x' is the current number of states
                for the worker.

                If the current worker is not the main worker, the name of the state must be prefixed with the name of the current worker.
                The prefix is automatically added, if missing.
            allow_assignments: If the state allows assignments. This is used for internal purposes.
            metadata: Metadatafor the new state. If not given, the current self.state_metadata_template will be used.

        Returns:
            The created state.
        """
        if metadata == {}:
            metadata = self.state_metadata_template
        return self.current_worker.create_state(name=name, allow_assignments=allow_assignments, metadata=metadata)

    @property
    def current_state(self) -> State:
        """Current state.

        Returns:
            The current state.
        """
        return self.current_worker.current_state

    @current_state.setter
    def current_state(self, state: StateProto) -> None:
        """Current state.

        Arguments:
            state: The new current state.

        Raises:
            UnfinishedForwardDeclarationError: If the next state has been forward-declared and is different from the new current state.
        """
        self.current_worker.current_state = state

    @property
    def next_state(self) -> State:
        """Forward-declared next state.

        This simplifies the creation of new states for non-branching sections of the state graph (e.g. via sync() or wait_for()).
        When you use next_state you must set it as current_state, before you can set any other state.

        Returns:
            The forward-declared next state.
        """
        return self.current_worker.next_state

    @property
    def reset_state(self) -> State:
        """The reset state of the current worker.

        This is the initial state from which the current worker will start.

        Returns:
            The reset state.
        """
        return self.current_worker.reset_state

    # Worker management
    @property
    def workers(self) -> Mapping[str, Worker]:
        """Mapping of workers."""
        return self._workers

    def create_worker(self, name: Optional[str] = None) -> Worker:
        """Create a new worker.

        Arguments:
            name: Optional name for the worker. If no name is provided, it defaults to 'WORKER_x', where 'x' is the current number of workers.

        Returns:
            The created worker.
        """
        if name is None:
            name = f'WORKER_{len(self.workers.values())}'
        if name in self.workers:
            raise KeyError(f'Worker {name} already exists.')

        worker = Worker(self, name, reset_state_name=self._reset_state_name)
        self._workers[name] = worker
        return worker

    @property
    def current_worker(self) -> Worker:
        """Current worker."""
        return self._current_worker

    @current_worker.setter
    def current_worker(self, worker: WorkerProto) -> None:
        """Name of the current worker."""
        if worker.engine is not self:
            raise OwnershipError('Worker does not belong to this engine')
        self.current_worker.leave_foreground()
        self._current_worker = worker  # type: ignore[assignment]

    @property
    def main_worker(self) -> Worker:
        """Main worker."""
        return self._main_worker

    # Thread management
    @property
    def current_thread(self) -> Thread:
        """Current worker thread."""
        return self.current_worker.current_thread

    @property
    def main_thread(self) -> Thread:
        """Main thread."""
        return self._main_thread

    # Signal management
    @property
    def signal_manager(self) -> SignalManager:
        """Signal manager."""
        return self._signal_manager

    @property
    def scratch_manager(self) -> ScratchManager:
        """Scratch manager."""
        return self._scratch_manager

    @property
    def signals(self) -> Mapping[str, Signal]:
        """Mapping of signals."""
        return self.signal_manager.signals

    @property
    def combinationals(self) -> Sequence[Tuple[Signal, Renderable]]:
        """Sequence of combinational signal assignments."""
        return self.signal_manager.combinationals

    def define_input(
        self, name: str, width: Union[int, Parameter, Renderable] = 1, data_type: str = 'logic', is_synchronized: bool = False
    ) -> Signal:
        """Define an input signal.

        Arguments:
            name: Name of the signal.
            width: Width of the signal in bits.
            data_type: Data type of the signal.
            is_synchronized: If the signal is synchronous to the used clock domain

        Returns:
            The defined input signal.
        """
        return self.signal_manager.create_signal('input', name, width=width, data_type=data_type, is_synchronized=is_synchronized)

    def define_output(
        self,
        name: str,
        width: Union[int, Parameter, Renderable] = 1,
        reset_value: int = 0,
        data_type: str = 'logic',
        value: Union[Renderable, None] = None,
    ) -> Signal:
        """Define an output signal.

        The noRTL engine implements two variants of output ports: Registers and continuous / combinational assigns.
        Regsiters can be set in different states and combinational assigns are assigned statically.

        Arguments:
            name: Name of the signal.
            width: Width of the signal in bits.
            reset_value: Reset value of the signal (only for registers).
            data_type: Data type of the signal.
            value: Value that should be assigned continuously (only for combinational assigns).

        Returns:
            The defined output signal.
        """
        if value is None:
            # Register
            signal = self.signal_manager.create_signal('output', name, width=width, data_type=data_type, is_synchronized=True)
            self.main_worker.reset_state.add_assignment(signal, to_renderable(reset_value))
        else:
            # Combinational assign
            signal = self.signal_manager.create_signal(
                'output', name, width=width, data_type=data_type, is_synchronized=True, assignment=to_renderable(value)
            )
        return signal

    def define_local(
        self,
        name: str,
        width: Union[int, Parameter, Renderable] = 1,
        reset_value: int | None = None,
        data_type: str = 'logic',
        pulsing: bool = False,
        value: Union[Renderable, None] = None,
    ) -> Signal:
        """Define a local signal.

        Arguments:
            name: Name of the signal.
            width: Width of the signal in bits.
            reset_value (int | None): Reset value (if applicable)
            data_type: Data type of the signal.
            pulsing: If true, the signal automatically resets to zero if not set in the current state
            value: value that should be assigned continuously (only for combinational assigns)

        Returns:
            The defined local signal.
        """
        if value is None:
            signal = self.signal_manager.create_signal('local', name, width=width, data_type=data_type, is_synchronized=True, pulsing=pulsing)
            if reset_value is not None:
                self.main_worker.reset_state.add_assignment(signal, to_renderable(reset_value))
        else:
            # Combinational assign
            signal = self.signal_manager.create_signal(
                'local', name, width=width, data_type=data_type, is_synchronized=True, assignment=to_renderable(value)
            )
        return signal

    def define_scratch(self, width: int) -> ScratchSignal:
        """Define a scratch signal.

        Arguments:
            width: Width of the signal in bits.
        """
        return self.scratch_manager.create_signal(width)

    # Parameter Managment
    @property
    def parameters(self) -> Mapping[str, Parameter]:
        """Mapping of parameters."""
        return self._parameters

    def define_parameter(self, name: str, default_value: int = 0, width: Optional[int] = None) -> Parameter:
        """Defines a parameter for the engine that can be passed on to module instances.

        Note that the only supported datatype for the parameter is int!

        Arguments:
            name: Name of the parameter
            default_value: Value of the parameter. Defaults to 0.
            width: Optional width for the parameter.

        Returns:
            Parameter: Parameter object
        """
        if name in self.signals:
            raise KeyError(f'Parameter name {name} collides with existing signal name.')
        if name in self.parameters:
            raise KeyError(f'Parameter {name} already exists.')

        parameter = Parameter(self, name, default_value, width=width)
        self._parameters[name] = parameter
        return parameter

    # Setting outputs
    def set(self, signal: AssignmentTarget, level: Union[Renderable, int, bool]) -> None:
        """Set level of an output signal.

        This is non-blocking, you can set multiple signals at the same time.
        Use sync(), wait_for() or jump_if() to apply all signals and move to the next state.

        Arguments:
            signal: The signal to be set.
            level: The level to which the signal is set.

        Raises:
            TypeError: If the signal is not a noRTL signal.
            OwnershipError: If the signal does not belong to this noRTL engine.
            ConflictingAssignmentError: If the assignment overlaps with another assignment.
        """
        if not hasattr(signal, 'write_access'):
            raise TypeError(f'{signal} is not a valid assignment target.')
        if signal.name not in self.signals or signal.engine is not self:
            raise OwnershipError(f"Signal '{signal.name}' does not belong to this engine.")

        self.current_state.add_assignment(write_access(signal), read_access(to_renderable(level)))

    def set_when(self, signal: AssignmentTarget, selector: Selector, allow_short_circuit: bool = False) -> None:
        """Set level of an output signal based on a selection of conditions.

        This is non-blocking, you can set multiple signals at the same time.
        Use sync(), wait_for() or jump_if() to apply all signals and move to the next state.

        Arguments:
            signal: The signal to be set.
            selector: Mapping of conditions to levels. When a condition is met, the signal is set to this level.
                If no condition is met, the signal is not updated. The conditions are processed in order, from top to bottom

                It is possible to define a default/fallback value by providing an entry named `'default'` in the selector.
                If no condition is met, the signal is set to the default level.
                Providing a `'default'` will treat the selector cases as being in prioritized order.
                This renders the expression as a `priority if` statement in Verilog, instead of a regular `if`, if this is enabled in the
                VerilogRenderer.
                Otherwise, the expression is treated as `unique if`. This means, that only one case at a time must be valid, but the cases may be
                treated in unsorted order by the synthesis tools.

                The level can also be a selector on its own (sub-selector), creating a nested nested.
                Note that the `'default'` value only applies to the selector mapping where it is defined, not to nested sub-selectors.
            allow_short_circuit: If the selector is not in prioritized order (because no `'default'` is provided), but one condition is found to be
                always True, the other conditions would be unreachable. This is a violation of the rules of `unique if`.
                If `allow_short_circuit` is True, noRTL will remove all other conditions, and only keep the always-True condition.
                If it is False , noRTL will raise an exception to avoid downstream issues in the Verilog code.

        !!! warning
            Selector assignments bypass the check for conflicting assignments, if there is a partial overlap between two unconditional assignment!

            This means, if two overlapping slices of the same signals have conditional assignments, no [ConflictingAssignmentError][nortl.core.exceptions.ConflictingAssignmentError] is raised.


        Example:
            The following example defines a 2x2 Input AND into 2-Input OR gate.

            ```python
            engine = CoreEngine('my_engine')

            ao22 = engine.define_output('ao22', reset_value=0)
            a = engine.define_input('a')
            b = engine.define_input('b')
            c = engine.define_input('c')
            d = engine.define_input('d')

            engine.set_when(
                ao22,
                {
                    (a & b): 1,
                    (c & d): 1,
                    'default': 0,
                },
            )
            ```

            The example roughly translates to this Verilog code:

            ```verilog
            priority
            if ((a & b) == 1)
                ao22 <= 1;
            else
            if ((c & d) == 1)
                ao22 <= 1;
            else
                ao22 <= 0;
            ```

        Raises:
            TypeError: If the signal is not a noRTL signal.
            OwnershipError: If the signal does not belong to this noRTL engine.
            ConflictingAssignmentError: If the selector assignment fully overlaps with another assignment or if it partially overlaps with an unconditional assignment.
        """
        if not hasattr(signal, 'write_access'):
            raise TypeError(f'{signal} is not a valid assignment target.')
        if signal.name not in self.signals or signal.engine is not self:
            raise OwnershipError(f"Signal '{signal.name}' does not belong to this engine.")

        self.current_state.add_selector_assignment(
            write_access(signal), read_access(selector_to_renderable(selector)), allow_short_circuit=allow_short_circuit
        )

    def set_once(self, signal: AssignmentTarget, level: Union[Renderable, int, bool], reset_level: Union[Renderable, int, bool] = False) -> None:
        """Set level of an output signal for current state, reset it in next state.

        This is non-blocking, you can set multiple signals at the same time.
        Use sync(), wait_for() or jump_if() to apply all signals and move to the next state.

        Using this method will declare the next state. The current state will be restricted to a single transition to the next state.
        You cannot create multiple transitions to other states.
        If you need to do this, use the regular set() method to set signals in this state, and reset them in others.

        Arguments:
            signal: The signal to be set.
            level: The level to which the signal is set.
            reset_level: The level to which the signal is reset in the next state.

        Raises:
            TypeError: If the signal is not a noRTL signal.
            OwnershipError: If the signal does not belong to this noRTL engine.
        """
        if not hasattr(signal, 'write_access'):
            raise TypeError(f'{signal} is not a valid assignment target.')
        if signal.name not in self.signals or signal.engine is not self:
            raise OwnershipError(f"Signal '{signal.name}' does not belong to this engine.")

        self.current_state.add_assignment(write_access(signal), read_access(to_renderable(level)))
        self.next_state.add_assignment(signal, read_access(to_renderable(reset_level)))
        # Restrict transitions
        self.current_state._restrict_transition(self.next_state)

    # Creating transitions to other states
    def sync(self) -> None:
        """Synchronize outputs.

        This creates a new state and sets it as new current state.
        It also locks the transitions for the current state. You cannot add any more transitions to it.
        """
        self.current_state._add_transition(Const(True), self.next_state)
        self.current_state._lock_transitions()
        self.current_state = self.next_state

    def wait_for(self, condition: Renderable) -> None:
        """Wait until a condition is met.

        This creates a new state and sets it as new current state.
        It also locks the transitions for the current state. You cannot add any more transitions to it.

        Arguments:
            condition: The condition to wait for.

        Raises:
            ValueError: If the condition is not a Renderable instance.
            KeyError: If the condition signal does not exist in the current engine.
        """
        if not hasattr(condition, 'render'):
            raise ValueError('Condition must be a Renderable instance')
        try:
            condition.render()
        except AttributeError:
            raise KeyError(f"Condition '{condition}' does not exist in this engine.")
        if self.current_state.transitions:
            raise TransitionLockError('wait_for() cannot be used in combination with other conditional transitions.')

        self.current_state._add_transition(read_access(to_renderable(condition)), self.next_state)
        self.current_state._lock_transitions()
        self.current_state = self.next_state

    def jump_if(self, condition: Renderable, true_state: StateProto, false_state: Optional[StateProto] = None) -> None:
        """Jump to a certain state, if condition is met.

        If the condition is not met, the engine stays in this state. jump_if can be used multiple times, as long as false_state is omitted.
        The conditions will be evaluated in the order in which they are defined.

        If false_state is provided, a transition to this state will be added.
        After you have used jump_if with a false_state, you can no longer add more transistions.

        This method will not create new states and stay at the current state. You need to manually define the states provided to true_state or false_state.

        Arguments:
            condition: The condition to jump if.
            true_state: The state to jump to if the condition is met.
            false_state: The state to jump to if the condition is not met.

        Raises:
            ValueError: If the condition is not a Renderable instance.
            KeyError: If the condition signal does not exist in the current engine.
        """
        if not hasattr(condition, 'render'):
            raise ValueError('Condition must be a Renderable instance')
        try:
            condition.render()
        except AttributeError:
            raise KeyError(f"Condition '{condition}' does not exist in this engine.")

        if true_state not in self.current_worker.states:
            raise ValueError('Target state does not exist in current thread')

        if false_state is not None:
            if false_state not in self.current_worker.states:
                raise ValueError('Target state does not exist in current thread')

        self.current_state._add_transition(read_access(to_renderable(condition)), true_state)

        if false_state is not None:
            self.current_state._add_transition(to_renderable(~condition), false_state)
            self.current_state._lock_transitions()

    # Debugging Prints
    def print(self, line: str, *args: Renderable) -> None:
        """Adds a line to the print list of the current state that will be processed during simulation."""
        self.current_state.print(line, *args)

    def printf(self, fname: str, line: str, *args: Renderable) -> None:
        """Store an item that will be output to a file during simulation."""
        self.current_state.printf(fname, line, *args)

    # Module definition
    @property
    def modules(self) -> Mapping[str, Module]:
        """Mapping of available modules this engine."""
        return self._modules

    @property
    def module_instances(self) -> Mapping[str, ModuleInstance]:
        """Mapping of module instances for this engine."""
        return self._module_instances

    def define_module(self, name: str) -> Module:
        """Define a new module.

        Arguments:
            name: Name of the module.

        Returns:
            The defined module.

        Raises:
            KeyError: If a module with the same name already exists.
        """
        if name in self.modules:
            raise KeyError(f'Module {name} already exists.')
        module = Module(name)
        self._modules[name] = module
        return module

    def add_module(self, module: ModuleProto) -> None:
        """Add a module from a library.

        Arguments:
            module: The module to be added.

        Raises:
            KeyError: If a module with the same name already exists.
        """
        if module.name in self.modules:
            raise KeyError(f'Module {module.name} already exists.')
        self._modules[module.name] = module  # type: ignore[assignment]

    def create_module_instance(self, module_name: str, instance_name: str, clock_gating: bool = False) -> ModuleInstance:
        """Create a new instance of a module.

        Arguments:
            module_name: Name of the module.
            instance_name: Name of the instance.
            clock_gating: If the unit is to be included in clock gating (if clock gating is enabled)

        Returns:
            The created module instance.

        Raises:
            KeyError: If the module does not exist or if an instance with the same name already exists.
        """
        if module_name not in self.modules:
            raise KeyError(f'Module {module_name} does not exist.')
        if instance_name in self.module_instances:
            raise KeyError(f'Module instance {instance_name} already exists.')
        module = self.modules[module_name]
        instance = ModuleInstance(module, instance_name, clock_gating=clock_gating)
        self._module_instances[instance_name] = instance
        return instance

    def connect_module_port(self, instance_name: str, port_name: str, signal: PermanentSignal) -> None:
        """Connect a port of a module instance to a signal.

        Arguments:
            instance_name: Name of the instance.
            port_name: Name of the port.
            signal: The signal to be connected.

        Raises:
            KeyError: If the instance or port does not exist.
            TypeError: If the signal is not a signal or signal slice. Scratch signals cannot be connected to modules.
            ValueError: If the port does not exist in the module.
        """
        if instance_name not in self.module_instances:
            raise KeyError(f'Module instance {instance_name} does not exist.')
        if not isinstance(signal, (Signal, SignalSlice)):
            raise TypeError(f'Signal {signal} can not be connected to a module port.')
        instance = self.module_instances[instance_name]

        if not instance.module.has_port(port_name):
            raise ValueError(f'Port {port_name} does not exist in module instance {instance_name}.')

        instance.connect_port(port_name, signal)

    def override_module_parameter(self, instance_name: str, parameter_name: str, value: Union[int, Parameter, Renderable]) -> None:
        """Override a parameter of a module instance.

        Arguments:
            instance_name: Name of the instance.
            parameter_name: Name of the parameter.
            value: New value of the parameter.

        Raises:
            KeyError: If the instance or parameter does not exist.
        """
        if instance_name not in self.module_instances:
            raise KeyError(f'Module instance {instance_name} does not exist.')
        instance = self.module_instances[instance_name]
        instance.override_parameter(parameter_name, value)
