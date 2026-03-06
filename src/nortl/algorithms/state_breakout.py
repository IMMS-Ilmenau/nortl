import copy
import math
from typing import Dict, List, Set, Tuple, Union

from nortl.core.constructs import Segment
from nortl.core.engine import CoreEngine
from nortl.core.operations import Const, to_renderable
from nortl.core.protocols import Renderable, Selector, SignalProto, StateProto, WorkerProto
from nortl.core.state import selector_to_renderable
from nortl.utils.operand_extraction import extract_operands


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


def move_state_to_worker(state: StateProto, new_worker: WorkerProto) -> StateProto:
    """Move a state from its current worker to a new worker.

    This function removes the state from the old worker and creates a copy in the new worker
    with the same assignments and transitions.

    Arguments:
        state: The state to move.
        new_worker: The worker to move the state to.

    Returns:
        The new state in the new worker.
    """
    # Remove state from old worker
    old_worker = state.worker
    old_worker.state_names.discard(state.name)
    old_worker._states = [s for s in old_worker.states if s.name != state.name]  # type: ignore

    # Add to new worker
    new_state = new_worker.create_state()
    new_state._assignments = state._assignments  # type:ignore
    new_state._transitions = state._transitions  # type:ignore

    return new_state


def state_in_partition(state: StateProto, partition: List[StateProto]) -> bool:
    """Check if a state is in the given partition.

    Arguments:
        state: The state to check.
        partition: The partition to check against.

    Returns:
        True if the state is in the partition, False otherwise.
    """
    for partition_state in partition:
        if state is partition_state:
            return True
    return False


def map_state_to_new_worker(state: StateProto, mapping: List[Tuple[StateProto, StateProto]]) -> StateProto:
    """Map a state to its corresponding new state using the mapping table.

    Arguments:
        state: The state to map.
        mapping: The mapping table containing state pairs.

    Returns:
        The new state corresponding to the given state.

    Raises:
        ValueError: If the state cannot be found in the mapping table.
    """
    for s1, s2 in mapping:
        if s1 is state:
            return s2

    raise ValueError('Could not map state to new worker!')


def writing_states(signal: SignalProto) -> Dict[str, List[StateProto]]:
    """Get all states that write to a given signal.

    This function returns a dictionary mapping worker names to lists of states that
    have assignments for the given signal.

    Arguments:
        signal: The signal to check for writing states.

    Returns:
        Dictionary mapping worker names to lists of writing states.
    """
    ret: Dict[str, List[StateProto]] = {}

    for workername, statelist in signal.engine.states.items():
        ret[workername] = []

        for state in statelist:
            # Ignore IDLE states
            if state.name == state.worker.create_scoped_name('IDLE'):
                continue

            if len(list(state.get_assignments(signal))) != 0:
                ret[workername].append(state)

        if len(ret[workername]) == 0:
            del ret[workername]

    return ret


def is_safe_transition_cond(current_state: StateProto, cond: Renderable) -> bool:
    """Check if a transition condition is safe to use when leaving a state.

    A transition is considered safe if:
    * The condition is unconditional (1'h1), or
    * The condition only involves signals that are written by a single worker
      and not written in the current state.

    Arguments:
        current_state: The state from which the transition is being made.
        cond: The transition condition to check.

    Returns:
        True if the transition is safe, False otherwise.
    """
    if cond.render() == "1'h1":
        return True

    operands = extract_operands(cond)

    for op in operands:
        wstates = writing_states(op)  # type:ignore

        # Check if signal is written from more than one worker
        # Also checks if the write is done in a different state than the read in the current state
        if len(set([*list(wstates.keys()), current_state.worker.name])) > 1:
            return False

        # Check if signal can be written in current state
        for states in wstates.values():
            for state in states:
                if state.name == current_state.name:
                    return False

    return True


def is_valid_partition(partition: List[StateProto]) -> bool:  # noqa: C901
    """Perform structural checks for the states in a partition.

    The following checks are performed:
    * All states must belong to the same worker.
    * The IDLE state of the worker must not be part of the partition.
    * Transitions entering and leaving the partition must be unconditional
      to avoid race conditions with Engine.set_when().

    Arguments:
        partition: The partition to validate.

    Returns:
        True if the partition is valid, False otherwise.
    """

    if len(set([s.worker.name for s in partition])) != 1:
        return False

    for state in partition:
        # Check incoming transitions
        for pre_state in preceeding_states(state):
            if not state_in_partition(pre_state, partition):
                for cond, next_state in pre_state.transitions:
                    if next_state is state and not is_safe_transition_cond(pre_state, cond):
                        return False

        # Check outgoing transitions
        for cond, next_state in state.transitions:
            if (not state_in_partition(next_state, partition)) and (not is_safe_transition_cond(state, cond)):
                return False

        # Idle states must not belong to partition
        if state.name == state.worker.create_scoped_name('IDLE'):
            return False

        # Also the state following the IDLE state must not be part of the partition since we cannot modify the idle state during breakout
        for _, state_following_idle in state.worker.reset_state.transitions:
            if state.name == state_following_idle.name:
                return False

    return True


def move_partition_to_worker(partition: List[StateProto], new_worker: WorkerProto) -> Tuple[List[StateProto], List[Tuple[StateProto, StateProto]]]:
    new_partition = []
    mapping = []

    for state in partition:
        """Move states to new worker."""
        new_state = move_state_to_worker(state, new_worker)
        mapping.append((state, new_state))
        new_partition.append(new_state)

    return new_partition, mapping


def get_crystal(start_state: StateProto, used_states: Set[str], n_max: int) -> List[StateProto]:
    """Create a partition from a start state.

    The process of generating a partition from a start state looks like a crystalization. The start state is the starting point
    and all following states are added to the result, if (and only if) they form a valid partition.
    To avoid using already occupied (or visited) states, the names of the used states are passed along as set of strings.

    Form a more computer-science approach, this algorithm is inspired by DFS.
    """
    ret: List[StateProto] = []

    if start_state.name in used_states:
        return []

    ret.append(start_state)

    for _, next_state in start_state.transitions:
        if next_state.name not in used_states:
            if is_valid_partition([*ret, next_state]):
                used_states.add(next_state.name)
                ret += get_crystal(start_state, used_states, n_max - len(ret))
            if len(ret) > n_max:
                break

    if is_valid_partition(ret):
        return ret
    else:
        return []


def get_partitions(all_states: List[StateProto], n_max: int = 64, n_min: int = 32) -> List[List[StateProto]]:
    if len(set([state.worker.name for state in all_states])) > 1:
        raise RuntimeError('All states must be part of the same worker!')

    # All states have to belong to the same worker
    ret: List[List[StateProto]] = []

    used_states: Set[str] = set()

    num_new_partitions = 123

    temp_partition = []

    while num_new_partitions > 0:
        num_new_partitions = 0
        for state in all_states:
            new_partition = get_crystal(state, copy.copy(used_states), n_max)
            if len(new_partition) >= n_min:
                ret.append(new_partition)
                num_new_partitions += 1
                for new_state in new_partition:
                    used_states.add(new_state.name)
            else:
                temp_partition += new_partition

                for new_state in new_partition:
                    used_states.add(new_state.name)

                if len(temp_partition) > n_min:
                    num_new_partitions += 1
                    ret.append(temp_partition)
                    temp_partition = []

    return ret


class StateBreakoutMixin(CoreEngine):
    """This Mixin provides functions that take a set of existing states in a worker and breaks them out into a new worker.

    In synthesis runs we see problems with large state machines being encoded in very suboptimal ways leading
    to large ressource demand. This can be corrected by splitting up into smaller state machines.

    This class provides methods to break out a set of states from an existing worker, inject them into a new worker
    and wire up the state graph such that the behavior is not changed.

    In the following state graph, the states S3 and S4 should be transferred to a new worker:

    ```mermaid
    stateDiagram-v2
        S1 --> S2
        S2 --> S3
        S3 --> S4
        S4 --> S5
        S5 --> S6
        S6 --> S1
    ```

    This will be transformed into the following shape:
    ```
    stateDiagram-v2
        state Source_Worker {
            S1 --> S2
            S2 --> WAIT
            WAIT --> S5
            S5 --> S6
            S6 --> S1
        }

        state New_Worker {
            WORKER_IDLE --> S3
            S3 --> S4
            S4 --> WORKER_IDLE
        }
    ```

    Where the New_Worker waits for a trigger from the Source_Worker. Then the new worker goes through the transferred
    states S3 and S4 and then returns to the WORKER_IDLE state. Meantime, the WAIT state in the source worker does essentially
    nothing (especially no signal assigns) but wait for the New_worker returning to the WORKER_IDLE state and then passes
    on the execution to S5.

    Now the challenge arises on how the inter-worker signalling is to be executed. Remember, that each state transition cannot be
    executed faster than a clock cycle. In the original scenario, the duration from S2 to S3 will be done in exactly one clock cycle
    (if the transition condition is 1'h1). If we would set the trigger in the final worker at the point where S3 had been, we would
    insert an additional cycle -- which we need to avoid. This means, we need to set this trigger in the preceeding state(s) of S1
    once the state transition is possible.
    In the same sense, the WAIT state needs to react on the transition condition of S4 to the WORKER_IDLE state in the New_Worker.

    For realizing this signalling, the process introduces new worker_start, worker_select and process_finished signals within the worker's
    scoped names.


    !!! warning

        The use of this mixin may degrade the performance or area of your engine -- depending on the selection of partitions.
        This will be subject to future research!
    """

    def state_breakout(self, partitions: Union[List[StateProto], List[List[StateProto]]]) -> None:
        """Move a list of states to a newly created worker and realize the glue.

        Consider the incoming list of states (i.e. a partition) to be cut out of an existing state graph that is substituted by a wait state in the original worker.
        This cut set has a set of incoming and outgoing transitions that are now incoming and outgoing transitions of the wait state.
        The function is realized by a new worker that starts upon the entry of the wait state. In this case, the new worker is triggered
        with a pulse (`TRIGGER`) and a select signal (`TRIGGER_SELECT`) indicating which state (that was moved to the worker) should follow next.
        Once the new worker reaches the transition to its IDLE state, the wait state of the original worker receives a select (`FINISH_SELECT`) signal that shows
        which outgoing transition is to be taken.

        !!! warning

            The use of this function may degrade the performance or area of your engine -- depending on the selection of partitions.
            This will be subject to future research!

        Arguments:
            partitions: List of states to break out into a new worker or List if partitions.

        Raises:
            ValueError: If the partition is invalid.
        """

        if len(partitions) == 0:
            return
        if isinstance(partitions[0], list):
            # We are dealing with a list of partitions

            # check for valid partitions first
            for partition in partitions:
                if not is_valid_partition(partition):  # type:ignore
                    raise ValueError('A given partition for the state breakout is invalid!')

            # Start the break out
            for partition in partitions:
                self._state_breakout_single_partition(partition)  # type:ignore
        else:
            self._state_breakout_single_partition(partitions)  # type:ignore

    def _state_breakout_single_partition(self, partition: List[StateProto]) -> None:
        if len(partition) == 0:
            return

        old_worker = partition[0].worker

        # Reuse existing wait state if available, otherwise create new one
        breakout_wait_state = self._get_wait_state(old_worker)

        new_worker = self.create_worker()
        new_worker_trigger = self.define_local(new_worker.create_scoped_name('TRIGGER'), 1, 0, pulsing=True)
        new_worker_finish = self.define_local(new_worker.create_scoped_name('FINISH'), 1, 0)
        new_worker_trigger_select = self.define_local(new_worker.create_scoped_name('TRIGGER_SELECT'), 1, 0)  # Width will be adapted afterwards
        new_worker_finish_select = self.define_local(new_worker.create_scoped_name('FINISH_SELECT'), 1, 0)

        # Make a check in worker disappear
        # FIXME: Look for cleaner way to do this.
        new_worker._threads = [123]  # type:ignore

        new_worker_idle_state = new_worker.next_state
        new_worker.reset_state._add_transition(Const(True), new_worker_idle_state)
        new_worker_idle_state.add_assignment(new_worker_finish, to_renderable(0))

        num_trigger_select = 0
        num_finish_select = 0

        new_partition, mapping = move_partition_to_worker(partition, new_worker)

        # Incoming transition handling
        for state in old_worker.states:
            """
            Each transition to one of the states of our partition converts to a transition from the IDLE state to the copied state inside of the new worker.
            At the same time, the original transition is modified to point to the wait state in the old worker.

            The transition conditions are copied as follows:

            * Old Worker: The transition condition stays unmodified. The worker enters the wait state as if it was entering the original state in the partition.
            * New Worker: The transition condition is augmented by the select and trigger signal.

            The select signal is used to show the new worker which state should be entered. This select signal has to be set inside of the preceeding states of the state inside of the partition.
            In a similar manner, the trigger signal is set there to 1 and reset in the wait state.

            Note that the preceeding state may enter the partition on different points. Therefore, the select signal has be be assigned with the same condition as the state transition.
            """

            if state.name == state.worker.create_scoped_name('IDLE'):
                continue

            # Iterate through all preceeding states and collect transitions and conditions
            # Since we already moved all partition states to the new worker, we can directly operate on the state list of the old worker.

            new_transitions: List[Tuple[Renderable, StateProto]] = []

            trigger_select_assign: Selector = {}
            trigger_assign: Selector = {}

            for cond, next_state in state.transitions:
                if state_in_partition(next_state, partition):
                    # configure trigger and select
                    trigger_select_assign[cond] = num_trigger_select  # type:ignore
                    trigger_assign[cond] = 1  # type:ignore

                    # Old worker needs to stop
                    new_transitions.append((cond, breakout_wait_state))

                    # New Worker takes over
                    new_worker_idle_state._add_transition(
                        (new_worker_trigger == 1) & (new_worker_trigger_select == num_trigger_select), map_state_to_new_worker(next_state, mapping)
                    )

                    num_trigger_select += 1
                else:
                    new_transitions.append((cond, next_state))

            state._transitions = new_transitions  # type:ignore
            state.add_selector_assignment(new_worker_trigger, selector_to_renderable(trigger_assign), True)
            state.add_selector_assignment(new_worker_trigger_select, selector_to_renderable(trigger_select_assign), True)

            # FIXME: Add Metadata for reachability analysis!

        new_worker_trigger_select._width = math.ceil(math.log2(num_trigger_select + 1)) + 1

        # Outgoing transition handling
        for state in new_partition:
            """
            To jump out of our partition, the old worker needs to leave the wait state and transition to the correct next state.
            This is done in a similar way as handling the input transitions: A finish signal and finish_select signal are used to determine which next state is to be entered.
            """

            new_transitions = []
            finish_select_assign: Selector = {}
            finish_assign: Selector = {}

            for cond, next_state in state.transitions:
                if not state_in_partition(next_state, partition):
                    finish_select_assign[cond] = num_finish_select  # type:ignore
                    finish_assign[cond] = 1  # type:ignore

                    # New worker stops
                    new_transitions.append((cond, new_worker_idle_state))

                    # Old worker takes over
                    breakout_wait_state._add_transition((new_worker_finish == 1) & (new_worker_finish_select == num_finish_select), next_state)

                    num_finish_select += 1

                else:
                    new_transitions.append((cond, map_state_to_new_worker(next_state, mapping)))

            state._transitions = new_transitions  # type:ignore
            state.add_selector_assignment(new_worker_finish, selector_to_renderable(finish_assign), True)
            state.add_selector_assignment(new_worker_finish_select, selector_to_renderable(finish_select_assign), True)

        new_worker_finish_select._width = math.ceil(math.log2(num_finish_select + 1)) + 1

    def _get_wait_state(self, old_worker: WorkerProto) -> StateProto:
        breakout_wait_state = None
        for state in old_worker.states:
            if state.name == old_worker.create_scoped_name('WAIT'):
                breakout_wait_state = state
                break

        if breakout_wait_state is None:
            breakout_wait_state = old_worker.create_state()
            breakout_wait_state.name = old_worker.create_scoped_name('WAIT')  # type:ignore
        return breakout_wait_state

    def breakout_segments(self, workername: str, n_states_max: int) -> None:
        partitions: List[List[StateProto]] = []
        current_partition: List[StateProto] = []

        for segment in Segment.get_engine_context(self).segments:
            for rendered_segment in segment.rendered_segments.values():
                if rendered_segment.start_state.worker.name != workername:
                    continue
                if is_valid_partition(rendered_segment.states):
                    if len(rendered_segment.states) > 2 * n_states_max:
                        pass
                    elif len(current_partition) + len(rendered_segment.states) < n_states_max:
                        current_partition += rendered_segment.states
                    else:
                        partitions.append(current_partition)
                        current_partition = rendered_segment.states

        if current_partition != [] and is_valid_partition(current_partition):
            partitions.append(current_partition)

        for partition in partitions:
            if is_valid_partition(partition):
                self.state_breakout(partition)
