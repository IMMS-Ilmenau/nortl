"""Describes engine states as Python object."""

from typing import Dict, List, Optional, Sequence, Set, Tuple

from typing_extensions import Self

from nortl.core.exceptions import ConflictingAssignmentError, ForbiddenAssignmentError, TransitionLockError, TransitionRestrictionError
from nortl.core.operations import Const

from .common import NamedEntity
from .protocols import AssignmentTarget, EngineProto, Renderable, StateProto, WorkerProto

__all__ = [
    'State',
]


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

        self._assignments: List[Tuple[AssignmentTarget, Renderable, Renderable]] = []
        self._assigned_signal_names: Set[str] = set()

        # Transition <Condition>, <next value of state variable>
        self._transitions: List[Tuple[Renderable, Self]] = []
        self._restricted_state: Optional[State] = None
        self._transitions_locked = False

        # Store for debug prints. These will not be rendered to synthesizeable constructs
        self._prints: List[Tuple[str, Tuple[Renderable, ...]]] = []
        self._printfs: Dict[str, List[Tuple[str, Tuple[Renderable, ...]]]] = {}

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
    def assignments(self) -> Sequence[Tuple[AssignmentTarget, Renderable, Renderable]]:
        """Sequence of assignments for this state."""
        return self._assignments

    def add_assignment(self, signal: AssignmentTarget, value: Renderable, condition: Optional[Renderable] = None) -> None:
        """Add assignment to this state."""
        if not self.allow_assignments:
            raise ForbiddenAssignmentError(f'State {self.name} does not allow assignments.')

        if condition is None:
            condition = Const(1)

        # Check if signal is already assigned for unconditional assigns
        if (old_assignment := self.get_assignment(signal)) is not None and (condition == 1).render() == "1'h1":
            other_signal, old_value, _ = old_assignment

            overlap = signal.overlaps_with(other_signal)

            if overlap == 'partial':
                raise ConflictingAssignmentError(
                    f'State {self.name} already has an assignment to signal {signal.name} that partially overlaps with the new assignment.\n'
                    f'Previous assignment was {other_signal} = {old_value}, new assignment is {signal} = {value}.'
                    '\nRefusing to overwrite the signal.'
                )

            # Check equality of the signals by rendering them. This could cause false-negatives, but is the easiest way.
            if overlap is True and value.render() != old_value.render():
                raise ConflictingAssignmentError(
                    f'State {self.name} already has an assignment to signal {signal.name}.\n'
                    f'Previous value was {old_value}, new value would be {value}. Refusing to overwrite the signal.'
                )

        self._assignments.append((signal, value, condition))
        self._assigned_signal_names.add(signal.name)

    def get_assignment(self, signal: AssignmentTarget) -> Optional[Tuple[AssignmentTarget, Renderable, Renderable]]:
        """Get current assignment for a signal.

        Arguments:
            signal: The signal to search for.

        Returns:
            The current assignment for this signal or None, if it is not assigned.


        !!! note: This returns only the first assignment and does not deal with conditional assigns!
        """
        # Use a set of the assigned signal names for quick check. In case of a match, search for the signal.
        if signal.name in self._assigned_signal_names:
            for other_signal, value, condition in self.assignments:
                # Check by signal name, will also find slices of the same signal
                if signal.name == other_signal.name:
                    return other_signal, value, condition
        return None

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

        for target, value, condition in sorted(self.assignments, key=lambda x: str(x[0])):
            ret += f'if {condition.render()}: {target} <= {value.render()} \n'

        ret += 'Transitions: \n'

        for condition, next_state in self.transitions:
            ret += f'If ({condition.render()}), then {next_state.name}\n'

        return ret
