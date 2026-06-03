"""JSON type definition for engine serialization."""

from typing import Dict, Final, List, Optional, Self

from pydantic import BaseModel, Field

from nortl.core.modifiers import unwrap_modifiers
from nortl.core.protocols import SIGNAL_TYPES, EngineProto, Renderable, StateProto, WorkerProto

from .checksum import create_sha256sum
from .coverage_overlay import DEFAULT_COVERAGE_NAME, EngineCoverage

__all__ = [
    'Engine',
    'EngineInfo',
    'State',
    'Worker',
]

VERSION: Final = '0.2'
"""Version of noRTL Engine Definition."""


# NOTE: The Engine Information intentionally uses a limited feature set of pydantic, to stay compatible with JSON Type Definition.
# Specifically, no union types are allowed!


class UnconditionalAssignment(BaseModel, extra='forbid'):
    """Unconditional assignment."""

    signal: str = Field(..., title='Signal', description='Name of the assignment target.')
    value: str = Field(..., title='Value', description='Value for the signal.')
    type: SIGNAL_TYPES = Field(..., title='Signal type', description='Type of the signal.')


class ConditionalAssignment(BaseModel, extra='forbid'):
    """Conditional assignment."""

    signal: str = Field(..., title='Signal', description='Name of the signal (assignment target).')
    cases: Dict[str, str] = Field(
        ..., title='Cases', description='Mapping of assignment cases, consisting of pairs of conditions and values for the signal.'
    )
    type: SIGNAL_TYPES = Field(..., title='Signal type', description='Type of the signal.')


class Transition(BaseModel, extra='forbid'):
    """Transition."""

    target: str = Field(..., title='Target state', description='Name of the target state.')
    condition: Optional[str] = Field(..., title='Transition condition', description='Optional condition of the transition.')


class State(BaseModel, extra='forbid'):
    """NoRTL State."""

    name: str = Field(..., title='Name', description='Name of the state.')
    unconditional_assignments: List[UnconditionalAssignment] = Field(
        ..., title='Unconditional assignments', description='List of unconditional assignments.'
    )
    conditional_assignments: List[ConditionalAssignment] = Field(..., title='Conditional assignments', description='List of conditional assignments.')
    transitions: List[Transition] = Field(..., title='Transition', description='List of outgoing transitions from this state')

    @classmethod
    def from_state(cls, state: StateProto) -> Self:
        """Create state model from noRTL state."""

        return cls(
            name=state.name,
            unconditional_assignments=cls._create_unconditional_assignments(state),
            conditional_assignments=cls._create_conditional_assignments(state),
            transitions=cls._create_transitions(state),
        )

    @classmethod
    def serialize_condition(cls, condition: Renderable) -> Optional[str]:
        """Serialize condition."""
        if condition.is_constant and condition.value == 1:  # type: ignore[attr-defined]
            return None
        else:
            return condition.render()

    @classmethod
    def _create_unconditional_assignments(cls, state: StateProto) -> List[UnconditionalAssignment]:
        """Serialize unconditional assignments."""
        return [
            UnconditionalAssignment(
                signal=f'{assignment.signal}',
                value=f'{assignment.value}',
                type=f'{unwrap_modifiers(assignment.signal).type}',  # type: ignore[arg-type, attr-defined]
            )
            for assignment in state.assignments
            if assignment.unconditional
        ]

    @classmethod
    def _create_conditional_assignments(cls, state: StateProto) -> List[ConditionalAssignment]:
        """Serialize conditional assignments."""
        return [
            ConditionalAssignment(
                signal=f'{assignment.signal}',
                cases={f'{condition}': f'{value}' for condition, value in assignment.flatten_cases()},
                type=f'{unwrap_modifiers(assignment.signal).type}',  # type: ignore[arg-type, attr-defined]
            )
            for assignment in state.assignments
            if not assignment.unconditional
        ]

    @classmethod
    def _create_transitions(cls, state: StateProto) -> List[Transition]:
        """Serialize transitions."""
        return [Transition(target=target.name, condition=cls.serialize_condition(condition)) for (condition, target) in state.transitions]


class Worker(BaseModel, extra='forbid'):
    """NoRTL Worker."""

    name: str = Field(..., title='Name', description='Name of the worker.')
    states: Dict[str, State] = Field(..., title='States', description='Mapping of state names to states.')

    @classmethod
    def from_worker(cls, worker: WorkerProto) -> Self:
        """Create worker model from noRTL worker."""

        return cls(name=worker.name, states={state.name: State.from_state(state) for state in worker.states})


class Engine(BaseModel, extra='forbid'):
    """NoRTL Engine."""

    name: str = Field(..., title='Name', description='Name of the engine.')
    workers: Dict[str, Worker] = Field(..., title='Workers', description='Mapping of worker names to workers.')

    @classmethod
    def from_engine(cls, engine: EngineProto) -> Self:
        """Create engine model from noRTL engine."""

        return cls(
            name=engine.module_name,
            workers={worker.name: Worker.from_worker(worker) for worker in engine.workers.values()},
        )


# Engine Info
class EngineInfo(BaseModel, extra='forbid'):
    """NoRTL Engine Information."""

    sha256sum: str = Field(..., title='SHA256 checksum', description='Checksum calculated from the engine data, i.e. the engine field.')
    version: str = Field(..., title='Model version', description='Version of noRTL engine information. This is not the version of the engine itself.')
    engine: Engine = Field(..., title='noRTL Engine', description='Serialized noRTL engine.')
    coverage_overlays: Dict[str, EngineCoverage] = Field(..., title='Coverage overlays', description='Mapping of test names to coverage overlays.')

    @classmethod
    def from_engine(cls, engine: EngineProto, include_coverage: bool = False) -> Self:
        """Create engine information from noRTL engine.

        Arguments:
            engine: noRTL engine.
            include_coverage: If True, will include coverage information for the engine.
                This should only be used, if coverage information was back-annotated to the engine.
                All coverage information will be contained in a "default" overlay.
                If the coverage was merged from multiple tests, this information is lost.
        """

        engine_model = Engine.from_engine(engine)
        coverage_overlays: Dict[str, EngineCoverage] = {}

        # Calculate SHA256 checksum from engine info
        checksum = create_sha256sum(engine_model.model_dump_json())

        # Add default coverage overlay
        if include_coverage:
            coverage_overlays[DEFAULT_COVERAGE_NAME] = EngineCoverage.from_engine(engine)

        return cls(
            sha256sum=checksum,
            version=VERSION,
            engine=engine_model,
            coverage_overlays=coverage_overlays,
        )

    def to_json(self, indent: Optional[int] = 2) -> str:
        """Dump engine information to JSON string."""
        return self.model_dump_json(indent=indent)
