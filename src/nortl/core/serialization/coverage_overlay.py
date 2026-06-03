"""JSON type definition for coverage overlays.

Coverage overlays are a part of the engine information.
"""

from typing import Dict, Final, List, Mapping, Optional, Protocol, Self, Sequence, Tuple

from pydantic import BaseModel, Field

from nortl.core.protocols import NamedEntityProto, Renderable, StateProto

__all__ = [
    'DEFAULT_COVERAGE_NAME',
    'EngineCoverage',
    'StateCoverage',
    'TransitionCoverage',
    'WorkerCoverage',
]

DEFAULT_COVERAGE_NAME: Final = 'default'
"""Name for default coverage overlay."""


# Coverage overlay requires only very little signature of the noRTL engine
class EngineLikeProto(Protocol):
    @property
    def workers(self) -> Mapping[str, 'WorkerLikeProto']: ...


class WorkerLikeProto(NamedEntityProto, Protocol):
    @property
    def states(self) -> Sequence['StateLikeProto']: ...


class StateLikeProto(NamedEntityProto, Protocol):
    @property
    def transitions(self) -> Sequence[Tuple[Renderable, StateProto]]: ...


class TransitionCoverage(BaseModel, extra='forbid'):
    """Transition coverage overlay."""

    coverage: bool = Field(..., title='Transition coverage', description='Coverage information for the transition.')


class StateCoverage(BaseModel, extra='forbid'):
    """State coverage overlay."""

    coverage: bool = Field(..., title='State coverage', description='Coverage information for the state.')
    transitions: List[TransitionCoverage] = Field(..., title='Transition coverage', description='Coverage information for transitions.')

    # TODO add cover points

    @classmethod
    def from_state(cls, state: StateLikeProto) -> Self:
        """Create state coverage overlay from noRTL state."""

        return cls(
            coverage=state.get_metadata('State Coverage', False),
            transitions=cls._create_transitions_coverage(state),
        )

    @classmethod
    def _create_transitions_coverage(cls, state: StateLikeProto) -> List[TransitionCoverage]:
        """Serialize transitions."""
        transition_coverage = state.get_metadata('Transition Coverage', {})
        return [TransitionCoverage(coverage=transition_coverage.get(target.name, False)) for (_, target) in state.transitions]


class WorkerCoverage(BaseModel, extra='forbid'):
    """Worker coverage overlay."""

    states: Dict[str, StateCoverage] = Field(..., title='States', description='Mapping of state names to states.')

    @classmethod
    def from_worker(cls, worker: WorkerLikeProto) -> Self:
        """Create worker coverage overlay from noRTL worker."""

        return cls(states={state.name: StateCoverage.from_state(state) for state in worker.states})


class EngineCoverage(BaseModel, extra='forbid'):
    """Engine coverage overlay."""

    name: str = Field(
        ..., title='Name', description='Name of the coverage overlay. Typically this is the name of the test where the coverage was collected.'
    )
    start_time: Optional[str] = Field(None, title='State time', description='Start time for test where coverage was collected.')
    workers: Dict[str, WorkerCoverage] = Field(..., title='Workers', description='Mapping of worker names to workers.')

    # TODO add covergroups

    @classmethod
    def from_engine(cls, engine: EngineLikeProto) -> Self:
        """Create default engine coverage overlay from noRTL engine."""

        return cls(
            name=DEFAULT_COVERAGE_NAME,
            start_time=None,
            workers={worker.name: WorkerCoverage.from_worker(worker) for worker in engine.workers.values()},
        )
