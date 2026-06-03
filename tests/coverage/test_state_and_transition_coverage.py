from typing import List

from nortl import Engine
from nortl.utils.test_wrapper import NoRTLTestBase


class TestCoverageSimple(NoRTLTestBase[Engine]):
    def init_sequence(self) -> Engine:
        engine = Engine('my_engine')
        return engine

    def dut(self, engine: Engine) -> None:
        for i in range(10):
            engine.sync()

    def the_testbench(self, engine: Engine) -> None:
        for i in range(10):
            engine.sync()

    def callback_before_rendering(self, engine: Engine) -> Engine:
        engine.coverage.monitor_state_coverage()
        engine.coverage.monitor_transition_coverage()
        return engine

    def callback_after_execution(self, engine: Engine) -> None:
        engine.coverage.annotate(self.coverage_file)

        # Coverage statistics include all workers, so the total percentage is confusing for tests in the test wrapper
        assert engine.coverage.state_coverage.covered > 20
        assert engine.coverage.transition_coverage.covered > 20

        for workername, statelist in engine.states.items():
            if workername in ['WORKER_1', 'WORKER_2']:  # Only check in DUT and the_testbench
                for state in statelist:
                    assert state.get_metadata('State Coverage', False)

                    assert state.has_metadata('Transition Coverage')
                    for covered in state.get_metadata('Transition Coverage', {}).values():
                        assert covered


class TestCoverage(NoRTLTestBase[Engine]):
    def init_sequence(self) -> Engine:
        engine = Engine('my_engine')
        self.covered_states: List[str] = []
        self.uncovered_states: List[str] = []

        self.testsignal = engine.define_local('test', 1, 0)
        return engine

    def dut(self, engine: Engine) -> None:
        with engine.condition(self.testsignal == 0):
            for _ in range(10):
                engine.sync()
                self.covered_states.append(engine.current_state.name)
        with engine.else_condition():
            for _ in range(10):
                engine.sync()
                self.uncovered_states.append(engine.current_state.name)

    def the_testbench(self, engine: Engine) -> None:
        for i in range(10):
            engine.sync()

    def callback_before_rendering(self, engine: Engine) -> Engine:
        engine.coverage.monitor_state_coverage()
        engine.coverage.monitor_transition_coverage()
        return engine

    def callback_after_execution(self, engine: Engine) -> None:
        engine.coverage.annotate(self.coverage_file)

        # Coverage statistics include all workers, so the total percentage is confusing for tests in the test wrapper
        assert engine.coverage.state_coverage.covered > 10
        assert engine.coverage.transition_coverage.covered > 10

        for statelist in engine.states.values():
            for state in statelist:
                if state.name in self.covered_states:
                    assert state.get_metadata('State Coverage', False)
                if state.name in self.uncovered_states:
                    assert not state.get_metadata('State Coverage', False)
