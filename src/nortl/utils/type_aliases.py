"""Provides type aliases for common types."""

from typing import TYPE_CHECKING, Optional

from typing_extensions import TypeAlias

__all__ = [
    'IntSlice',
]

# slice became generic in 2024, but is somewhat broken (still includes Any?))
if TYPE_CHECKING:
    IntSlice: TypeAlias = slice[Optional[int], Optional[int], Optional[int]]
else:
    IntSlice = slice  # type: ignore[misc]
