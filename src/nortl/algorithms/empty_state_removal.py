"""Empty state removal optimization for noRTL engines.

This module provides an optimization that removes states from the state graph that have no assignments
and only one transition to a next state with a condition of "1'h1" (always on).
"""

from typing import List, Tuple

from nortl.core.engine import CoreEngine
from nortl.core.protocols import Renderable, StateProto


class EmptyStateRemovalMixin(CoreEngine):
    """Mixin providing empty state removal optimization.

    This optimization removes states that:
    1. Have no assignments
    2. Have exactly one transition
    3. The transition condition is "1'h1" (always true)
    4. Have the metadata 'collapsable' set to True

    Example:
        Consider the state sequence S1 -> S_empty -> S3 where S_empty is a state without assignments
        and with only one transition to S3 with a condition being 1'h1 (always on).
        The optimizer will remove S_empty and wire the state graph to S1 -> S3.
    """

    def _is_empty_state(self, state: StateProto) -> bool:
        """Check if a state has no assignments.

        Arguments:
            state: The state to check.

        Returns:
            True if the state has no assignments, False otherwise.
        """
        return len(state.assignments) == 0

    def _is_single_transition(self, state: StateProto) -> bool:
        """Check if a state has exactly one transition.

        Arguments:
            state: The state to check.

        Returns:
            True if the state has exactly one transition, False otherwise.
        """
        return len(state.transitions) == 1

    def _is_always_true_transition(self, state: StateProto) -> bool:
        """Check if a state's transition condition is "1'h1" (always true).

        Arguments:
            state: The state to check.

        Returns:
            True if the transition condition is "1'h1", False otherwise.
        """
        if not self._is_single_transition(state):
            return False

        condition, _ = state.transitions[0]
        return condition.render() == "1'h1"

    def _is_collapsable(self, state: StateProto) -> bool:
        """Check if a state has the 'collapsable' metadata set to True.

        Arguments:
            state: The state to check.

        Returns:
            True if the state has 'collapsable' metadata set to True, False otherwise.
        """
        return state.has_metadata('collapsable') and state.get_metadata('collapsable') is True

    def _is_removable_state(self, state: StateProto) -> bool:
        """Check if a state meets all criteria for removal.

        A state is removable if:
        1. It has no assignments
        2. It has exactly one transition
        3. The transition condition is "1'h1" (always true)
        4. It has the 'collapsable' metadata set to True

        Arguments:
            state: The state to check.

        Returns:
            True if the state is removable, False otherwise.
        """
        return (
            self._is_empty_state(state)
            and self._is_single_transition(state)
            and self._is_always_true_transition(state)
            and self._is_collapsable(state)
        )

    def _get_predecessor_states(self, state: StateProto) -> List[StateProto]:
        """Get all states that have a transition to the given state.

        Arguments:
            state: The state to find predecessors for.

        Returns:
            List of predecessor states.
        """
        predecessors: List[StateProto] = []
        for worker_states in self.states.values():
            for predecessor in worker_states:
                for condition, next_state in predecessor.transitions:
                    if next_state == state:
                        predecessors.append(predecessor)
                        break
        return predecessors

    def _get_successor_state(self, state: StateProto) -> StateProto | None:
        """Get the successor state of a state.

        Arguments:
            state: The state to get the successor for.

        Returns:
            The successor state if there is exactly one transition, None otherwise.
        """
        if not self._is_single_transition(state):
            return None

        _, successor = state.transitions[0]
        return successor

    def _remove_empty_state(self, state: StateProto) -> None:
        """Remove an empty state and update transitions.

        This function removes the given state and updates all transitions that pointed to it
        to point to its successor state instead.

        Arguments:
            state: The state to remove.
        """
        successor = self._get_successor_state(state)
        if successor is None:
            return

        # Get all predecessor states
        predecessors = self._get_predecessor_states(state)

        # Update transitions in predecessor states
        for predecessor in predecessors:
            new_transitions: List[Tuple[Renderable, StateProto]] = []
            for condition, next_state in predecessor.transitions:
                if next_state == state:
                    new_transitions.append((condition, successor))
                else:
                    new_transitions.append((condition, next_state))
            predecessor._transitions = new_transitions  # type: ignore

        # Remove the state from its worker
        worker = state.worker
        worker._states = [s for s in worker.states if s.name != state.name]  # type: ignore
        worker._state_names.discard(state.name)  # type: ignore

    def empty_state_removal(self) -> None:
        """Remove empty states from the state graph.

        This function iterates through all states and removes those that meet the criteria:
        1. No assignments
        2. Exactly one transition
        3. Transition condition is "1'h1" (always true)
        4. Has 'collapsable' metadata set to True

        The removal is done in a single pass, as removing one state doesn't affect the
        removability of other states (since we only remove states with no assignments).
        """
        for worker_states in self.states.values():
            # Create a list of states to remove (to avoid modifying list while iterating)
            states_to_remove: List[StateProto] = [state for state in worker_states if self._is_removable_state(state)]

            for state in states_to_remove:
                self._remove_empty_state(state)
