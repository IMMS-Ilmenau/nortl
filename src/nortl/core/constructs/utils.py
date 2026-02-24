"""Utilities for constructs."""

from typing import Iterator, Optional

from nortl.core.exceptions import read_access
from nortl.core.modifiers import BaseModifier
from nortl.core.operations import BaseOperation
from nortl.core.protocols import AnySignal, AssignmentTarget, EngineProto, Renderable
from nortl.core.signal import ScratchSignal, Signal, SignalSlice
from nortl.core.state import SelectorAssignment

__all__ = [
    'FastForwarder',
]


class FastForwarder:
    """Helper class to check if values for an assignment can be fast-forwarded.

    This can be used by constructs, to avoid protective sync() cycles when passing inputs.
    """

    def __init__(self, engine: EngineProto):
        self.engine = engine
        self.needs_sync = False

    def __call__(self, value: Renderable) -> Optional[AnySignal]:
        """Check if the value for an assignment can be fast-forwarded.

        This checks if the value was freshly assigned in the current state. If this is the, case, it will return the new value.
        It will also update the attribute `needs_sync`.

        In the following example, the value of `a` is freshly assigned in the current state. It also shall be copied into a different variable, `c`, which would require a `sync()` in between:

        ```python
        engine.set(a, b)
        engine.sync()  # this protective sync() could be removed
        engine.set(c, a)
        ```

        These assignments could be transformed into:

        ```python
        engine.set(a, b)
        engine.set(c, b) # fast-forward assignment
        ```
        """
        # Check if the input value has been assigned in the current state
        fast_forward_value: AnySignal = value  # type: ignore[assignment]
        for signal in self.extract_all_signals(value):
            for assignment in self.engine.current_state.get_assignments(signal):
                overlap = signal.overlaps_with(assignment.signal)
                if overlap is False:
                    # No overlap
                    continue
                elif overlap == 'partial' or not assignment.unconditional:
                    # Partial or conditional assignments are too complicated to fast-forward
                    self.needs_sync = True
                    return None

                # If an assignment is found, the behavior depends on the type of the input value
                if isinstance(value, BaseModifier):
                    value = value.content
                if isinstance(value, (Signal, SignalSlice, ScratchSignal)):
                    # If the input value is a signal, its possible to copy the value directly into the input slot
                    # Any modifier is preserved
                    if isinstance(value, BaseModifier):
                        fast_forward_value = value.copy(assignment.value)
                    else:
                        fast_forward_value = assignment.value  # type: ignore[assignment]
                else:
                    # Signals used in operations are also too complicated to fast-forward
                    self.needs_sync = True
                    return None

        return fast_forward_value

    def reclaim(self, value: Renderable) -> None:
        """Reclaim all scratch signals in an renderable."""
        for signal in self.extract_all_signals(value):
            if isinstance(signal, ScratchSignal) and signal.released:
                signal.reclaim()

    def add_assignment_case(self, target: AssignmentTarget, value: AnySignal, condition: Renderable) -> None:
        """Set a fast-forward value to a target for a certain condition.

        This helper method will add a selector assignment to the target, or update an existing one, if possible.
        """
        for assignment in self.engine.current_state.get_assignments(target):
            overlap = target.overlaps_with(assignment.signal)

            if overlap is not True:
                # No overlap
                continue
            elif not isinstance(assignment, SelectorAssignment):
                raise RuntimeError(f'Found unexpected assignment to {target} when attempting to add assignment case: {assignment.signal}')

            # Add new case to selector
            new_selector = {condition: value for condition, value in assignment.selector.items()}
            new_selector[condition] = read_access(value)
            assignment.selector = new_selector
            return

        # If no assignment was found, add a new selector
        self.engine.set_when(target, {condition: value})

    @classmethod
    def extract_all_signals(cls, renderable: Renderable) -> Iterator[AnySignal]:
        """Extract all signals from a renderable."""
        # Unpack modifiers
        if isinstance(renderable, BaseModifier):
            renderable = renderable.content

        if isinstance(renderable, BaseOperation):
            for operand in renderable.operands:
                yield from cls.extract_all_signals(operand)
        elif isinstance(renderable, (Signal, SignalSlice, ScratchSignal)):
            yield renderable
