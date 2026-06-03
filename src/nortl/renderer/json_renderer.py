"""JSON Renderer for noRTL engines."""

from nortl.core.protocols import EngineProto
from nortl.core.serialization import EngineInfo

__all__ = [
    'JsonRenderer',
]


class JsonRenderer:
    """JSON Renderer for noRTL engine."""

    def __init__(self, engine: EngineProto, include_coverage: bool = False):
        self.engine = engine
        self.include_coverage = include_coverage

    def render(self) -> str:
        """Render engine information to JSON string."""
        engine_info = EngineInfo.from_engine(self.engine, include_coverage=self.include_coverage)
        return engine_info.model_dump_json(indent=2)
