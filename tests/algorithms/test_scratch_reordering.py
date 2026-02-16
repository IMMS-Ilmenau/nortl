from pathlib import Path
from typing import List

from nortl import Engine
from nortl.algorithms.scratch_reordering import index_overlap
from nortl.core.protocols import ScratchSignalProto
from nortl.renderer import ScratchpadVisualizationRenderer
from nortl.utils.test_wrapper import NoRTLTestBase


def verify_nonegative_indices(engine: Engine) -> None:
    # Verify no negative indices
    for s in engine.scratch_manager.scratch_signals:
        index = s.index
        if isinstance(index, int):
            assert index >= 0, f'Scratch signal {s.name} has negative index: {index}'
        else:
            assert index.start >= 0, f'Scratch signal {s.name} has negative start index: {index.start}'  # type:ignore
            assert index.stop >= 0, f'Scratch signal {s.name} has negative stop index: {index.stop}'  # type:ignore


def verify_scratch_pad_width(engine: Engine) -> None:
    # Verify no negative indices
    for s in engine.scratch_manager.scratch_signals:
        index = s.index
        if isinstance(index, int):
            assert index <= engine.scratch_manager.scratchpad_width, f'Scratch signal {s.name} has index {index} which is beyond scratch pad size'
        else:
            assert index.start <= engine.scratch_manager.scratchpad_width, (  # type:ignore
                f'Scratch signal {s.name} has start index {index.start} which is beyond scratch pad size'
            )
            assert index.stop <= engine.scratch_manager.scratchpad_width, (  # type:ignore
                f'Scratch signal {s.name} has stop index {index.stop} which is beyond scratch pad size'
            )


def test_simple_reordering() -> None:
    # Some whatever engine
    engine = Engine('my_engine')
    engine.tracer.upper_boundary = str(Path(__file__))

    _ = engine.define_input('IN')
    engine.sync()
    local_cnt = engine.define_scratch(4)
    engine.set(local_cnt, 1)
    dummy_before = engine.define_local('test', 2, 0)
    engine.set(dummy_before, local_cnt)

    with engine.fork('proc2') as proc2:
        with engine.fork('Proc1') as proc1:
            dummy = engine.define_scratch(2)
            engine.set(dummy, local_cnt)
            engine.sync()
            _ = engine.define_scratch(5)
            engine.set(local_cnt, 2)
            engine.sync()

        proc1.cancel()
        engine.set(local_cnt, 2)
        engine.set(dummy_before, local_cnt)

    proc2.cancel()
    dummy = engine.define_scratch(2)
    engine.set(dummy, local_cnt)
    engine.sync()

    verify_nonegative_indices(engine)
    verify_scratch_pad_width(engine)

    renderer = ScratchpadVisualizationRenderer(engine)

    with open((Path(__file__).parent / 'artifacts') / 'before_reorder.md', 'w') as file:
        file.write(renderer.render())

    engine.scratch_reordering()

    renderer = ScratchpadVisualizationRenderer(engine)

    with open((Path(__file__).parent / 'artifacts') / 'after_reorder.md', 'w') as file:
        file.write(renderer.render())


def test_simple_reordering_2() -> None:
    # Some whatever engine
    engine = Engine('my_engine')
    engine.tracer.upper_boundary = str(Path(__file__))

    _ = engine.define_input('IN')
    engine.sync()
    local_cnt = engine.define_scratch(4)
    engine.set(local_cnt, 1)
    dummy_before = engine.define_local('test', 2, 0)
    engine.set(dummy_before, local_cnt)

    with engine.fork('proc2') as proc2:
        local_cnt = engine.define_scratch(4)
        engine.sync()
        with engine.fork('Proc1'):
            dummy = engine.define_scratch(2)
            engine.set(dummy, local_cnt)
            engine.sync()
            _ = engine.define_scratch(5)
            engine.set(local_cnt, 2)
            engine.sync()

            with engine.condition(local_cnt == 2):
                _ = engine.define_scratch(16)
                engine.sync()

        engine.sync()

        _ = engine.define_scratch(1)

        engine.sync()

    with engine.fork('proc3'):
        test = engine.define_scratch(12)
        for _ in range(12):
            engine.sync()
        test.release()
        engine.sync()

    proc2.cancel()
    dummy = engine.define_scratch(2)
    engine.sync()

    engine.scratch_reordering()

    verify_nonegative_indices(engine)
    verify_scratch_pad_width(engine)


def test_for_overlap() -> None:
    engine = Engine('my_engine')

    engine.sync()
    s1 = engine.define_scratch(4)
    engine.sync()

    s2 = engine.define_scratch(8)
    engine.sync()

    engine.scratch_reordering()

    assert not index_overlap(s1, s2)


class TestScratchReoderingWithVerilog(NoRTLTestBase[Engine]):
    def init_sequence(self) -> Engine:
        e = Engine('my_engine')
        e.sync()
        self.scratch_lst: List[ScratchSignalProto] = []

        return e

    def dut(self, engine: Engine) -> None:
        s1 = engine.define_scratch(4)
        engine.set(s1, 1)
        self.scratch_lst.append(s1)
        engine.sync()

        s2 = engine.define_scratch(8)
        engine.set(s2, 2)
        self.scratch_lst.append(s2)

        print(s2.render())
        engine.sync()

    def callback_before_rendering(self, engine: Engine) -> Engine:
        engine.scratch_reordering()
        return engine

    def verify_final_state(self, engine: Engine) -> None:
        for i, scratch in enumerate(self.scratch_lst):
            engine.print(f'scratch_lst[{i}]=%d', scratch)
            self.assertEqual(scratch, i + 1)

        self.finish_simulation()
