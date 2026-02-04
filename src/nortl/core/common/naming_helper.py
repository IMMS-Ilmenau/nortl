from typing import Any, Dict

from .debug import DebugEntity


class NamedEntity(DebugEntity):
    """Model a named something in Verilog and implement the feature to add metadata.

    This class will (in future) ensure that there are no naming collisions since all names of verilog objects will be stored here.
    To add traceability, this class inherits from DebugEntity that stores the current execution trace.
    """

    def __init__(self, name: str) -> None:
        super().__init__()
        self._metadata: Dict[str, Any] = {}
        self._name = name

    @property
    def name(self) -> str:
        """Just return name."""
        return self._name

    def get_metadata(self, key: str, default: Any = None) -> Any:
        """Get metadata item."""
        return self._metadata.get(key, default)

    def set_metadata(self, key: str, value: Any) -> None:
        """Set metadata item."""
        self._metadata[key] = value

    def has_metadata(self, key: str) -> bool:
        """Test if a certain key is present in metadata."""
        return key in self._metadata
