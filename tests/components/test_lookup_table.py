# ruff: noqa: N801
from typing import Any, cast

import pytest

from nortl.components import LookupTable
from nortl.core import CoreEngine, IfThenElse
from nortl.core.operations import Const
from nortl.core.protocols import Renderable
from nortl.utils.test_wrapper import NoRTLTestBase


class TestLookupTable_InRange(NoRTLTestBase[CoreEngine]):
    def init_sequence(self) -> CoreEngine:
        engine = CoreEngine('my_engine')
        self.table = LookupTable([10, 20, 30, 40])
        self.idx = engine.define_input('IDX', width=4)
        return engine

    def dut(self, engine: CoreEngine) -> None:
        pass

    def the_testbench(self, engine: CoreEngine) -> None:
        for i, expected in enumerate([10, 20, 30, 40]):
            engine.set(self.idx, i)
            engine.sync()
            self.assertEqual(self.table.read(self.idx), expected)


class TestLookupTable_OutOfRange(NoRTLTestBase[CoreEngine]):
    def init_sequence(self) -> CoreEngine:
        engine = CoreEngine('my_engine')
        self.table = LookupTable([10, 20, 30, 40], default=99)
        self.idx = engine.define_input('IDX', width=4)
        return engine

    def dut(self, engine: CoreEngine) -> None:
        pass

    def the_testbench(self, engine: CoreEngine) -> None:
        for idx_val in (4, 15):
            engine.set(self.idx, idx_val)
            engine.sync()
            self.assertEqual(self.table.read(self.idx), 99)


class TestLookupTable_RenderableEntries(NoRTLTestBase[CoreEngine]):
    def init_sequence(self) -> CoreEngine:
        engine = CoreEngine('my_engine')
        self.a = engine.define_input('A', width=8)
        self.b = engine.define_input('B', width=8)
        self.table = LookupTable([self.a, self.b, 5])
        self.idx = engine.define_input('IDX', width=4)
        return engine

    def dut(self, engine: CoreEngine) -> None:
        pass

    def the_testbench(self, engine: CoreEngine) -> None:
        engine.set(self.a, 11)
        engine.set(self.b, 22)
        engine.sync()
        for idx_val, expected in ((0, 11), (1, 22), (2, 5), (3, 0)):
            engine.set(self.idx, idx_val)
            engine.sync()
            self.assertEqual(self.table.read(self.idx), expected)


class TestLookupTable_NestingSim(NoRTLTestBase[CoreEngine]):
    def init_sequence(self) -> CoreEngine:
        engine = CoreEngine('my_engine')
        self.rows = LookupTable([LookupTable([1, 2]), LookupTable([3, 4])])
        self.row = engine.define_input('ROW', width=1)
        self.col = engine.define_input('COL', width=2)
        return engine

    def dut(self, engine: CoreEngine) -> None:
        pass

    def the_testbench(self, engine: CoreEngine) -> None:
        for row_val, col_val, expected in ((0, 1, 2), (1, 0, 3), (1, 1, 4)):
            engine.set(self.row, row_val)
            engine.set(self.col, col_val)
            engine.sync()
            value = IfThenElse(self.row == 0, self.rows[0].read(self.col), self.rows[1].read(self.col))
            self.assertEqual(value, expected)


class TestLookupTable_NestedChainedSet(NoRTLTestBase[CoreEngine]):
    """Chained build-time access x[0][1] on a nested LookupTable, fed to engine.set in the testbench."""

    def init_sequence(self) -> CoreEngine:
        engine = CoreEngine('my_engine')
        self.rows = LookupTable([LookupTable([1, 2]), LookupTable([3, 4])])
        self.out = engine.define_output('OUT', width=8, reset_value=0)
        return engine

    def dut(self, engine: CoreEngine) -> None:
        pass

    def the_testbench(self, engine: CoreEngine) -> None:
        # x[0][1] is a raw Python int (2) — chained getitem fed directly to engine.set
        engine.set(self.out, self.rows[0][1])
        engine.sync()
        self.assertEqual(self.out, 2)


class TestLookupTable_NestedDynamicSim(NoRTLTestBase[CoreEngine]):
    """Chained dynamic access rows[row_idx][col_idx] with renderable indices (2-D lookup)."""

    def init_sequence(self) -> CoreEngine:
        engine = CoreEngine('my_engine')
        self.rows = LookupTable([LookupTable([1, 2]), LookupTable([3, 4])])
        self.row = engine.define_input('ROW', width=1)
        self.col = engine.define_input('COL', width=2)
        return engine

    def dut(self, engine: CoreEngine) -> None:
        pass

    def the_testbench(self, engine: CoreEngine) -> None:
        # rows[row][col]: first getitem muxes the row, second reads the column.
        value = cast('Renderable', cast('LookupTable[Any]', self.rows[self.row])[self.col])
        for row_val, col_val, expected in ((0, 0, 1), (0, 1, 2), (1, 0, 3), (1, 1, 4)):
            engine.set(self.row, row_val)
            engine.set(self.col, col_val)
            engine.sync()
            self.assertEqual(value, expected)


class TestLookupTable_GetItemAndListProtocol:
    def test_raw_int_access(self) -> None:
        table = LookupTable([10, 20, 30, 40])
        assert table[0] == 10
        assert isinstance(table[0], int)
        assert not hasattr(table[0], 'render')

    def test_wrap_around(self) -> None:
        table = LookupTable([10, 20, 30, 40])
        assert table[-1] == 40
        assert table[-4] == 10

    def test_out_of_range_raises(self) -> None:
        table = LookupTable([10, 20, 30, 40])
        with pytest.raises(IndexError):
            _ = table[4]
        with pytest.raises(IndexError):
            _ = table[-5]

    def test_len_iter_length(self) -> None:
        table = LookupTable([10, 20, 30, 40])
        assert len(table) == 4
        assert list(table) == [10, 20, 30, 40]
        assert table.length == 4

    def test_read_returns_renderable(self) -> None:
        table = LookupTable([10, 20, 30, 40])
        result = table.read(0)
        assert hasattr(result, 'render')
        # All-int table with int index constant-folds to a Const
        assert result.is_constant
        assert cast(Const, result).value == 10


class TestLookupTable_RenderableEntriesBuildTime:
    def test_raw_element_access(self) -> None:
        engine = CoreEngine('my_engine')
        a = engine.define_input('A', width=8)
        b = engine.define_input('B', width=8)
        table = LookupTable([a, b, 5])
        assert table[0] is a
        assert table[-1] == 5
        assert isinstance(table[-1], int)


class TestLookupTable_SingleElement:
    def test_fold(self) -> None:
        table = LookupTable([7])
        assert cast(Const, table.read(0)).value == 7
        assert cast(Const, table.read(1)).value == 0  # default


class TestLookupTable_Empty:
    def test_fold_to_default(self) -> None:
        table: LookupTable[int] = LookupTable([], default=5)
        assert table.length == 0
        assert cast(Const, table.read(0)).value == 5
        assert cast(Const, table.read(100)).value == 5


class TestLookupTable_Validation:
    def test_bad_entry_raises(self) -> None:
        with pytest.raises(TypeError):
            LookupTable(['nope'])
        with pytest.raises(TypeError):
            LookupTable([1.5])

    def test_bad_default_raises(self) -> None:
        with pytest.raises(TypeError):
            LookupTable([1, 2], default='nope')  # type: ignore[arg-type]

    def test_lookup_table_default_raises(self) -> None:
        with pytest.raises(TypeError):
            LookupTable([1, 2], default=LookupTable([3, 4]))  # type: ignore[arg-type]

    def test_negative_read_raises(self) -> None:
        table = LookupTable([1, 2, 3])
        with pytest.raises(ValueError):
            table.read(-1)


class TestLookupTable_Nesting:
    def test_raw_row_access(self) -> None:
        rows = LookupTable([LookupTable([1, 2]), LookupTable([3, 4])])
        row0 = rows[0]
        assert isinstance(row0, LookupTable)
        assert row0[1] == 2
        row1 = rows[1]
        assert isinstance(row1, LookupTable)
        assert row1[-1] == 4

    def test_read_raises_on_nested(self) -> None:
        rows = LookupTable([LookupTable([1, 2]), LookupTable([3, 4])])
        with pytest.raises(TypeError):
            rows.read(0)
        with pytest.raises(TypeError):
            rows.read(Const(0))

    def test_value_width_none_for_tables(self) -> None:
        rows = LookupTable([LookupTable([1, 2]), LookupTable([3, 4])])
        assert rows.value_width is None

    def test_mixed_width_inference_skips_tables(self) -> None:
        table = LookupTable([LookupTable([1, 2]), 255])
        assert table.value_width == 8


class TestLookupTable_MinMaxBuildTime:
    def test_min_fold(self) -> None:
        table = LookupTable([10, 3, 7, 0])
        result = table.min()
        assert hasattr(result, 'render')
        assert result.is_constant
        assert cast(Const, result).value == 0

    def test_max_fold(self) -> None:
        table = LookupTable([10, 3, 7, 0])
        result = table.max()
        assert hasattr(result, 'render')
        assert result.is_constant
        assert cast(Const, result).value == 10

    def test_single_element(self) -> None:
        table = LookupTable([42])
        assert cast(Const, table.min()).value == 42
        assert cast(Const, table.max()).value == 42

    def test_empty_raises(self) -> None:
        table: LookupTable[int] = LookupTable([])
        with pytest.raises(ValueError):
            table.min()
        with pytest.raises(ValueError):
            table.max()

    def test_nested_raises(self) -> None:
        rows = LookupTable([LookupTable([1, 2]), LookupTable([3, 4])])
        with pytest.raises(TypeError):
            rows.min()
        with pytest.raises(TypeError):
            rows.max()


class TestLookupTable_SumBuildTime:
    def test_sum_fold(self) -> None:
        table = LookupTable([10, 3, 7, 0])
        result = table.sum()
        assert hasattr(result, 'render')
        assert result.is_constant
        assert cast(Const, result).value == 20

    def test_single_element(self) -> None:
        table = LookupTable([42])
        assert cast(Const, table.sum()).value == 42

    def test_empty_raises(self) -> None:
        table: LookupTable[int] = LookupTable([])
        with pytest.raises(ValueError):
            table.sum()

    def test_nested_raises(self) -> None:
        rows = LookupTable([LookupTable([1, 2]), LookupTable([3, 4])])
        with pytest.raises(TypeError):
            rows.sum()


class TestLookupTable_CountBuildTime:
    def test_count_fold(self) -> None:
        table = LookupTable([10, 3, 7, 3, 3])
        result = table.count(3)
        assert hasattr(result, 'render')
        assert result.is_constant
        assert cast(Const, result).value == 3

    def test_count_zero(self) -> None:
        table = LookupTable([10, 20, 30, 40])
        assert cast(Const, table.count(99)).value == 0

    def test_count_single_element(self) -> None:
        table = LookupTable([42])
        assert cast(Const, table.count(42)).value == 1
        assert cast(Const, table.count(1)).value == 0

    def test_count_empty(self) -> None:
        table: LookupTable[int] = LookupTable([])
        assert cast(Const, table.count(1)).value == 0

    def test_nested_raises(self) -> None:
        rows = LookupTable([LookupTable([1, 2]), LookupTable([3, 4])])
        with pytest.raises(TypeError):
            rows.count(1)


class TestLookupTable_WhereBuildTime:
    def test_where_no_arg_returns_nonzero_indices(self) -> None:
        # No-arg form is numpy's np.where(lt): indices of nonzero entries.
        table = LookupTable([0, 1, 0, 2, 0], default=0)
        results = table.where()
        assert len(results) == 2
        assert cast(Const, results[0]).value == 1
        assert cast(Const, results[1]).value == 3

    def test_where_no_arg_all_nonzero(self) -> None:
        table = LookupTable([1, 2, 3], default=0)
        results = table.where()
        assert [cast(Const, r).value for r in results] == [0, 1, 2]

    def test_where_no_arg_all_zero_returns_empty(self) -> None:
        table = LookupTable([0, 0, 0], default=0)
        assert table.where() == []

    def test_where_two_arg_value_selection(self) -> None:
        # Two-arg form is numpy's np.where(cond, x, y): element-wise values.
        table = LookupTable([10, 20, 30], default=0)
        results = table.where(False, other=99)
        for result in results:
            assert result.is_constant
            assert cast(Const, result).value == 99

    def test_where_two_arg_keeps_entries(self) -> None:
        table = LookupTable([10, 20, 30], default=0)
        results = table.where(True, other=99)
        for i, expected in enumerate((10, 20, 30)):
            assert cast(Const, results[i]).value == expected

    def test_where_condition_without_other_uses_default(self) -> None:
        # where(cond) is value-selection with the table's default as substitute.
        table = LookupTable([10, 20, 30], default=7)
        results = table.where(False)
        for result in results:
            assert cast(Const, result).value == 7

    def test_where_other_without_condition_raises(self) -> None:
        # `other` only makes sense together with a condition.
        table = LookupTable([1, 2, 3], default=0)
        with pytest.raises(TypeError):
            table.where(other=99)

    def test_nested_raises(self) -> None:
        rows = LookupTable([LookupTable([1, 2]), LookupTable([3, 4])])
        with pytest.raises(TypeError):
            rows.where()

    def test_lookup_table_other_raises(self) -> None:
        table = LookupTable([1, 2])
        with pytest.raises(TypeError):
            table.where(True, other=LookupTable([3, 4]))  # type: ignore[arg-type]


class TestLookupTable_SlicingBuildTime:
    def test_full_slice(self) -> None:
        table = LookupTable([10, 20, 30, 40])
        sliced = table[:]
        assert isinstance(sliced, LookupTable)
        assert list(sliced) == [10, 20, 30, 40]
        assert len(sliced) == 4

    def test_partial_slice(self) -> None:
        table = LookupTable([10, 20, 30, 40])
        sliced = table[1:3]
        assert isinstance(sliced, LookupTable)
        assert list(sliced) == [20, 30]
        assert len(sliced) == 2

    def test_open_bounds(self) -> None:
        table = LookupTable([10, 20, 30, 40])
        assert list(table[:2]) == [10, 20]
        assert list(table[2:]) == [30, 40]

    def test_negative_bounds(self) -> None:
        table = LookupTable([10, 20, 30, 40])
        assert list(table[-2:]) == [30, 40]
        assert list(table[:-2]) == [10, 20]

    def test_empty_slice(self) -> None:
        table = LookupTable([10, 20, 30])
        sliced = table[2:1]
        assert isinstance(sliced, LookupTable)
        assert len(sliced) == 0
        assert cast(Const, sliced.read(0)).value == 0  # falls through to default

    def test_read_of_sliced(self) -> None:
        table = LookupTable([10, 20, 30, 40])
        sliced = table[1:3]
        assert cast(Const, sliced.read(0)).value == 20
        assert cast(Const, sliced.read(1)).value == 30
        assert cast(Const, sliced.read(2)).value == 0  # out of range -> default

    def test_default_inherited(self) -> None:
        table = LookupTable([10, 20, 30, 40], default=99)
        sliced = table[1:3]
        assert cast(Const, sliced.read(5)).value == 99

    def test_step_not_supported(self) -> None:
        table = LookupTable([10, 20, 30, 40])
        with pytest.raises(ValueError):
            _ = table[::2]

    def test_nested_slice_returns_tables(self) -> None:
        rows = LookupTable([LookupTable([1, 2]), LookupTable([3, 4])])
        sliced = rows[0:1]
        assert isinstance(sliced, LookupTable)
        assert isinstance(sliced[0], LookupTable)
        assert sliced[0][1] == 2

    def test_dynamic_bounds_keep_full_length(self) -> None:
        table = LookupTable([10, 20, 30, 40, 50], default=99)
        sliced = table[slice(Const(1), Const(4))]
        assert isinstance(sliced, LookupTable)
        assert len(sliced) == 5
        assert sliced.default == 99

    def test_dynamic_bounds_fold(self) -> None:
        table = LookupTable([10, 20, 30, 40, 50], default=99)
        sliced = table[slice(Const(1), Const(4))]
        for idx_val, expected in ((0, 99), (1, 20), (2, 30), (3, 40), (4, 99)):
            result = sliced.read(idx_val)
            assert result.is_constant
            assert cast(Const, result).value == expected

    def test_dynamic_bounds_open_start(self) -> None:
        table = LookupTable([10, 20, 30, 40], default=99)
        sliced = table[slice(None, Const(2))]
        for idx_val, expected in ((0, 10), (1, 20), (2, 99), (3, 99)):
            assert cast(Const, sliced.read(idx_val)).value == expected

    def test_dynamic_bounds_open_stop(self) -> None:
        table = LookupTable([10, 20, 30, 40], default=99)
        sliced = table[slice(Const(2), None)]
        for idx_val, expected in ((0, 99), (1, 99), (2, 30), (3, 40)):
            assert cast(Const, sliced.read(idx_val)).value == expected

    def test_dynamic_bounds_empty_window(self) -> None:
        table = LookupTable([10, 20, 30], default=99)
        sliced = table[slice(Const(2), Const(2))]
        for idx_val in (0, 1, 2, 3):
            assert cast(Const, sliced.read(idx_val)).value == 99

    def test_dynamic_bounds_nested_raises(self) -> None:
        rows = LookupTable([LookupTable([1, 2]), LookupTable([3, 4])])
        with pytest.raises(TypeError):
            _ = rows[slice(Const(0), Const(1))]

    def test_dynamic_index_not_a_slice(self) -> None:
        # A Renderable index is still a hardware lookup, not a slice
        table = LookupTable([10, 20, 30, 40])
        result = table[Const(1)]
        assert hasattr(result, 'render')
        assert cast(Const, result).value == 20


class TestLookupTable_Update:
    def test_update_folded(self) -> None:
        table = LookupTable([10, 20, 30, 40])
        table.update(Const(1), 99, True)
        # Index 1 is replaced, others unchanged
        assert cast(Const, table.read(0)).value == 10
        assert cast(Const, table.read(1)).value == 99
        assert cast(Const, table.read(2)).value == 30
        assert cast(Const, table.read(3)).value == 40

    def test_update_out_of_range_keeps_default(self) -> None:
        table = LookupTable([10, 20], default=5)
        table.update(Const(7), 99, True)
        assert cast(Const, table.read(7)).value == 99
        assert cast(Const, table.read(3)).value == 5

    def test_multiple_updates(self) -> None:
        table = LookupTable([1, 2, 3, 4])
        table.update(Const(0), 100, True)
        table.update(Const(2), 300, True)
        assert cast(Const, table.read(0)).value == 100
        assert cast(Const, table.read(1)).value == 2
        assert cast(Const, table.read(2)).value == 300
        assert cast(Const, table.read(3)).value == 4

    def test_update_with_renderable_value(self) -> None:
        engine = CoreEngine('my_engine')
        a = engine.define_input('A', width=8)
        table = LookupTable([10, 20, 30, 40])
        table.update(Const(1), a, True)
        result = table.read(Const(1))
        assert hasattr(result, 'render')
        assert not result.is_constant  # live signal, cannot fold


class TestLookupTable_SetItem:
    def test_single_index(self) -> None:
        table = LookupTable([10, 20, 30, 40])
        table[1] = 99
        assert cast(Const, table.read(0)).value == 10
        assert cast(Const, table.read(1)).value == 99
        assert cast(Const, table.read(2)).value == 30
        assert cast(Const, table.read(3)).value == 40

    def test_single_index_out_of_range(self) -> None:
        table = LookupTable([10, 20, 30, 40])
        with pytest.raises(IndexError):
            table[4] = 99
        with pytest.raises(IndexError):
            table[-1] = 99

    def test_fancy_indexing_scalar_broadcast(self) -> None:
        table = LookupTable([10, 20, 30, 40])
        table[[1, 3]] = 5
        assert cast(Const, table.read(0)).value == 10
        assert cast(Const, table.read(1)).value == 5
        assert cast(Const, table.read(2)).value == 30
        assert cast(Const, table.read(3)).value == 5

    def test_fancy_indexing_value_sequence(self) -> None:
        table = LookupTable([10, 20, 30, 40])
        table[[0, 2]] = [100, 200]
        assert cast(Const, table.read(0)).value == 100
        assert cast(Const, table.read(1)).value == 20
        assert cast(Const, table.read(2)).value == 200
        assert cast(Const, table.read(3)).value == 40

    def test_fancy_indexing_from_lookup_table(self) -> None:
        table = LookupTable([10, 20, 30, 40])
        table[LookupTable([1, 2])] = 7
        assert cast(Const, table.read(1)).value == 7
        assert cast(Const, table.read(2)).value == 7

    def test_fancy_indexing_list_of_renderables_builds(self) -> None:
        engine = CoreEngine('my_engine')
        table = LookupTable([10, 20, 30, 40])
        # B is a list of Renderables (dynamic indices), like np.asarray of signals.
        b = [engine.define_input('B0', width=3), engine.define_input('B1', width=3)]
        table[b] = 5
        # Each dynamic index produces a live update; the read is not constant.
        result = table.read(Const(1))
        assert hasattr(result, 'render')
        assert not result.is_constant

    def test_setitem_from_where_nonzero(self) -> None:
        # No-arg where() returns indices of nonzero entries, so the write
        # scatters to exactly those positions (numpy's A[np.where(A)] = v idiom).
        table = LookupTable([0, 1, 0, 2, 0], default=0)
        table[table.where()] = 3
        assert [cast(Const, table.read(Const(i))).value for i in range(5)] == [0, 3, 0, 3, 0]

    def test_setitem_from_where_two_arg(self) -> None:
        # where(cond, other) returns `other` for every position, so all
        # writes collapse onto the single address `other`.
        table = LookupTable([0, 1, 2], default=0)
        table[table.where(False, 1)] = 3
        assert cast(Const, table.read(Const(1))).value == 3
        assert cast(Const, table.read(Const(0))).value == 0
        assert cast(Const, table.read(Const(2))).value == 2

    def test_fancy_indexing_length_mismatch(self) -> None:
        table = LookupTable([10, 20, 30, 40])
        with pytest.raises(ValueError):
            table[[0, 1]] = [100, 200, 300]

    def test_fancy_indexing_out_of_range(self) -> None:
        table = LookupTable([10, 20, 30, 40])
        with pytest.raises(IndexError):
            table[[0, 9]] = 5

    def test_slice_broadcast(self) -> None:
        table = LookupTable([10, 20, 30, 40])
        table[1:3] = 55
        assert cast(Const, table.read(0)).value == 10
        assert cast(Const, table.read(1)).value == 55
        assert cast(Const, table.read(2)).value == 55
        assert cast(Const, table.read(3)).value == 40

    def test_dynamic_address(self) -> None:
        engine = CoreEngine('my_engine')
        addr = engine.define_input('ADDR', width=3)
        table = LookupTable([10, 20, 30, 40])
        table[addr] = 99
        # A dynamic address update is applied whenever addr selects it.
        result = table.read(addr)
        assert hasattr(result, 'render')
        assert not result.is_constant


class TestLookupTable_SetItemDynamicListSim(NoRTLTestBase[CoreEngine]):
    def init_sequence(self) -> CoreEngine:
        engine = CoreEngine('my_engine')
        self.b0 = engine.define_input('B0', width=3)
        self.b1 = engine.define_input('B1', width=3)
        self.table = LookupTable([10, 20, 30, 40])
        # B is a list of Renderables (dynamic indices), like np.asarray of signals.
        self.table[[self.b0, self.b1]] = 5
        return engine

    def dut(self, engine: CoreEngine) -> None:
        pass

    def the_testbench(self, engine: CoreEngine) -> None:
        # Each dynamic index, when it selects a position, writes 5 there.
        for b0_val, b1_val in ((1, 3), (0, 2), (1, 1)):
            engine.set(self.b0, b0_val)
            engine.set(self.b1, b1_val)
            engine.sync()
            expected = [10, 20, 30, 40]
            for pos in (b0_val, b1_val):
                expected[pos] = 5
            for i, exp in enumerate(expected):
                self.assertEqual(self.table.read(Const(i)), exp)


class TestLookupTable_WhereLiveScatterSim(NoRTLTestBase[CoreEngine]):
    def init_sequence(self) -> CoreEngine:
        engine = CoreEngine('my_engine')
        # Live entries: where() returns indices of the nonzero entries at runtime.
        self.entries = [engine.define_input(f'E{i}', width=4) for i in range(5)]
        self.table = LookupTable(self.entries, default=0)
        # numpy idiom: A[np.where(A)] = 5  (scatter to the nonzero positions)
        self.table[self.table.where()] = 5
        return engine

    def dut(self, engine: CoreEngine) -> None:
        pass

    def the_testbench(self, engine: CoreEngine) -> None:
        # A position becomes 5 exactly when its entry is nonzero at runtime.
        for pattern in ((1, 0, 1, 0, 1), (0, 0, 0, 0, 0), (2, 0, 0, 3, 0), (1, 1, 1, 1, 1)):
            for i, val in enumerate(pattern):
                engine.set(self.entries[i], val)
            engine.sync()
            for i, val in enumerate(pattern):
                self.assertEqual(self.table.read(Const(i)), 5 if val != 0 else 0)


class TestLookupTable_MinMaxSim(NoRTLTestBase[CoreEngine]):
    def init_sequence(self) -> CoreEngine:
        engine = CoreEngine('my_engine')
        self.a = engine.define_input('A', width=8)
        self.b = engine.define_input('B', width=8)
        self.table = LookupTable([self.a, self.b, 5])
        self.idx = engine.define_input('IDX', width=4)
        return engine

    def dut(self, engine: CoreEngine) -> None:
        pass

    def the_testbench(self, engine: CoreEngine) -> None:
        engine.set(self.a, 11)
        engine.set(self.b, 22)
        engine.sync()
        self.assertEqual(self.table.min(), 5)
        self.assertEqual(self.table.max(), 22)
        engine.set(self.a, 33)
        engine.sync()
        self.assertEqual(self.table.min(), 5)
        self.assertEqual(self.table.max(), 33)


class TestLookupTable_SumSim(NoRTLTestBase[CoreEngine]):
    def init_sequence(self) -> CoreEngine:
        engine = CoreEngine('my_engine')
        self.a = engine.define_input('A', width=8)
        self.b = engine.define_input('B', width=8)
        self.table = LookupTable([self.a, self.b, 5])
        return engine

    def dut(self, engine: CoreEngine) -> None:
        pass

    def the_testbench(self, engine: CoreEngine) -> None:
        for a_val, b_val in ((11, 22), (33, 4), (200, 255)):
            engine.set(self.a, a_val)
            engine.set(self.b, b_val)
            engine.sync()
            self.assertEqual(self.table.sum(), a_val + b_val + 5)


class TestLookupTable_CountSim(NoRTLTestBase[CoreEngine]):
    def init_sequence(self) -> CoreEngine:
        engine = CoreEngine('my_engine')
        self.a = engine.define_input('A', width=8)
        self.b = engine.define_input('B', width=8)
        self.table = LookupTable([self.a, self.b, 5])
        return engine

    def dut(self, engine: CoreEngine) -> None:
        pass

    def the_testbench(self, engine: CoreEngine) -> None:
        for a_val, b_val in ((11, 22), (33, 4), (200, 255), (5, 5), (5, 7)):
            engine.set(self.a, a_val)
            engine.set(self.b, b_val)
            engine.sync()
            expected = [a_val, b_val, 5].count(a_val)
            self.assertEqual(self.table.count(a_val), expected)
            self.assertEqual(self.table.count(99), 0)


class TestLookupTable_WhereSim(NoRTLTestBase[CoreEngine]):
    def init_sequence(self) -> CoreEngine:
        engine = CoreEngine('my_engine')
        self.a = engine.define_input('A', width=8)
        self.b = engine.define_input('B', width=8)
        self.table = LookupTable([self.a, self.b, 5], default=99)
        self.cond = engine.define_input('COND', width=1)
        return engine

    def dut(self, engine: CoreEngine) -> None:
        pass

    def the_testbench(self, engine: CoreEngine) -> None:
        engine.set(self.a, 11)
        engine.set(self.b, 22)
        engine.sync()
        # cond high -> entries
        engine.set(self.cond, 1)
        engine.sync()
        results = self.table.where(self.cond, other=0)
        self.assertEqual(results[0], 11)
        self.assertEqual(results[1], 22)
        self.assertEqual(results[2], 5)
        # cond low -> substitute
        engine.set(self.cond, 0)
        engine.sync()
        results = self.table.where(self.cond, other=0)
        self.assertEqual(results[0], 0)
        self.assertEqual(results[1], 0)
        self.assertEqual(results[2], 0)


class TestLookupTable_SlicingSim(NoRTLTestBase[CoreEngine]):
    def init_sequence(self) -> CoreEngine:
        engine = CoreEngine('my_engine')
        self.table = LookupTable([10, 20, 30, 40, 50], default=99)
        self.idx = engine.define_input('IDX', width=4)
        self.start = engine.define_input('START', width=4)
        self.stop = engine.define_input('STOP', width=4)
        return engine

    def dut(self, engine: CoreEngine) -> None:
        pass

    def the_testbench(self, engine: CoreEngine) -> None:
        # Static slice: [1:4] -> [20, 30, 40]
        static = self.table[1:4]
        assert isinstance(static, LookupTable)
        engine.set(self.idx, 0)
        engine.sync()
        self.assertEqual(static.read(self.idx), 20)
        engine.set(self.idx, 2)
        engine.sync()
        self.assertEqual(static.read(self.idx), 40)
        engine.set(self.idx, 3)
        engine.sync()
        self.assertEqual(static.read(self.idx), 99)  # out of range -> default

        # Dynamic slice: start <= i < stop (Renderable bounds are not part of Python's slice type)
        dynamic = self.table[slice(self.start, self.stop)]
        assert isinstance(dynamic, LookupTable)
        assert len(dynamic) == 5
        for start_val, stop_val, idx_val, expected in (
            (1, 4, 0, 99),  # below window
            (1, 4, 1, 20),  # window start
            (1, 4, 3, 40),  # window end - 1
            (1, 4, 4, 99),  # at stop (exclusive)
            (2, 5, 4, 50),  # top of table
            (0, 5, 2, 30),  # full window
        ):
            engine.set(self.start, start_val)
            engine.set(self.stop, stop_val)
            engine.set(self.idx, idx_val)
            engine.sync()
            self.assertEqual(dynamic.read(self.idx), expected)


class TestLookupTable_UpdateSim(NoRTLTestBase[CoreEngine]):
    def init_sequence(self) -> CoreEngine:
        engine = CoreEngine('my_engine')
        self.table = LookupTable([10, 20, 30, 40], default=0)
        self.addr = engine.define_input('ADDR', width=4)
        self.data = engine.define_input('DATA', width=8)
        self.en = engine.define_input('EN', width=1)
        self.table.update(self.addr, self.data, self.en)
        self.idx = engine.define_input('IDX', width=4)
        return engine

    def dut(self, engine: CoreEngine) -> None:
        pass

    def the_testbench(self, engine: CoreEngine) -> None:
        # cond low -> original table
        engine.set(self.en, 0)
        engine.set(self.addr, 1)
        engine.set(self.data, 99)
        engine.sync()
        for idx_val, expected in ((0, 10), (1, 20), (2, 30), (3, 40)):
            engine.set(self.idx, idx_val)
            engine.sync()
            self.assertEqual(self.table.read(self.idx), expected)

        # cond high -> updated entry at addr
        engine.set(self.en, 1)
        engine.set(self.addr, 1)
        engine.set(self.data, 99)
        engine.sync()
        for idx_val, expected in ((0, 10), (1, 99), (2, 30), (3, 40)):
            engine.set(self.idx, idx_val)
            engine.sync()
            self.assertEqual(self.table.read(self.idx), expected)

        # moving the address
        engine.set(self.addr, 3)
        engine.set(self.data, 77)
        engine.sync()
        for idx_val, expected in ((1, 20), (3, 77)):
            engine.set(self.idx, idx_val)
            engine.sync()
            self.assertEqual(self.table.read(self.idx), expected)


class TestLookupTable_DynamicSliceLocalSignalsSim(NoRTLTestBase[CoreEngine]):
    """Dynamic slicing with `define_local` bounds and a `define_scratch` result.

    The bounds are live local signals (not inputs, not constants), so the `IfThenElse`
    window logic inside the sliced `LookupTable` cannot constant-fold and is verified
    as real combinational hardware in simulation.
    """

    def init_sequence(self) -> CoreEngine:
        engine = CoreEngine('my_engine')
        self.table = LookupTable([10, 20, 30, 40, 50], default=99)
        self.start = engine.define_local('SLICE_START', width=4, reset_value=0)
        self.stop = engine.define_local('SLICE_STOP', width=4, reset_value=0)
        self.idx = engine.define_local('SLICE_IDX', width=4, reset_value=0)
        # Build the dynamic slice once; bounds are live signals
        self.dynamic = self.table[slice(self.start, self.stop)]
        assert isinstance(self.dynamic, LookupTable)
        self.result = engine.define_scratch(8)
        return engine

    def dut(self, engine: CoreEngine) -> None:
        pass

    def the_testbench(self, engine: CoreEngine) -> None:
        # The IfThenElse chain must NOT have folded: entries are live expressions
        assert not self.dynamic[0].is_constant  # type: ignore[attr-defined]

        test_cases = (
            (0, 5, 0, 10),  # full window, first entry
            (0, 5, 4, 50),  # full window, last entry
            (1, 4, 0, 99),  # below window -> default
            (1, 4, 1, 20),  # window start (inclusive)
            (1, 4, 3, 40),  # window end - 1 (stop exclusive)
            (1, 4, 4, 99),  # at stop -> default
            (2, 5, 4, 50),  # top of table inside window
            (2, 5, 1, 99),  # below window -> default
            (3, 3, 2, 99),  # empty window (start == stop)
            (0, 1, 0, 10),  # single-entry window
            (0, 1, 1, 99),  # just outside single-entry window
        )
        for start_val, stop_val, idx_val, expected in test_cases:
            engine.set(self.start, start_val)
            engine.set(self.stop, stop_val)
            engine.set(self.idx, idx_val)
            engine.sync()
            engine.set(self.result, self.dynamic.read(self.idx))
            engine.sync()
            self.assertEqual(self.result, expected)
