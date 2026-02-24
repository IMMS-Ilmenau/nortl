"""Describes engine states as Python object."""

from abc import ABCMeta, abstractmethod
from typing import Dict, Final, Iterable, Iterator, List, Literal, Mapping, Optional, Sequence, Set, Tuple, Union

from typing_extensions import Self

from nortl.core.exceptions import ConflictingAssignmentError, ForbiddenAssignmentError, TransitionLockError, TransitionRestrictionError
from nortl.core.operations import All, Any, to_renderable

from .common import NamedEntity
from .protocols import AssignmentTarget, EngineProto, Renderable, RenderableSelector, Selector, StateProto, WorkerProto

__all__ = [
    'State',
]


class BaseAssignment(metaclass=ABCMeta):
    """Baseclass for assignments."""

    def __init__(self, signal: AssignmentTarget) -> None:
        self.signal = signal


class Assignment(BaseAssignment):
    """Regular assignment."""

    unconditional: Final = True

    def __init__(self, signal: AssignmentTarget, value: Renderable) -> None:
        super().__init__(signal)
        self.value = value

    def __format__(self, format_spec: str) -> str:
        return f'{self.signal} = {self.value}'


class _ConditionalAssignmentMixin(metaclass=ABCMeta):
    @property
    @abstractmethod
    def cases(self) -> Sequence[Tuple[Renderable, Union[Renderable, 'SelectorAssignment']]]:
        pass

    def flatten_cases(self) -> Sequence[Tuple[Renderable, Renderable]]:
        """Flatten cases."""
        result: List[Tuple[Renderable, Renderable]] = []

        for condition, value in self.cases:
            if isinstance(value, SelectorAssignment):
                all_conditions = []
                for sub_condition, sub_value in value.flatten_cases():
                    result.append((All(condition, sub_condition), sub_value))
                    all_conditions.append(sub_condition)

                default_condition = All(condition, ~Any(*all_conditions))
                if isinstance(value.default, SelectorAssignment):
                    for sub_condition, sub_value in value.default.flatten_cases():
                        result.append((All(default_condition, sub_condition), sub_value))
                elif value.default is not None:
                    result.append((default_condition, value.default))
            else:
                result.append((condition, value))
        return result


class ConditionalAssignment(_ConditionalAssignmentMixin, BaseAssignment):
    """Assignment creating a conditional assignment."""

    unconditional: Final = False
    priority: Final = False
    default: Final = None

    def __init__(self, signal: AssignmentTarget, value: Renderable, condition: Renderable) -> None:
        super().__init__(signal)
        self.value = value
        self.condition = condition

    @property
    def cases(self) -> Tuple[Tuple[Renderable, Renderable]]:
        return ((self.condition, self.value),)

    def __format__(self, format_spec: str) -> str:
        return f'{self.signal} = {self.value} if {self.condition}'


class SelectorAssignment(_ConditionalAssignmentMixin, BaseAssignment):
    """Assignment creating a selector expression.

    A selector assignment effectively bundles mulitple conditional assignments. It also supports nested cases.
    If a signal has a selector assignment, no other assignments are allowed.
    """

    unconditional: Final = False

    def __init__(self, signal: AssignmentTarget, selector: RenderableSelector, allow_short_circuit: bool = False) -> None:
        super().__init__(signal)
        self._selector = selector
        self._allow_short_circuit = allow_short_circuit
        self._priority: bool
        self._cases: Sequence[Tuple[Renderable, Union[Renderable, 'SelectorAssignment']]]
        self._default: Optional[Union[Renderable, 'SelectorAssignment']]
        self._update_cases()

    @property
    def selector(self) -> RenderableSelector:
        return self._selector

    @selector.setter
    def selector(self, value: RenderableSelector) -> None:
        self._selector = value
        self._update_cases()

    @property
    def priority(self) -> bool:
        """Indicates if the cases of the selector assignment are in prioritized order.

        This is detected based on the presence of a 'default' condition.
        """
        return self._priority

    @property
    def cases(self) -> Sequence[Tuple[Renderable, Union[Renderable, 'SelectorAssignment']]]:
        """Sequence of cases for the selector assignment.

        Each case is represented by a tuple of (condition, value). The value can be a selector assignment of its own.
        """
        return self._cases

    @property
    def default(self) -> Optional[Union[Renderable, 'SelectorAssignment']]:
        """Default value, if no condition is met."""
        return self._default

    def __format__(self, format_spec: str) -> str:
        return f'{self.signal} = {self.selector}'

    def _update_cases(self) -> None:  # noqa: C901
        """Compute cases, default and priority."""

        cases: List[Tuple[Renderable, Union[Renderable, 'SelectorAssignment']]] = []
        default: Optional[Union[Renderable, 'SelectorAssignment']] = None
        priority: bool = False

        # Find the default and copy the rest into a new selector
        selector: Dict['Renderable', Union['Renderable', 'RenderableSelector']] = {}
        for condition, value in self.selector.items():
            if isinstance(condition, str) and condition == 'default':
                # If a default is found, the selector is treated as prioritized
                priority = True
                if isinstance(value, Mapping):
                    default = SelectorAssignment(self.signal, value, allow_short_circuit=self._allow_short_circuit)
                else:
                    default = value
            else:
                selector[condition] = value

        # Process conditions
        for condition, value in selector.items():
            short_circuit = False
            if condition.is_constant:
                # Filter unreachable cases and short circuit: If the current case is always True, the remaining cases are unreachable
                if condition.value == 0:  # type: ignore[attr-defined]
                    continue
                elif condition.value == 1:  # type: ignore[attr-defined]
                    if priority:
                        # Replace the default and stop processing the rest of the cases
                        # This is only done, if the selector was found to have a priority before
                        if isinstance(value, Mapping):
                            default = SelectorAssignment(self.signal, value, allow_short_circuit=self._allow_short_circuit)
                        else:
                            default = value
                        break
                    elif not self._allow_short_circuit:
                        raise RuntimeError(
                            'Selector assignment contains an case that is constantly True.\n'
                            'However, the selector cases were neither in prioritized order, nor was it created with `allow_short_circuit=True`.\n'
                            "Selector assignments are treated as prioritized, if the contain a 'default' case.\n"
                            'To allow noRTL to remove all other cases and only keep the constantly True one, set `allow_short_circuit=True`.'
                        )
                    else:
                        # Short circuit, remove all other cases
                        cases = []
                        short_circuit = True

            if isinstance(value, Mapping):
                cases.append((condition, SelectorAssignment(self.signal, value, allow_short_circuit=self._allow_short_circuit)))
            else:
                cases.append((condition, value))
            if short_circuit:
                break

        self._cases = cases
        self._default = default
        self._priority = priority


def selector_to_renderable(selector: Selector) -> RenderableSelector:
    """Convert conditions and levels of selector to renderables."""
    new_selector: Dict[Union[Renderable, Literal['default']], Union[Renderable, RenderableSelector]] = {}
    for condition, value in selector.items():
        if isinstance(condition, str) and condition == 'default':
            pass
        else:
            condition = to_renderable(condition)

        if isinstance(value, Mapping):
            value = selector_to_renderable(value)
        else:
            value = to_renderable(value)
        new_selector[condition] = value

    return new_selector


AnyAssignment = Union[Assignment, ConditionalAssignment, SelectorAssignment]


class State(NamedEntity):
    """Representation of an engine state.

    An engine state is characterized by a set of assignments to signals and a set of
    conditions, when to enter which next state (transitions).

    Each state belongs to a worker. Transitions can only be created betwen states of the same worker.
    """

    def __init__(self, worker: WorkerProto, name: str, allow_assignments: bool = True):
        """Initialize a state.

        Arguments:
            worker: Engine worker.
            name: State name.
            allow_assignments: If the state allows assignments. This is used for internal purposes.
        """
        super().__init__('')
        self._worker = worker

        # Use setter for validation
        self.name = name

        self._allow_assignments = allow_assignments

        self._assignments: List[AnyAssignment] = []
        self._assigned_signal_names: Set[str] = set()

        # Transition <Condition>, <next value of state variable>
        self._transitions: List[Tuple[Renderable, Self]] = []
        self._restricted_state: Optional[State] = None
        self._transitions_locked = False

        # Store for debug prints. These will not be rendered to synthesizeable constructs
        self._prints: List[Tuple[str, Tuple[Renderable, ...]]] = []
        self._printfs: Dict[str, List[Tuple[str, Tuple[Renderable, ...]]]] = {}

        # Store stack trace at point of creation
        self.engine.tracer.add_metadata(self, 'stack@creation', profile=True)

        # Store all currently active scratch signals for later scratch pad optimization
        self.active_scratch_signals = [
            s for s in self.engine.scratch_manager.active_zone.scratch_signals if not s.released and s.owner == self.engine.current_thread
        ]
        for zone in self.engine.scratch_manager.suspended_zones:
            self.active_scratch_signals.extend([s for s in zone.scratch_signals if not s.released and s.owner == self.engine.current_thread])

    @property
    def engine(self) -> EngineProto:
        """Engine that this state belongs to."""
        return self.worker.engine

    @property
    def worker(self) -> WorkerProto:
        """Engine worker that this state belongs to."""
        return self._worker

    @property
    def name(self) -> str:
        """State name.

        If the worker for this state is not the main worker, the name of the state must be prefixed with the name of the current worker.
        The prefix is automatically added, if missing.
        """
        return self._name

    @name.setter
    def name(self, name: str) -> None:
        """State name.

        If the worker for this state is not the main worker, the name of the state must be prefixed with the name of the current worker.
        The prefix is automatically added, if missing.
        """

        # Prefix the worker name if missing. The prefix is omitted for the main worker.
        name = self.worker.create_scoped_name(name)

        if name == self.name:
            return

        if name in self.worker.state_names:
            raise KeyError(f'State {name} already exists.')

        # Update set of state names in worker
        if self.name != '':
            self.worker.state_names.discard(self.name)
        self.worker.state_names.add(name)

        self._name = name

    # Assignment Management
    @property
    def allow_assignments(self) -> bool:
        """If this state allows assignments."""
        return self._allow_assignments

    @property
    def assignments(self) -> Sequence[AnyAssignment]:
        """Sequence of assignments for this state."""
        return self._assignments

    def add_assignment(self, signal: AssignmentTarget, value: Renderable, condition: Optional[Renderable] = None) -> None:
        """Add assignment to this state.

        !!! warning
            Conditional assignments bypass the multi-assignment check for overlap with other conditional assignments!
        """
        if not self.allow_assignments:
            raise ForbiddenAssignmentError(f'State {self.name} does not allow assignments.')

        # Check if signal is already assigned
        for assignment in self.get_assignments(signal):
            # Ignore conditional assignments
            if isinstance(assignment, ConditionalAssignment) and condition is not None:
                continue

            # Test overlap
            overlap = signal.overlaps_with(assignment.signal)

            if overlap == 'partial':
                raise ConflictingAssignmentError(
                    f'State {self.name} already has an assignment to signal {signal.name} that partially overlaps with the new assignment.\n'
                    f'Previous assignment was {assignment}, new assignment is {signal} = {value}.'
                    '\nRefusing to overwrite the signal.'
                )

            # Selector assignments prevent all other assignments
            if overlap is True:
                if isinstance(assignment, SelectorAssignment):
                    raise ConflictingAssignmentError(
                        f'State {self.name} already has an selector assignment to signal {signal.name}.\nIt is not possible to add another assignment.'
                    )

                # Check equality of the signals by rendering them. This could cause false-negatives, but is the easiest way.
                if value.render() != assignment.value.render():
                    raise ConflictingAssignmentError(
                        f'State {self.name} already has an assignment to signal {signal.name}.\n'
                        f'Previous value was {assignment.value}, new value would be {value}. Refusing to overwrite the signal.'
                    )

        # Save new assignment
        if condition is None:
            self._assignments.append(Assignment(signal, value))
        else:
            self._assignments.append(ConditionalAssignment(signal, value, condition))

        self._assigned_signal_names.add(signal.name)

    def add_selector_assignment(self, signal: AssignmentTarget, selector: RenderableSelector, allow_short_circuit: bool = False) -> None:
        """Add selector assignment to this state.

        !!! warning
            Selector assignments bypass the multi-assignment check for partial overlaps!
        """
        if not self.allow_assignments:
            raise ForbiddenAssignmentError(f'State {self.name} does not allow assignments.')

        # Check if signal is already assigned
        for assignment in self.get_assignments(signal):
            overlap = signal.overlaps_with(assignment.signal)
            if overlap is True:
                raise ConflictingAssignmentError(
                    f'State {self.name} already has an assignment to signal {signal.name}.\nIt is not possible to add a selector assignment.'
                )
            elif overlap == 'partial' and assignment.unconditional:
                raise ConflictingAssignmentError(
                    f'State {self.name} already has an unconditional assignment to signal {signal.name}.\nIt is not possible to add a selector assignment.'
                )

        # Save new assignment
        self._assignments.append(SelectorAssignment(signal, selector, allow_short_circuit=allow_short_circuit))
        self._assigned_signal_names.add(signal.name)

    def get_assignments(self, signal: AssignmentTarget) -> Iterator[AnyAssignment]:
        """Iter over current assignment for a signal.

        Arguments:
            signal: The signal to search for.

        Yields:
            The current assignments for this signal.
        """
        # Use a set of the assigned signal names for quick check. In case of a match, search for the signal.
        if signal.name in self._assigned_signal_names:
            for assignment in self.assignments:
                # Check by signal name, will also find slices of the same signal
                if signal.name == assignment.signal.name:
                    yield assignment

    # Transition Management
    @property
    def transitions(self) -> Sequence[Tuple[Renderable, Self]]:
        """List of transitions to other states."""
        return tuple(self._transitions)

    def _add_transition(self, condition: Renderable, state: StateProto) -> None:
        """Add transition to other state."""
        if self._transitions_locked:
            raise TransitionLockError('The transitions for this state have been locked. You cannot add any other transitions.')
        elif self._restricted_state is not None and state is not self._restricted_state:
            raise TransitionRestrictionError(
                f'This state was restricted to transitions to state {self._restricted_state.name}. Unable to add other transitions.'
            )
        if condition.render() != "1'h0":
            self._transitions.append((condition, state))  # type: ignore[arg-type]

    def _restrict_transition(self, state: StateProto) -> None:
        """Restrict transitions to only allow one other state."""
        if self._restricted_state is not None and state is not self._restricted_state:
            raise TransitionRestrictionError(
                f'This state was alreay restricted to transitions to state {self._restricted_state.name}. Unable to restrict for another state.'
            )
        self._restricted_state = state  # type: ignore[assignment]

    def _lock_transitions(self) -> None:
        """Lock the current transitions and prevent any others from being added."""
        self._transitions_locked = True

    # Misc.
    def render(self, target: Optional[str] = None) -> str:
        """Returns the state name for Verilog.

        This function will later contain the logic to transform any string to a correct verilog name.
        """
        return self._name

    def __format__(self, format_spec: str) -> str:
        return self.render()

    def print(self, line: str, *args: Renderable) -> None:
        """Adds a line to the print list that will be processed during simulation."""
        self._prints.append((line, args))

    def printf(self, fname: str, line: str, *args: Renderable) -> None:
        """Store an item that will be output to a file during simulation."""
        if fname in self._printfs:
            self._printfs[fname].append((line, args))
        else:
            self._printfs[fname] = [(line, args)]

    @property
    def signature(self) -> str:
        """Create a string that comprises all assignments and transitions.

        This will be used for redundant state detection.
        """
        ret = ''

        ret += 'Assignments: \n'

        for assignment in sorted(self.assignments, key=lambda x: x.signal.render()):
            if assignment.unconditional:
                ret += f'{assignment.signal} <= {assignment.value}'  # type: ignore[union-attr]
            else:
                ret += '\n'.join(self._extract_conditional_assignment(assignment))  # type: ignore[arg-type]
        ret += '\n'

        ret += 'Transitions: \n'

        for condition, next_state in self.transitions:
            ret += f'if ({condition.render()}), then {next_state.name}\n'

        return ret

    @classmethod
    def _extract_conditional_assignment(cls, assignment: Union[ConditionalAssignment, SelectorAssignment], indent: str = '') -> Iterable[str]:
        """Extract conditional assignment for signature."""
        for i, (condition, value) in enumerate(assignment.cases):
            if i == 0:
                ret = f'{indent}if ({condition}): '
            else:
                ret = f'{indent}elif ({condition}): '

            if hasattr(value, 'cases'):
                ret += f'\n{indent}'
                ret += f'\n{indent}'.join(cls._extract_conditional_assignment(value, indent=indent + '    '))  # type: ignore[arg-type]
            else:
                ret += f'{assignment.signal} <= {value}'
            yield ret
