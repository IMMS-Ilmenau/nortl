"""Coverage Manager."""

import itertools as it
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple, Union

from nortl.core.coverage.annotator import Annotator
from nortl.core.coverage.coverpoint import CoverGroup, CoverPoint
from nortl.core.coverage.statistics import CoverageStatistics
from nortl.core.operations import All, to_renderable
from nortl.core.protocols import CoverGroupProto, EngineProto, Renderable, StateProto
from nortl.core.serialization import EngineCoverage, EngineInfo

from .records import CoverPointRecord, StateCoverageRecord, TestInfo, TransitionCoverageRecord, parse_records

__all__ = [
    'CoverageManager',
]


class CoverageManager:
    """Coverage Manager.

    The coverage manager provides methods for annotating state coverage and transition coverage.
    In addition, functional coverage with groups and points can be modelled.

    To enable coverage monitoring, call the two `monitor_*` methods after building your engine:

    ```python
    # Build engine
    engine = build_engine()

    engine.coverage.monitor_state_coverage()
    engine.coverage.monitor_transition_coverage()
    ```

    !!! warning

        Coverage monitoring should be enabled after all engine optimizations are completed.
        Calling the `monitor_*` methods will add print statements to all states and transitions in the engine.
        If the transitions are modified later-on, e.g. by merging states, the coverage prints may be corrupted.

    After testing, you can back-annotate the coverage information:

    ```python
    # Build engine again
    engine = build_engine()

    # One or more filepaths to coverage files
    coverage_file = Path('my_engine.coverage.jsonl')

    # Create coverage overlay
    cov = engine.coverage.annotate(coverage_file)

    print(cov.state_coverage)
    print(cov.transition_coverage)
    ```

    !!! note

        noRTL includes a hash of the engine inside the coverage prints.
        When back-annotating the collected coverage information, this hash is checked against a fresh hash of the engine.
    """

    def __init__(self, engine: EngineProto) -> None:
        self.engine = engine

        self._state_coverage_enabled = False
        self._transition_coverage_enabled = False
        self._coverpoints: Dict[str, CoverPoint] = {}
        self._covergroups: Dict[str, CoverGroup] = {}

        # Helper properties
        self._states: Optional[Mapping[str, StateProto]] = None
        self._engine_info: Optional[EngineInfo] = None

        # Coverage statistics
        self._state_coverage: Optional[CoverageStatistics] = None
        self._transition_coverage: Optional[CoverageStatistics] = None
        self._coverpoint_coverage: Optional[CoverageStatistics] = None

    # Helper properties
    @property
    def states(self) -> Mapping[str, StateProto]:
        """Flat mapping of all states."""
        if self._states is None:
            self._states = {}
            for worker_states in self.engine.states.values():
                self._states.update({state.name: state for state in worker_states})
        return self._states

    @property
    def engine_info(self) -> EngineInfo:
        """Serialized engine information."""
        if self._engine_info is None:
            self._engine_info = EngineInfo.from_engine(self.engine)
        return self._engine_info

    @property
    def enabled(self) -> bool:
        """Indicates if the engine has any coverage monitoring."""
        return self._state_coverage_enabled or self._transition_coverage_enabled or len(self._coverpoints) > 0

    # Cover points
    @property
    def coverpoints(self) -> Mapping[str, CoverPoint]:
        """Cover points."""
        return self._coverpoints

    @property
    def covergroups(self) -> Mapping[str, CoverGroup]:
        """Cover groups."""
        return self._covergroups

    # Back annotation
    def back_annotate_coverpoint(
        self,
        name: str,
        state: StateProto,
        condition: Union[Renderable, str],
        group: Optional[CoverGroupProto] = None,
        group_coords: Optional[Sequence[int]] = None,
    ) -> None:
        """Back annotate coverpoint to engine."""
        if name not in self.coverpoints:
            self._coverpoints[name] = CoverPoint(name, state, condition, group=group, group_coords=group_coords)

    def back_annotate_covergroup(self, name: str, axis: Sequence[Union[Renderable, str]], limits: Sequence[Tuple[int, int]]) -> None:
        """Back annotate covergroup to engine."""
        if name not in self.covergroups:
            self._covergroups[name] = CoverGroup(self.engine, name, axis, limits)

    # Coverage monitoring
    def monitor_state_coverage(self) -> None:
        """Monitor state coverage.

        This enables emission of state coverage records in the Verilog output via the [CoverageWriter][nortl.renderer.verilog_utils.print_handlers.CoverageWriter] print handler.
        """
        if self._state_coverage_enabled:
            raise RuntimeError('State coverage monitoring was already enabled before.')
        self._state_coverage_enabled = True

        # TODO to avoid spamming the coverage file with emissions on every clock cycle, consider triggering the state coverage only on state enter

        for worker_states in self.engine.states.values():
            for state in worker_states:
                record = StateCoverageRecord(type='state', state=state.name, covered=True)
                state.print(record, handler='coverage_writer', target=self.engine.module_name)

    def monitor_transition_coverage(self) -> None:
        """Monitor transition coverage.

        This enables emission of transition coverage records in the Verilog output via the [CoverageWriter][nortl.renderer.verilog_utils.print_handlers.CoverageWriter] print handler.
        """
        if self._transition_coverage_enabled:
            raise RuntimeError('Transition coverage monitoring was already enabled before.')
        self._transition_coverage_enabled = True

        for worker_states in self.engine.states.values():
            for state in worker_states:
                for condition, next_state in state.transitions:
                    record = TransitionCoverageRecord(type='transition', source=state.name, target=next_state.name, covered=True)
                    state.print_if(condition, record, handler='coverage_writer', target=self.engine.module_name)

    def coverpoint(
        self,
        condition: Renderable,
        point_name: Optional[str] = None,
        group_name: Optional[str] = None,
        group_coords: Optional[List[int]] = None,
    ) -> str:
        """Create a coverage point."""

        # Automatically name coverpoint
        if point_name is None:
            point_name = f'{self.engine.current_state.name}_cp_{len(self.coverpoints)}'

        # Get group
        if group_name and group_name not in self.covergroups:
            raise ValueError(f'Coverage group {group_name} does not exist!')
        group: Optional[CoverGroup] = self.covergroups[group_name] if group_name else None

        # Save coverpoint
        point = CoverPoint(point_name, self.engine.current_state, condition=to_renderable(condition), group=group, group_coords=group_coords)
        self._coverpoints[point_name] = point

        # Create monitoring print
        self.engine.current_state.print_if(
            condition, CoverPointRecord.from_coverpoint(point, True), handler='coverage_writer', target=self.engine.module_name
        )

        return point_name

    def covergroup(self, name: str, target: List[Tuple[Renderable, int, int]]) -> None:
        """Create a coverage group."""
        if name in self.covergroups:
            raise ValueError(f'Cover group {name} already exists!')

        # Extract axis signals and limits
        axis = tuple(signal for signal, _, _ in target)
        limits = tuple((start, stop) for _, start, stop in target)

        # Save covergroup
        self._covergroups[name] = CoverGroup(self.engine, name, axis, limits)

        # Create coverpoints
        ranges = [range(start, stop + 1) for start, stop in limits]
        for coords in it.product(*ranges):
            condition = All(t == value for t, value in zip(axis, coords))
            self.coverpoint(condition, f'{name}.{coords}', group_name=name, group_coords=coords)  # type: ignore[arg-type]

    # Coverage annotation
    def annotate(self, source_file: Union[Path, str]) -> EngineCoverage:
        """Annotate coverage from file.

        Arguments:
            source_file: Paths to coverage file.

        Returns:
            Coverage overlay, containing the coverage statistics for this source file.
        """

        # Parse records
        source_file = Path(source_file)
        lines = source_file.read_text().splitlines()

        try:
            info_record, coverage_records = parse_records(lines)
        except Exception as e:
            raise e from ValueError(f'Failed to parse coverage file {source_file}')

        # Validate engine information
        if info_record.engine.sha256sum != self.engine_info.sha256sum or info_record.engine.name != self.engine.module_name:
            raise ValueError(
                f'Failed to annotate coverage file {source_file}: '
                f'Engine {self.engine.module_name} (#{self.engine_info.sha256sum[0:8]}) does not match '
                f'engine {info_record.engine.name} (#{info_record.engine.sha256sum[0:8]}) of the parsed coverage file!'
            )

        # Annotate records
        annotator = Annotator(self)
        for record in coverage_records:
            record.annotate(annotator)

        # Commit annotator results and update statistics
        annotator.commit()
        self._update_stats()

        # Create overlay
        if info_record.test is None:
            test_info = TestInfo(name='unknown', start_time='unknown')
        else:
            test_info = info_record.test

        return annotator.as_overlay(test_info)

    # Statistics
    @property
    def state_coverage(self) -> CoverageStatistics:
        """State coverage."""
        if self._state_coverage is None:
            raise RuntimeError('Coverage statistics are not available yet. Please annotate one or more coverage files.')
        return self._state_coverage

    @property
    def transition_coverage(self) -> CoverageStatistics:
        """Transition coverage."""
        if self._transition_coverage is None:
            raise RuntimeError('Coverage statistics are not available yet. Please annotate one or more coverage files.')
        return self._transition_coverage

    @property
    def coverpoint_coverage(self) -> CoverageStatistics:
        """Coverage of all coverpoints (including covergroups)."""
        if self._coverpoint_coverage is None:
            raise RuntimeError('Coverage statistics are not available yet. Please annotate one or more coverage files.')
        return self._coverpoint_coverage

    def _update_stats(self) -> None:
        """Update coverage statistics."""
        self._state_coverage = self._calc_state_coverage()
        self._transition_coverage = self._calc_transition_coverage()
        self._coverpoint_coverage = self._calc_coverpoint_coverage()

    def _calc_state_coverage(self) -> CoverageStatistics:
        """Calculate state coverage."""
        covered = sum(state.get_metadata('State Coverage', False) * 1 for state in self.states.values())
        total = len(self.states)

        return CoverageStatistics('State Coverage', covered, total)

    def _calc_transition_coverage(self) -> CoverageStatistics:
        """Calculate transition coverage."""
        covered = sum(sum(1 * coverage for coverage in state.get_metadata('Transition Coverage', {}).values()) for state in self.states.values())
        total = sum(len(state.transitions) for state in self.states.values())

        return CoverageStatistics('Transition Coverage', covered, total)

    def _calc_coverpoint_coverage(self) -> CoverageStatistics:
        """Calculate coverpoint statistics."""
        covered = sum(coverpoint.covered for coverpoint in self.coverpoints.values())
        total = len(self.coverpoints)

        return CoverageStatistics('Coverpoint Coverage', covered, total)
