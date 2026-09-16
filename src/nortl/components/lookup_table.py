from __future__ import annotations

from math import ceil, log2
from typing import Any, Generic, Iterator, List, Optional, Sequence, Tuple, TypeVar, Union, cast, overload

from nortl.core import All, IfThenElse
from nortl.core.operations import Const, to_renderable
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

        self.updates: List[Tuple[Renderable, Renderable, Renderable]] = []

    # Re-declare so that `Operand` (int/bool/Renderable) is accepted at call sites.
    def update(self, k: Operand, v: Operand, cond: Operand) -> None:
        """Updates Lookup Table at position k with value v -- if condition is met.

        Note that the condition is a Renderable so it might change during the course of your logic.
        Make sure that you only use static values here (or that you really know what you are doing.)
        """
        self.updates.append((to_renderable(k), to_renderable(v), to_renderable(cond)))

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

        # Now also check the updates
        for adr, upd_value, cond in self.updates:
            ret = IfThenElse(All(idx == adr, cond), to_renderable(cast(Operand, upd_value)), ret)

        return ret

    def _require_flat(self, operation: str) -> None:
        if any(isinstance(v, LookupTable) for v in self._values):
            raise TypeError(f'{operation}() is not supported on a table containing LookupTable entries')

    def min(self) -> Renderable:
        """Return the minimum of all entries as a `Renderable` (hardware min tree).

        The result is a pure combinational expression built by folding pairwise
        `IfThenElse(a < b, a, b)` muxes over the entries, so it can be used inside any
        thread/condition context and fed directly into `engine.set(...)`. All-int tables
        constant-fold to a `Const`.

        Raises:
            TypeError: If the table contains `LookupTable` entries.
            ValueError: If the table is empty.
        """
        self._require_flat('min')
        if not self._values:
            raise ValueError('cannot compute min() of an empty LookupTable')
        result = to_renderable(cast(Operand, self._values[0]))
        for value in self._values[1:]:
            v = to_renderable(cast(Operand, value))
            result = IfThenElse(result < v, result, v)
        return result

    def max(self) -> Renderable:
        """Return the maximum of all entries as a `Renderable` (hardware max tree).

        The result is a pure combinational expression built by folding pairwise
        `IfThenElse(a > b, a, b)` muxes over the entries, so it can be used inside any
        thread/condition context and fed directly into `engine.set(...)`. All-int tables
        constant-fold to a `Const`.

        Raises:
            TypeError: If the table contains `LookupTable` entries.
            ValueError: If the table is empty.
        """
        self._require_flat('max')
        if not self._values:
            raise ValueError('cannot compute max() of an empty LookupTable')
        result = to_renderable(cast(Operand, self._values[0]))
        for value in self._values[1:]:
            v = to_renderable(cast(Operand, value))
            result = IfThenElse(result > v, result, v)
        return result

    def sum(self) -> Renderable:
        """Return the sum of all entries as a `Renderable` (hardware adder tree).

        The result is a pure combinational expression built by folding pairwise
        additions over the entries, so it can be used inside any thread/condition
        context and fed directly into `engine.set(...)`. All-int tables
        constant-fold to a `Const`.

        Raises:
            TypeError: If the table contains `LookupTable` entries.
            ValueError: If the table is empty.
        """
        self._require_flat('sum')
        if not self._values:
            raise ValueError('cannot compute sum() of an empty LookupTable')
        result = to_renderable(cast(Operand, self._values[0]))
        for value in self._values[1:]:
            result = result + to_renderable(cast(Operand, value))
        return result

    def count(self, value: Operand) -> Renderable:
        """Return how many entries equal `value` as a `Renderable` (hardware comparator tree).

        Mirrors Python's `list.count()`: returns the number of table entries that compare
        equal to `value`. The result is a pure combinational expression built by folding
        `IfThenElse(entry == value, 1, 0)` terms into an adder tree, so it can be used
        inside any thread/condition context and fed directly into `engine.set(...)`.
        All-int tables constant-fold to a `Const`. An empty table yields `0`.

        Arguments:
            value: `int`/`bool` or `Renderable` to compare against.

        Raises:
            TypeError: If the table contains `LookupTable` entries.
        """
        self._require_flat('count')
        target = to_renderable(value)
        result = to_renderable(0)
        for entry in self._values:
            result = result + IfThenElse(to_renderable(cast(Operand, entry)) == target, 1, 0)
        return result

    def where(self, condition: Optional[Operand] = None, other: Optional[Operand] = None) -> List[Renderable]:
        """Element-wise `np.where`, matching numpy's two `where` forms.

        No arguments — the `np.where(lt)` / `np.nonzero(lt)` form: returns the
        *indices* of the table's own **nonzero** entries as a `List[Renderable]`, so it
        can be fed straight back into fancy indexing, e.g. `table[table.where()] = value`
        (equivalent to numpy's `A[np.where(A)] = value`). With constant entries this
        folds to a plain list of `Const` indices (one per nonzero entry, empty if all
        zero). With live `Renderable` entries each index is
        `IfThenElse(entry_i != 0, i, out_of_range)`, so a following write lands on
        position `i` exactly when `entry_i` is nonzero at runtime.

        With a condition — the `np.where(cond, x, y)` form: returns a list of
        `Renderable`s with the same length as the table. Entry `i` is
        `IfThenElse(condition, entry_i, other)` — i.e. the entry itself when `condition`
        is high, and `other` (defaulting to the table's `default`) otherwise.

        Both forms produce pure combinational expressions, safe to use inside any
        thread/condition context and to feed into `engine.set(...)`.

        Arguments:
            condition: 1-bit `int`/`bool` or `Renderable` selection condition. Omit it
                for the no-arg (nonzero-indices) form.
            other: Substitute value used where `condition` is low. Must be an
                `int`/`bool` or `Renderable` — not a `LookupTable`. Defaults to the
                table's `default`.

        Raises:
            TypeError: If the table contains `LookupTable` entries, if `other` is given
                without a `condition`, or if `other` is a `LookupTable`.
        """
        self._require_flat('where')

        # Value-selection form (numpy 3-arg `np.where(cond, x, y)`): a condition is
        # given, so select each entry or a substitute element-wise. `other` defaults
        # to the table's `default`.
        if condition is not None:
            if other is not None and isinstance(other, LookupTable):
                raise TypeError('other must be an int/bool or Renderable, not a LookupTable')
            cond = to_renderable(condition)
            sub = to_renderable(self._default if other is None else other)
            return [IfThenElse(cond, to_renderable(cast(Operand, value)), sub) for value in self._values]

        # No-argument form: indices of the nonzero entries (numpy 1-arg `np.where(lt)`).
        if other is not None:
            raise TypeError('where(other) requires a condition; call where(condition, other) or where()')
        out_of_range = Const(self.length, width=self.index_width + 1)
        results: List[Renderable] = []
        for i, value in enumerate(self._values):
            nonzero = to_renderable(cast(Operand, value)) != 0
            if nonzero.is_constant:
                if bool(cast(Const, nonzero).value):
                    results.append(Const(i, width=self.index_width))
            else:
                results.append(IfThenElse(nonzero, Const(i, width=self.index_width), out_of_range))
        return results

    def _slice(self, index: slice) -> 'LookupTable[T_Entry]':
        """Slice the table, returning a new `LookupTable`.

        Static bounds (`int`/`None`): a build-time slice with native Python semantics
        (stop exclusive, negative bounds wrap around). The result contains the selected
        raw entries and shares the table's `default`.

        Dynamic bounds (`Renderable` start and/or stop): the result keeps the full
        length of the table; entry `i` is `IfThenElse(start <= i < stop, value_i,
        default)`, so reading an index outside the dynamic window yields `default`.
        Nested `LookupTable` entries are not supported for dynamic bounds.
        """
        start, stop, step = index.start, index.stop, index.step
        if step is not None and step != 1:
            raise ValueError('LookupTable slicing does not support a step other than 1')

        def _is_dynamic(value: object) -> bool:
            return value is not None and not isinstance(value, (int, bool)) and hasattr(value, 'render')

        if _is_dynamic(start) or _is_dynamic(stop):
            self._require_flat('dynamic slicing')
            lo = 0 if start is None else to_renderable(start)
            hi = self.length if stop is None else to_renderable(stop)
            default = to_renderable(self._default)
            entries: List[Renderable] = [
                IfThenElse(to_renderable((lo <= i) & (i < hi)), to_renderable(cast(Operand, value)), default) for i, value in enumerate(self._values)
            ]
            return LookupTable(cast(Sequence[T_Entry], entries), default=self._default)

        s = 0 if start is None else start
        e = self.length if stop is None else stop
        if not isinstance(s, int) or isinstance(s, bool) or not isinstance(e, int) or isinstance(e, bool):
            raise TypeError(f'LookupTable slice bounds must be int or Renderable, got {type(s).__name__}/{type(e).__name__}')
        return LookupTable(self._values[s:e], default=self._default)

    @overload
    def __getitem__(self, index: int) -> T_Entry: ...
    @overload
    def __getitem__(self, index: slice) -> LookupTable[T_Entry]: ...
    @overload
    def __getitem__(self, index: Renderable) -> Renderable | LookupTable[Any]: ...
    def __getitem__(self, index: Union[Operand, slice]) -> T_Entry | LookupTable[T_Entry] | Renderable | LookupTable[Any]:
        """Dual-mode indexing.

        An `int`/`bool` index returns the raw element directly (native list semantics:
        negative indices wrap around, out-of-range raises `IndexError`) — a plain Python
        `int` for int entries, the `Renderable` itself for `Renderable` entries, or the
        nested `LookupTable` for table entries. A `slice` returns a new `LookupTable`
        (see `_slice` for the static/dynamic bound semantics). A `Renderable` index
        delegates to `read()` (hardware lookup).
        """
        if isinstance(index, slice):
            return self._slice(index)
        if isinstance(index, (int, bool)):
            return self._values[index]
        # Renderable (hardware) index.
        if any(isinstance(v, LookupTable) for v in self._values):
            # Nested table: select the row dynamically, returning a flat LookupTable
            # so that a second (column) index yields the full 2-D lookup lt[row][col].
            return self._select_row(index)
        return self.read(index)

    def _select_row(self, index: Operand) -> LookupTable[Any]:
        """Dynamically select a row of a nested table, returning a flat `LookupTable`.

        The result has one entry per column; entry `c` is the value at column `c` of the
        row selected by `index`, muxed across all rows via `IfThenElse`. Reading the
        result with a column index yields the full 2-D lookup `lt[row_idx][col_idx]`,
        so `lt[idx1][idx2]` with renderable `idx1`/`idx2` is a single combinational
        expression. Rows are assumed rectangular (same length); the width is the max.
        """
        rows = [cast('LookupTable[Any]', v) for v in self._values]
        ncols = max(r.length for r in rows)
        idx = to_renderable(index)
        entries: List[Renderable] = []
        for c in range(ncols):
            ret = to_renderable(self._default)
            for r, row in enumerate(rows):
                ret = IfThenElse(idx == r, row.read(c), ret)
            entries.append(ret)
        return LookupTable(entries, default=self._default)

    def _slice_indices(self, index: slice) -> List[int]:
        """Resolve a static `slice` to the list of affected indices.

        Uses native Python `range` semantics (negative bounds wrap, out-of-range
        bounds are clamped). Dynamic (`Renderable`) bounds are not supported here —
        use `update()` per address for dynamic selection.
        """
        start, stop, step = index.start, index.stop, index.step
        if step is not None and step != 1:
            raise ValueError('LookupTable __setitem__ slicing does not support a step other than 1')
        for b in (start, stop):
            if b is not None and not isinstance(b, (int, bool)) and hasattr(b, 'render'):
                raise TypeError('dynamic slice bounds are not supported in __setitem__; use update() per address')
        return list(range(self.length)[index])

    def _broadcast_values(self, value: Union[Operand, Sequence[Operand], 'LookupTable[Any]'], count: int) -> List[Operand]:
        """Normalize an assignment value to exactly `count` `Operand`s.

        A scalar (`int`/`bool`/`Renderable`) is broadcast to every position. A
        sequence or `LookupTable` is used element-wise and must have exactly
        `count` entries.
        """
        if isinstance(value, (list, tuple, LookupTable)):
            vals = list(value)
            if len(vals) != count:
                raise ValueError(f'value sequence length {len(vals)} does not match the number of selected indices {count}')
            return cast(List[Operand], vals)
        return [cast(Operand, value)] * count

    def __setitem__(
        self, index: Union[Operand, Sequence[Operand], 'LookupTable[Any]', slice], value: Union[Operand, Sequence[Operand], 'LookupTable[Any]']
    ) -> None:
        """Assign to one or more entries (numpy-style fancy indexing).

        Records hardware updates that `read()` applies, so any later read of a
        selected position yields the assigned value. Supported forms:

        - `table[i] = v` — single static index (`int`/`bool`). Out-of-range
          raises `IndexError` (matching `list`/`numpy`).
        - `table[i:j] = v` — static slice; `v` is broadcast to every position.
        - `table[[i, j, ...]] = v` — fancy indexing over a list/tuple/`LookupTable`
          of indices. `v` is a scalar (broadcast) or a sequence/`LookupTable` with
          one value per index.
        - `table[addr] = v` — a single `Renderable` `addr` is a dynamic address
          (the update is applied whenever `addr` selects it).

        Note: with duplicate indices the *first* listed index wins (the update
        chain is evaluated front-to-back), unlike numpy's last-wins behaviour.

        Arguments:
            index: Index or selection (see above).
            value: Scalar `Operand`, or a sequence/`LookupTable` of values for
                fancy indexing.

        Raises:
            IndexError: If a static `int` index is out of range.
            ValueError: If a value sequence length does not match the selection,
                or a slice uses a step other than 1.
            TypeError: If a dynamic slice bound is used.
        """
        if isinstance(index, (int, bool)):
            if not 0 <= index < self.length:
                raise IndexError(f'index {index} out of range for table of length {self.length}')
            self.update(index, self._broadcast_values(value, 1)[0], True)
            return
        if isinstance(index, slice):
            scalar = self._broadcast_values(value, 1)[0]
            for i in self._slice_indices(index):
                self.update(i, scalar, True)
            return
        if isinstance(index, (list, tuple, LookupTable)):
            indices = list(index)
            values = self._broadcast_values(value, len(indices))
            for i, v in zip(indices, values):
                if isinstance(i, (int, bool)) and not 0 <= i < self.length:
                    raise IndexError(f'index {i} out of range for table of length {self.length}')
                self.update(cast(Operand, i), v, True)
            return
        # A single Renderable is a dynamic address.
        self.update(cast(Operand, index), self._broadcast_values(value, 1)[0], True)

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

    @property
    def default(self) -> Operand:
        """The value returned for out-of-range indices."""
        return self._default
