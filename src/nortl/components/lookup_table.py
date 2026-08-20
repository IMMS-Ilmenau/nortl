from __future__ import annotations

from math import ceil, log2
from typing import Generic, Iterator, Optional, Sequence, TypeVar, cast, overload

from nortl.core import IfThenElse
from nortl.core.operations import to_renderable
from nortl.core.protocols import Operand, Renderable

T_Entry = TypeVar('T_Entry')


class LookupTable(Generic[T_Entry]):
    """A read-only, list-like lookup table that compiles to a combinational `IfThenElse` chain.

    The table wraps a fixed Python sequence of values. Each entry may be a build-time
    constant (`int`/`bool`), a live `Renderable` (signal or expression), or a nested
    `LookupTable` (list-of-lists). Given an index, `read()` returns the selected value as a
    `Renderable` by chaining `IfThenElse` — the same mechanism as a hand-written lookup.
    Out-of-range indices yield the configurable `default`.

    The class is engine-independent: it is a pure expression builder that can be constructed
    anywhere, even before an engine exists.

    Example:
    ```python
    table = LookupTable([10, 20, 30, 40], default=0)
    idx = engine.define_input('IDX', width=4)
    engine.set(out, table.read(idx))
    ```
    """

    def __init__(self, values: Sequence[T_Entry], default: Operand = 0) -> None:
        """Initialize the lookup table.

        Arguments:
            values: Fixed sequence of entries. Each entry is an `int`/`bool` (baked in as a
                constant), a `Renderable` (muxed through as-is), or a nested `LookupTable`.
            default: Value returned for out-of-range indices (final `else` branch). Must be an
                `int`/`bool` or `Renderable` — not a `LookupTable`.
        """
        if isinstance(default, LookupTable) or not (isinstance(default, (int, bool)) or hasattr(default, 'render')):
            raise TypeError('default must be an int/bool or Renderable, not a LookupTable')
        vals: list[T_Entry] = []
        for v in values:
            if isinstance(v, (int, bool)) or isinstance(v, LookupTable) or hasattr(v, 'render'):
                vals.append(v)
            else:
                raise TypeError(f'unsupported LookupTable entry: {v!r}')
        self._values = vals
        self._default = default
        self.length = len(vals)
        self.index_width = max(1, ceil(log2(max(1, self.length))))
        widths: list[int] = []
        for v in vals:
            if isinstance(v, (int, bool)):
                widths.append(max(1, v.bit_length()))
            elif isinstance(v, LookupTable):
                continue  # LookupTable entries are skipped in width inference
            else:
                w = getattr(v, 'operand_width', None)
                if w is not None:
                    widths.append(w)
        self.value_width: Optional[int] = max(widths) if widths else None

    def read(self, index: Operand) -> Renderable:
        """Perform a hardware lookup: return the entry selected by `index` as a `Renderable`.

        The result is a pure combinational `IfThenElse` chain — safe to use inside any
        thread/condition context and to feed directly into `engine.set(...)`. Indices
        `>= length` (or with high bits set) yield `default`.

        Arguments:
            index: Non-negative `int`/`bool` or `Renderable` index.

        Raises:
            TypeError: If the table contains `LookupTable` entries (compose rows manually
                with `IfThenElse`), or if `index` is not a valid `Operand`.
            ValueError: If `index` is a negative `int` (hardware indices are unsigned; use
                `__getitem__` for build-time wrap-around).
        """
        if any(isinstance(v, LookupTable) for v in self._values):
            raise TypeError('read() is not supported on a table containing LookupTable entries; compose rows manually with IfThenElse')
        if isinstance(index, int) and index < 0:
            raise ValueError('hardware index must be non-negative')
        idx = to_renderable(index)
        ret = to_renderable(self._default)
        for i, value in enumerate(self._values):
            # Nested entries are rejected above, so every value is a plain Operand here.
            ret = IfThenElse(idx == i, to_renderable(cast(Operand, value)), ret)
        return ret

    @overload
    def __getitem__(self, index: int) -> T_Entry: ...
    @overload
    def __getitem__(self, index: Renderable) -> Renderable: ...
    def __getitem__(self, index: Operand) -> T_Entry | Renderable:
        """Dual-mode indexing.

        An `int`/`bool` index returns the raw element directly (native list semantics:
        negative indices wrap around, out-of-range raises `IndexError`) — a plain Python
        `int` for int entries, the `Renderable` itself for `Renderable` entries, or the
        nested `LookupTable` for table entries. A `Renderable` index delegates to `read()`
        (hardware lookup).
        """
        if isinstance(index, (int, bool)):
            return self._values[index]
        return self.read(index)

    def __len__(self) -> int:
        """Return the number of entries."""
        return self.length

    def __iter__(self) -> Iterator[T_Entry]:
        """Iterate over the raw entries."""
        return iter(self._values)

    @property
    def values(self) -> list[T_Entry]:
        """The raw entries (plain reference; do not mutate)."""
        return self._values
