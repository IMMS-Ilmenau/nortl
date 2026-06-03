"""Models of records in coverage files."""

from __future__ import annotations

from typing import Annotated, Any, Dict, List, Literal, Mapping, Optional, Protocol, Self, Sequence, Tuple, Union

from pydantic import BaseModel, Field, TypeAdapter

from nortl.core.protocols import CoverGroupProto, CoverPointProto, EngineProto, Renderable, StateProto
from nortl.core.serialization.engine_info import EngineInfo

__all__ = [
    'AnyRecord',
    'CoverGroupRecord',
    'CoverPointRecord',
    'CoverageParseError',
    'InfoRecord',
    'StateCoverageRecord',
    'TransitionCoverageRecord',
    'parse_records',
]


class CoverageParseError(RuntimeError):
    """Error raised when parsing of coverage records fails."""


class AnnotationTarget(Protocol):
    """Protocol for annotation target. It wraps the final engine and provides a mapping of states for faster lookup."""

    @property
    def engine(self) -> EngineProto: ...
    @property
    def states(self) -> Mapping[str, StateAnnotationTarget]: ...

    @property
    def covergroups(self) -> Mapping[str, CoverGroupProto]: ...

    def back_annotate_coverpoint(
        self,
        name: str,
        state: StateProto,
        condition: Union[Renderable, str],
        group: Optional[CoverGroupProto] = ...,
        group_coords: Optional[Sequence[int]] = ...,
    ) -> None: ...
    def back_annotate_covergroup(self, name: str, axis: Sequence[Union[Renderable, str]], limits: Sequence[Tuple[int, int]]) -> None: ...


class StateAnnotationTarget(Protocol):
    state: StateProto

    def get_metadata(self, key: str, default: Any = None) -> Any: ...
    def set_metadata(self, key: str, value: Any) -> None: ...
    def has_metadata(self, key: str) -> bool: ...


# Information record
class InfoRecord(BaseModel, extra='forbid'):
    """Record with information about the noRTL engine and test time.

    Only one info record is allowed per file.
    """

    type: Literal['info'] = Field(..., title='Record type')
    engine: EngineReference = Field(..., title='Engine reference')
    test: Optional[TestInfo] = Field(None, title='Test information')


class EngineReference(BaseModel, extra='forbid'):
    """Engine reference."""

    name: str = Field(..., title='Engine', description='Name of the engine.')
    sha256sum: str = Field(..., title='SHA256 checksum', description='Checksum of engine data.')

    @classmethod
    def from_engine_info(cls, engine_info: EngineInfo) -> Self:
        """Create engine reference from full engine information."""
        return cls(name=engine_info.engine.name, sha256sum=engine_info.sha256sum)


class TestInfo(BaseModel, extra='forbid'):
    """Test information."""

    name: str = Field(..., title='Test name', description='Name of the test.')
    start_time: str = Field(..., title='Start time', description='Start time of the test.')


# Coverage records
class StateCoverageRecord(BaseModel, extra='forbid'):
    """Record for state coverage."""

    type: Literal['state'] = Field(..., title='Record type')
    state: str = Field(..., title='State', description='Name of the state.')
    covered: bool = Field(..., title='State coverage', description='Coverage information for the state.')

    def annotate(self, target: AnnotationTarget) -> None:
        """Annotate coverage to engine."""
        state = target.states[self.state]
        state.set_metadata('State Coverage', self.covered or state.get_metadata('State Coverage', False))


class TransitionCoverageRecord(BaseModel, extra='forbid'):
    """Record for transition coverage."""

    type: Literal['transition'] = Field(..., title='Record type')
    source: str = Field(..., title='Source state', description='Name of the source state.')
    target: str = Field(..., title='Target state', description='Name of the target state.')
    covered: bool = Field(..., title='Transition coverage', description='Coverage information for the transition.')

    def annotate(self, target: AnnotationTarget) -> None:
        """Annotate coverage to engine."""
        state = target.states[self.source]
        if state.has_metadata('Transition Coverage'):
            cov = state.get_metadata('Transition Coverage')
            if self.target not in cov:
                cov[self.target] = self.covered
            else:
                cov[self.target] |= self.covered
        else:
            state.set_metadata('Transition Coverage', {self.target: self.covered})


class CoverPointRecord(BaseModel, extra='forbid'):
    """Record for coverage point.

    A coverage point is a combination of a reached state with a met condition.

    This means, a covered point means: I saw the exact state and met the condition in this state.
    In addition, coverage points may be grouped together by group names.

    In a later report generation, we need to know, how to map out the points in a diagram or csv file.
    It would be really hard to then parse the condition and knit things together, therefore we store the
    coordinates of the point along with the coordinates in group_coords.
    """

    type: Literal['coverpoint'] = Field(..., title='Record type')
    state: str = Field(..., title='State', description='Name of the state.')
    condition: str = Field(..., title='Condition', description='Condition of the coverage point.')
    point_name: str = Field(..., title='Name', description='Name of the coverage point.')
    group_name: Optional[str] = Field(None, title='Group', description='Name of the coverage group.')
    group_coords: Optional[List[int]] = Field(None, title='Group coordinates', description='Coordinates inside the coverage group.')
    covered: bool = Field(..., title='Coverage', description='Coverage information for the coverage point.')

    @classmethod
    def from_coverpoint(cls, coverpoint: CoverPointProto, covered: bool) -> Self:
        """Create record from coverpoint."""
        return cls(
            type='coverpoint',
            state=coverpoint.state.name,
            condition=coverpoint.condition,
            point_name=coverpoint.name,
            group_name=coverpoint.group.name if coverpoint.group else None,
            group_coords=list(coverpoint.group_coords) if coverpoint.group_coords else None,
            covered=covered,
        )

    def annotate(self, target: AnnotationTarget) -> None:
        """Annotate coverage to engine."""
        state = target.states[self.state]
        group = target.covergroups[self.group_name] if self.group_name else None

        target.back_annotate_coverpoint(self.point_name, state.state, condition=self.condition, group=group, group_coords=self.group_coords)

        if state.has_metadata('Cover Points'):
            cp: Dict[str, bool] = state.get_metadata('Cover Points')
            if self.point_name not in cp:
                cp[self.point_name] = self.covered
            else:
                cp[self.point_name] |= self.covered
        else:
            state.set_metadata('Cover Points', {self.point_name: self.covered})


class CoverGroupRecord(BaseModel, extra='forbid'):
    """Coverage group."""

    type: Literal['covergroup'] = Field(..., title='Record type')
    name: str = Field(..., title='Name', description='Name of the coverage group.')
    axis: List[str] = Field(..., title='Axis names', description='List of axis names.')
    limits: List[Tuple[int, int]] = Field(..., title='Limits', description='List of axis limits.')

    def annotate(self, target: AnnotationTarget) -> None:
        """Annotate coverage to engine."""
        target.back_annotate_covergroup(self.name, self.axis, self.limits)

    @classmethod
    def from_covergroup(cls, covergroup: CoverGroupProto) -> Self:
        """Create record from covergroup."""
        return cls(
            type='covergroup',
            name=covergroup.name,
            axis=list(covergroup.axis),
            limits=list(covergroup.limits),
        )


AnyRecord = Annotated[
    Union[InfoRecord, StateCoverageRecord, TransitionCoverageRecord, CoverPointRecord, CoverGroupRecord], Field(discriminator='type')
]


def parse_records(
    lines: Sequence[str],
) -> Tuple[InfoRecord, Sequence[Union[StateCoverageRecord, TransitionCoverageRecord, CoverPointRecord, CoverGroupRecord]]]:
    """Parse sequence of records from lines of a coverage file.

    Returns the information record (if found) and a sequence of coverage records.
    """
    ta: TypeAdapter[AnyRecord] = TypeAdapter(AnyRecord)

    info_record: Optional[InfoRecord] = None
    coverage_records: List[Union[StateCoverageRecord, TransitionCoverageRecord, CoverPointRecord, CoverGroupRecord]] = []

    try:
        for line, text in enumerate(lines):
            record = ta.validate_json(text)
            if record.type != 'info':
                coverage_records.append(record)
            elif info_record is None:
                info_record = record
            elif info_record.engine != record.engine:
                raise CoverageParseError(
                    f'Found conflicting information record in line {line}, but only one record is allowed per file. '
                    'Coverage file may be corrupted.\n'
                    'This could be caused by writing the coverage information from two or more simulation runs to the same file.\n'
                    'Instead, each simulation run should be written to a separate file.\n\n'
                    f'First information record was: {info_record.model_dump_json()}\n'
                    f'Second information record was: {record.model_dump_json()}'
                )
    except Exception as e:
        raise CoverageParseError(f'Failed to parse record in line {line}: {e}')

    if info_record is None:
        raise CoverageParseError('Found no engine information record. Coverage file may be corrupted.')
    if len(coverage_records) == 0:
        raise CoverageParseError('Found no coverage records in the file..')

    return info_record, coverage_records
