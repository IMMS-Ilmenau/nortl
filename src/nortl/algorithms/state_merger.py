from typing import Dict, List, Set, Tuple

from nortl.core.engine import CoreEngine
from nortl.core.operations import Any
from nortl.core.protocols import Renderable, StateProto


class StateMergerMixin(CoreEngine):
    """This Mixin provides functions that merge states that do the same things: Same Assignments, same Transitions, etc."""

    def _get_same_signature_states(self) -> Dict[str, Dict[str, List[str]]]:
        """Group states by their signature in a dict.

        This function gets the signature of all states and uses them to group the states by their signature.
        The signature is a string that comprises all transitions and assignments in an ordered manner.
        In this way, two states sharing the same signature are doing the same thing -- and can therefore be grouped
        (and merged later).
        """
        ret: Dict[str, Dict[str, List[str]]] = {}
        for workername, statelist in self.states.items():
            worker_dict = {}
            for state in statelist:
                if state.signature not in worker_dict:
                    worker_dict[state.signature] = [state.name]
                else:
                    worker_dict[state.signature].append(state.name)

            ret[workername] = worker_dict

        return ret

    def _merge_same_signature_states(self, workername: str, state_lst: List[str]) -> None:
        """Merge states by re-referencing transitions.

        This function uses a list of given states and merges them by preserving the first state in the list and
        pointing all references to the other (merged) states to this first state. The merged states are now unreachable
        and are deleted.

        In this process, a state may now have several transitions pointing to the same target state.
        These transitions are also merged along the way.
        """
        if len(state_lst) < 2:
            return

        target_state_name = state_lst[0]
        merged_state_names = state_lst[1:]

        target_state = next(state for state in self.states[workername] if state.name == target_state_name)

        # Go through all states of the worker and change the target of transitions:
        # The transition to a merged state will point afterwards to the target state.

        for state in self.states[workername]:
            new_transitions: List[Tuple[Renderable, StateProto]] = []

            set_of_tgt_states: Set[str] = set()

            for condition, target in state._transitions:
                if target.name in merged_state_names:
                    target = target_state

                if target.name in set_of_tgt_states:
                    tmplst = []
                    for c, t in new_transitions:
                        if t == target:
                            c = Any(c, condition)
                        tmplst.append((c, t))
                    new_transitions = tmplst
                else:
                    new_transitions.append((condition, target))
                    set_of_tgt_states.add(target.name)

            # FIXME: We should add a modifier to the state class for that.
            state._transitions = new_transitions  # type:ignore

        # Now, we can delete the merged states

        worker = self.workers[workername]
        worker._states = [state for state in worker.states if state.name not in merged_state_names]
        worker._state_names = set([state.name for state in worker.states])

    def _same_signature_state_merging_single_iteration(self) -> int:
        """Executes a single iteration and returns the number of merged states.

        For this purpose, the signatures of all states are extracted and grouped.
        Then, the identical states are passed to the merge function.

        This means
        """
        signatures = self._get_same_signature_states()
        ret = 0

        for workername, workerdict in signatures.items():
            mergelist = [lst for lst in workerdict.values() if len(lst) > 1]

            for merge_items in mergelist:
                ret += len(merge_items) - 1
                self._merge_same_signature_states(workername, merge_items)
        return ret

    def state_merging(self) -> None:
        """Entry-point for the state merging procedure.

        This function loops over iterations of the state merging algorithm.
        In each step, identical states are merged based on their signature. Consider the state sequence shown
        in the diagram

        ```mermaid
        stateDiagram-v2
            S1 --> S2
            S1 --> S4
            S2 --> S3
            S4 --> S5
            S5 --> Final
            S3 --> Final
        ```

        Consider S5 and S3 are having the same assigns and same transitions.
        Also, the second pair S4 and S2 share the same assigns but not the same transitions since the following states
        are not the same.

        After the first iteration, the states S5 and S3 are merged to a state S3_5:
        ```mermaid
        stateDiagram-v2
            S1 --> S2
            S1 --> S4
            S2 --> S3_5
            S4 --> S3_5
            S3_5 --> Final
        ```

        Now, S4 and S2 not only share the same assignments but also the same transitions. These are merged
        in the following iteration.
        ```mermaid
        stateDiagram-v2
            S1 --> S2_4
            S2_4 --> S3_5
            S3_5 --> Final
        ```

        After this iteration there is no possible further merge. Therefore the next iteration will not change the
        state diagram and will end the procedure.
        """
        while self._same_signature_state_merging_single_iteration() > 0:
            pass
