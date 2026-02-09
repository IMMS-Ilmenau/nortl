from nortl.core.engine import CoreEngine
from nortl.core.protocols import StateProto


class ReachabilityAnalysisMixin(CoreEngine):
    """Reachability analysis by evaluating state transitions.

    This class realizes the functions to execute a simple reachability analysis.
    For this case, we iterate the state graph of the main worker starting from the reset state.
    We visit all states that are reachable in the sense, that there is a transition with a non-zero
    condition can be taken, and mark them as reachable.

    Along this way, the possible thread start states are used to also iterate through the worker's state graphs.

    The information about reachability is stored in the state's metadata in the key 'reachable'
    """

    # Metadata keys to be uses
    REACHABILITY_KEY = 'reachable'

    def reachability_analysis(self) -> None:
        """Entry point for the reachability analysis.

        This function starts a DFS-like iteration of the state graph.
        Initially, all states are marked (via metadata) as unreachable. Then, the DFS will mark all reachable states.
        The iteration startes at the reset state of the main_worker.
        """
        # First, set all states as unreachable and unvisited

        for statelist in self.states.values():
            for state in statelist:
                state.set_metadata(self.REACHABILITY_KEY, False)

        # Start analysis at the reset state of the main worker
        self._reachability_visit(self.main_worker.reset_state)

    def _reachability_visit(self, state: StateProto) -> None:
        """Visit a state in the reachability analysis.

        This function marks a state as reachable and recurses into the following states.
        The following states are only visited, if the transitions are not constantly off
        (i.e. have a condition being statically False).

        For including the fork-join methods, the recursion also visits the start states of forked processes.
        This is possible, since the states forking new threads are marked via metadata key 'Forked Processes'.
        """
        state.set_metadata(self.REACHABILITY_KEY, True)

        # Visit transition states
        for condition, next_state in state.transitions:
            if (condition == 0).render() != "1'h1":
                # If the condition is not constantly off, we visit the next state
                if not next_state.get_metadata(self.REACHABILITY_KEY):
                    self._reachability_visit(next_state)

        # Visit possibly forked threads
        if state.has_metadata('Forked Processes'):
            for workername, threadid in state.get_metadata('Forked Processes'):
                # Now we have to find the start state in the worker and visit it
                worker = self.workers[workername]
                for workerstate in worker.states:
                    if workerstate.has_metadata('Fork Select ID'):
                        if workerstate.get_metadata('Fork Select ID') == threadid:
                            self._reachability_visit(workerstate)
                            break

    def prune_unreachable_states(self) -> None:
        """Entry point for state pruning.

        Executes a reachability analysis and deletes all states that are not reachable.
        """
        self.reachability_analysis()

        for worker in self.workers.values():
            worker._states = [state for state in worker.states if state.get_metadata(self.REACHABILITY_KEY)]
            worker._state_names = set([state.name for state in worker.states])
