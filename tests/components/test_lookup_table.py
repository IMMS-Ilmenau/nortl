# ruff: noqa: N801
from typing import cast

import pytest

from nortl.components import LookupTable
from nortl.core import CoreEngine, IfThenElse
from nortl.core.operations import Const
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
