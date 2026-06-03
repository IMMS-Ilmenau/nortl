from typing import Dict, Mapping, Optional, Self, Sequence, Tuple, Union

from nortl.core.common.naming_helper import NamedEntity
from nortl.core.coverage.records import TestInfo
from nortl.core.protocols import CoverageManagerProto, CoverGroupProto, CoverPointProto, EngineProto, Renderable, StateProto, WorkerProto
from nortl.core.serialization import EngineCoverage, WorkerCoverage


class StateProxy(NamedEntity):
    """Proxy helper for state.

    The proxy object is used to capture metadata added by coverage annotation from a single file.
    The metadata later gets commited to the original state, as well as exported as a coverage overlay.
    """

    def __init__(self, state: StateProto) -> None:
        super().__init__(state.name)
        self.state = state

    @property
    def transitions(self) -> Sequence[Tuple[Renderable, StateProto]]:
        return self.state.transitions


class WorkerProxy(NamedEntity):
    """Proxy helper for worker.

    The proxy object is used to mimic the noRTL engine structure when generating a coverage overlay.
    """

    def __init__(self, name: str, states: Sequence[StateProxy]) -> None:
        super().__init__(name)
        self.states = states

    @classmethod
    def mimic(cls, worker: WorkerProto, all_states: Mapping[str, StateProxy]) -> Self:
        """Create worker proxy that mimics original.

        Filters the states for this worker from a flat mapping of all states of the engine.
        """
        worker_states = tuple(all_states[state.name] for state in worker.states)
        return cls(worker.name, worker_states)


class Annotator:
    """Helper class for coverage annotation."""

    def __init__(self, manager: CoverageManagerProto):
        self.manager = manager

        self.states: Dict[str, StateProxy] = {}
        for worker_states in self.engine.states.values():
            self.states.update({state.name: StateProxy(state) for state in worker_states})

    @property
    def engine(self) -> EngineProto:
        """Target noRTL Engine."""
        return self.manager.engine

    @property
    def covergroups(self) -> Mapping[str, CoverGroupProto]:
        """Cover groups."""
        return self.manager.covergroups

    @property
    def coverpoints(self) -> Mapping[str, CoverPointProto]:
        """Cover points."""
        return self.manager.coverpoints

    def back_annotate_coverpoint(
        self,
        name: str,
        state: StateProto,
        condition: Union[Renderable, str],
        group: Optional[CoverGroupProto] = None,
        group_coords: Optional[Sequence[int]] = None,
    ) -> None:
        """Back annotate coverpoint to engine."""
        self.manager.back_annotate_coverpoint(name, state, condition, group=group, group_coords=group_coords)

    def back_annotate_covergroup(self, name: str, axis: Sequence[Renderable | str], limits: Sequence[Tuple[int, int]]) -> None:
        """Back annotate covergroup to engine."""
        self.manager.back_annotate_covergroup(name, axis, limits)

    def commit(self) -> None:
        """Commit annotation results to noRTL engine."""
        for worker_states in self.engine.states.values():
            for state in worker_states:
                proxy = self.states[state.name]
                self.merge_state_coverage(proxy, state)
                self.merge_transition_coverage(proxy, state)
                self.merge_coverpoints(proxy, state)

    @staticmethod
    def merge_state_coverage(proxy: StateProxy, state: StateProto) -> None:
        """Merge state coverage from proxy into state."""
        cov = proxy.get_metadata('State Coverage', False) or state.get_metadata('State Coverage', False)
        state.set_metadata('State Coverage', cov)

    @staticmethod
    def merge_transition_coverage(proxy: StateProxy, state: StateProto) -> None:
        """Merge transition coverage from proxy into state."""
        cov = state.get_metadata('Transition Coverage', {target.name: False for _, target in state.transitions})

        for target, covered in proxy.get_metadata('Transition Coverage', {}).items():
            if covered:
                cov[target] = True

        state.set_metadata('Transition Coverage', cov)

    def merge_coverpoints(self, proxy: StateProxy, state: StateProto) -> None:
        """Merge cover points from proxy into state."""
        cov = state.get_metadata(
            'Cover Points', {point_name: False for point_name, coverpoint in self.coverpoints.items() if coverpoint.state == state}
        )

        for point_name, covered in proxy.get_metadata('Cover Points', {}).items():
            if covered:
                cov[point_name] = True

        state.set_metadata('Cover Points', cov)

    def as_overlay(self, test_info: TestInfo) -> EngineCoverage:
        """Convert to engine coverage overlay."""
        # Split states to individual workers
        workers = {name: WorkerCoverage.from_worker(WorkerProxy.mimic(worker, self.states)) for name, worker in self.engine.workers.items()}

        return EngineCoverage(
            name=test_info.name,
            start_time=test_info.start_time,
            workers=workers,
        )
