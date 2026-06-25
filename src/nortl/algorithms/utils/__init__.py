from typing import List

from nortl.core.protocols import StateProto


def preceeding_states(state: StateProto) -> List[StateProto]:
    """Get all states that have a transition to the given state.

    Arguments:
        state: The state to find predecessors for.

    Returns:
        List of states that have a transition to the given state.
    """
    preceeding_states: List[StateProto] = []
    for worker_state in state.worker.states:
        for _, next_state in worker_state.transitions:
            if next_state is state:
                preceeding_states.append(worker_state)
    return preceeding_states
