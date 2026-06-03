import itertools

from nortl import Engine
from nortl.utils.test_wrapper import NoRTLTestBase


class TestCoveragePoint(NoRTLTestBase[Engine]):
    def init_sequence(self) -> Engine:
        engine = Engine('my_engine')
        return engine

    def dut(self, engine: Engine) -> None:
        test_signal = engine.define_scratch(1)
        engine.set(test_signal, 0)
        engine.sync()
        engine.coverage.coverpoint(test_signal == 1, 'Not-Covered CP')
        engine.sync()
        engine.coverage.coverpoint(test_signal == 0, 'Covered CP')
        engine.sync()

    def the_testbench(self, engine: Engine) -> None:
        for i in range(10):
            engine.sync()

    def callback_after_execution(self, engine: Engine) -> None:
        engine.coverage.annotate(self.coverage_file)

        # Coverage state of coverpoints can be looked up through a mapping on the coverage manager
        assert engine.coverage.coverpoints['Covered CP'].covered
        assert not engine.coverage.coverpoints['Not-Covered CP'].covered

        # Check statistics
        stats = engine.coverage.coverpoint_coverage
        assert stats.covered == 1
        assert stats.uncovered == 1

        # They are also available by walking all states
        found_cp1 = False
        found_cp2 = False
        for statelist in engine.states.values():
            for state in statelist:
                cp = state.get_metadata('Cover Points', {})
                if 'Not-Covered CP' in cp:
                    assert not cp['Not-Covered CP']
                    found_cp1 = True
                if 'Covered CP' in cp:
                    assert cp['Covered CP']
                    found_cp2 = True
        assert found_cp1
        assert found_cp2


class TestCrossCoverage(NoRTLTestBase[Engine]):
    def init_sequence(self) -> Engine:
        engine = Engine('my_engine')
        return engine

    def dut(self, engine: Engine) -> None:
        test_signal = engine.define_scratch(1)
        engine.set(test_signal, 0)
        engine.sync()
        with engine.for_loop(0, 5) as i:
            with engine.for_loop(0, 6) as j:
                engine.coverage.covergroup('My Coverage', [(i, 0, 9), (j, 0, 9)])
                engine.sync()
        engine.sync()

    def the_testbench(self, engine: Engine) -> None:
        for i in range(10):
            engine.sync()

    def callback_after_execution(self, engine: Engine) -> None:
        engine.coverage.annotate(self.coverage_file)

        # Extract coverage and check if it matches the expectation
        cg = engine.coverage.covergroups['My Coverage'].extract()
        for i, j in itertools.product(range(10), range(10)):
            if i < 5 and j < 6:
                assert cg[(i, j)]
            else:
                assert not cg[(i, j)]

        # Only 30 of 100 coverpoints in the group are covered
        stats = engine.coverage.covergroups['My Coverage'].coverage
        assert stats.covered == 30
        assert stats.total == 100

        # As there is only one coverpoint, the total statistics should be the same
        stats = engine.coverage.coverpoint_coverage
        assert stats.covered == 30
        assert stats.total == 100
