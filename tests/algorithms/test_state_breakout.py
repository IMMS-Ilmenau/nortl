from typing import List

from nortl import Engine, Segment
from nortl.core.protocols import StateProto
from nortl.utils.test_wrapper import NoRTLTestBase


class TestSimple(NoRTLTestBase[Engine]):
    def init_sequence(self) -> Engine:
        self.breakout_states: List[StateProto] = []

        e = Engine('my_engine')
        e.sync()
        return e

    def dut(self, engine: Engine) -> None:
        engine.sync()
        for _ in range(5):
            engine.sync()
            self.breakout_states.append(engine.current_state)
        engine.sync()

    def the_testbench(self, engine: Engine) -> None:
        engine.sync()

    def callback_before_rendering(self, engine: Engine) -> Engine:
        engine.state_breakout(self.breakout_states)

        assert len(engine.workers) > 3

        return engine


class TestSimpleWithTiming(NoRTLTestBase[Engine]):
    def init_sequence(self) -> Engine:
        self.breakout_states: List[StateProto] = []

        e = Engine('my_engine')
        e.sync()
        self.tx = e.define_local('transfer', 4, 0)
        self.tx.access_checker.disable_check('identical_rw')

        return e

    def dut(self, engine: Engine) -> None:
        for _ in range(5):
            engine.sync()

        for i in range(10):
            engine.set(self.tx, i)
            engine.print('tx = %d', self.tx)
            engine.sync()
            self.breakout_states.append(engine.current_state)
        engine.sync()

    def the_testbench(self, engine: Engine) -> None:
        result = engine.define_scratch(1)
        engine.set(result, 1)

        engine.wait_for(self.tx == 1)

        for i in range(2, 10):
            engine.sync()
            engine.set(result, result & (i == self.tx))
            engine.print(f'i ={i}, rx = %d, result = %d', self.tx, result)

        self.assertTrue(result == 1)

    def callback_before_rendering(self, engine: Engine) -> Engine:
        engine.state_breakout(self.breakout_states)
        return engine


class TestComplexCase(NoRTLTestBase[Engine]):
    def init_sequence(self) -> Engine:
        self.breakout_states: List[StateProto] = []

        e = Engine('my_engine')
        e.sync()
        self.tx = e.define_local('transfer', 4, 0)
        self.tx.access_checker.disable_check('identical_rw')

        return e

    def dut(self, engine: Engine) -> None:
        for _ in range(5):
            engine.sync()

        for i in range(10):
            engine.set(self.tx, i)
            engine.print('tx = %d', self.tx)
            engine.sync()
            if i % 2 == 0:  # Complex case: breakout every second case!
                self.breakout_states.append(engine.current_state)
        engine.sync()

    def the_testbench(self, engine: Engine) -> None:
        result = engine.define_scratch(1)
        engine.set(result, 1)

        engine.wait_for(self.tx == 1)

        for i in range(2, 10):
            engine.sync()
            engine.set(result, result & (i == self.tx))
            engine.print(f'i ={i}, rx = %d, result = %d', self.tx, result)

        self.assertTrue(result == 1)

    def callback_before_rendering(self, engine: Engine) -> Engine:
        engine.state_breakout(self.breakout_states)
        return engine


@Segment
def the_test_segment(engine: Engine, n: int) -> None:
    for _ in range(n):
        engine.sync()


class TestSegmentBreakout(NoRTLTestBase[Engine]):
    def init_sequence(self) -> Engine:
        e = Engine('my_engine')
        e.sync()
        self.tx = e.define_local('transfer', 4, 0)
        self.tx.access_checker.disable_check('identical_rw')

        return e

    def dut(self, engine: Engine) -> None:
        for _ in range(5):
            engine.sync()

        for i in range(10):
            engine.set(self.tx, i)
            engine.print('tx = %d', self.tx)
            engine.sync()

        the_test_segment(engine, 5)

        engine.sync()

    def the_testbench(self, engine: Engine) -> None:
        result = engine.define_scratch(1)
        engine.set(result, 1)

        engine.wait_for(self.tx == 1)

        for i in range(2, 10):
            engine.sync()
            engine.set(result, result & (i == self.tx))
            engine.print(f'i ={i}, rx = %d, result = %d', self.tx, result)

        self.assertTrue(result == 1)

    def callback_before_rendering(self, engine: Engine) -> Engine:
        workername = ''

        assert len(Segment.get_engine_context(engine).segments) == 1
        for segment in Segment.get_engine_context(engine).segments:
            assert len(segment.rendered_segments) == 1
            for rendered_segment in segment.rendered_segments.values():
                assert len(rendered_segment.states) == 6  # 5 states + start and last state
                workername = rendered_segment.start_state.worker.name

        engine.breakout_segments(workername, 25)

        return engine


@Segment
def the_second_test_segment(engine: Engine, n: int) -> None:
    engine.sync()
    the_test_segment(engine, n)
    the_test_segment(engine, n)
    the_test_segment(engine, n)
    engine.sync()


@Segment
def the_third_test_segment(engine: Engine, n: int) -> None:
    engine.sync()
    the_second_test_segment(engine, n)
    engine.sync()


class TestAdjacentSegmentBreakout(NoRTLTestBase[Engine]):
    def init_sequence(self) -> Engine:
        e = Engine('my_engine')
        e.sync()
        self.tx = e.define_local('transfer', 4, 0)
        self.tx.access_checker.disable_check('identical_rw')

        return e

    def dut(self, engine: Engine) -> None:
        for _ in range(5):
            engine.sync()

        for i in range(10):
            engine.set(self.tx, i)
            engine.print('tx = %d', self.tx)
            engine.sync()

        the_third_test_segment(engine, 25)

        engine.sync()

    def the_testbench(self, engine: Engine) -> None:
        result = engine.define_scratch(1)
        engine.set(result, 1)

        engine.wait_for(self.tx == 1)

        for i in range(2, 10):
            engine.sync()
            engine.set(result, result & (i == self.tx))
            engine.print(f'i ={i}, rx = %d, result = %d', self.tx, result)

        self.assertTrue(result == 1)

    def callback_before_rendering(self, engine: Engine) -> Engine:
        workername = ''

        for segment in Segment.get_engine_context(engine).segments:
            for rendered_segment in segment.rendered_segments.values():
                workername = rendered_segment.start_state.worker.name

        engine.breakout_segments(workername, 30)

        assert len(engine.workers) > 4

        print(engine.workers)

        return engine
