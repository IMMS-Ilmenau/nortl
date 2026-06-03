from typing import Dict, Mapping, Optional, Sequence, Tuple, Union

from nortl.core.coverage.statistics import CoverageStatistics
from nortl.core.protocols import CoverGroupProto, CoverPointProto, EngineProto, Renderable, StateProto

__all__ = [
    'CoverGroup',
    'CoverPoint',
]


class CoverPoint:
    def __init__(
        self,
        name: str,
        state: StateProto,
        condition: Union[Renderable, str],
        group: Optional[CoverGroupProto] = None,
        group_coords: Optional[Sequence[int]] = None,
    ) -> None:
        self.name = name
        self.state = state
        self.condition = f'{condition}'
        self.group = group
        self.group_coords = group_coords

        # Register inside covergroup
        if group:
            if not group_coords:
                raise RuntimeError('Coverpoint has no group coordinates but is associated to a coverage group!')

            group.register_coverpoint(self)

    @property
    def covered(self) -> bool:
        """Coverage state."""
        cp: Mapping[str, bool] = self.state.get_metadata('Cover Points')
        return cp[self.name]


class CoverGroup:
    def __init__(self, engine: EngineProto, name: str, axis: Sequence[Union[Renderable, str]], limits: Sequence[Tuple[int, int]]) -> None:
        self.engine = engine
        self.name = name
        self.axis: Sequence[str] = tuple(f'{signal}' for signal in axis)
        self.limits = limits
        self._coverpoints: Dict[str, CoverPointProto] = {}

    @property
    def coverpoints(self) -> Mapping[str, CoverPointProto]:
        """Cover points in cover group."""
        return self._coverpoints

    def register_coverpoint(self, coverpoint: CoverPointProto) -> None:
        """Register coverpoint. This is used by the coverpoint."""
        if coverpoint.name not in self.coverpoints:
            self._coverpoints[coverpoint.name] = coverpoint

    def extract(self) -> Mapping[Tuple[int, ...], bool]:
        """Extract cover group."""
        res: Dict[Tuple[int, ...], bool] = {}

        for coverpoint in self.coverpoints.values():
            if coverpoint.group_coords is None:
                raise RuntimeError('Coverpoint has no group coordinates but is associated to a coverage group!')

            res[tuple(coverpoint.group_coords)] = coverpoint.covered

        return res

    @property
    def coverage(self) -> CoverageStatistics:
        """Coverage statistics."""
        covered = sum(coverpoint.covered for coverpoint in self.coverpoints.values())
        total = len(self.coverpoints)

        return CoverageStatistics(f'Covergroup coverage: {self.name}', covered, total)
