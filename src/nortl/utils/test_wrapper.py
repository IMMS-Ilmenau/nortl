import re
import subprocess
from abc import ABC, abstractmethod
from inspect import currentframe, getframeinfo
from pathlib import Path
from tempfile import TemporaryDirectory
from types import FrameType

import pytest

from nortl.core import CoreEngine
from nortl.core.constructs import Condition, ElseCondition, Fork
from nortl.core.modifiers import UnregisteredRead
from nortl.core.operations import to_renderable
from nortl.core.protocols import Renderable
from nortl.renderer.verilog_renderer import VerilogRenderer


class NoRTLTestBase(ABC):
    """Base class for noRTL tests with Verilog simulation.

    Subclasses must implement:
        - build_engine(): Create and configure the engine to be tested
        - generate_testbench(): Generate the Verilog testbench file

    The simulation is automatically run before each test method.
    Test methods can access:
        - self.engine: The engine instance
        - self.simulation_result: The subprocess result from simulation
        - self.simulation_output: Parsed simulation output (string)
    """

    @abstractmethod
    def init_sequence(self) -> CoreEngine:
        """This function must initialize the engine that is to be tested. In the most trivial case, this means, that an instance of CoreEngine is created.

        Returns:
            CoreEngine: Initialized engine
        """
        pass

    def verify_final_state(self, engine: CoreEngine) -> None:
        """This state-sequence is called after the dut and testbench threads have ended. It can be used to verify the final state of the dut."""
        pass

    def the_testbench(self, engine: CoreEngine) -> None:
        """The state sequence that is run in parallel to the engine-under-Test. This may use the self.assert* functions to verify the behavior.

        Arguments:
            engine (CoreEngine): engine instance
        """
        pass

    @abstractmethod
    def dut(self, engine: CoreEngine) -> None:
        """The dut function is the state sequence that is to be tested. It is executed in parallel to the testbench.

        A call to self.assert* is not forbidden but not advised to create a good seperation between dut and test code.
        """
        pass

    def get_test_engine(self) -> CoreEngine:
        self.engine = self.init_sequence()

        self.finish_flag = self.engine.define_output('finish', 1, 0)
        self.state_flag = self.engine.define_output('passed', 1, 0)
        self.error_ctr = self.engine.define_local('error_ctr', 16, 0)
        self.timeout = self.engine.define_output('timeout', 1, 0)
        ctr = self.engine.define_local('timeout_ctr', 16, 0)

        self.engine.sync()

        # FIXME: Introduce Timeout-timer
        with Fork(self.engine, 'DUT') as t_dut:
            self.dut(self.engine)
        with Fork(self.engine, 'testbench') as t_tb:
            self.the_testbench(self.engine)
        with Fork(self.engine, 'timeout') as t_timeout:
            self.engine.sync()
            self.engine.set(ctr, ctr + 1)
            with Condition(self.engine, ctr == 0xFFFF):
                self.engine.set(self.timeout, 1)
                t_timeout.finish()

        self.engine.sync()

        self.engine.wait_for((t_dut.finished & t_tb.finished) | t_timeout.finished)

        with Condition(self.engine, t_timeout.finished):
            t_dut.cancel()
            t_tb.cancel()
            if not hasattr(self, 'expect_timeout'):
                self.assertTrue(0)  # Show that we had a timeout
            else:
                self.assertTrue(self.expect_timeout)
        with ElseCondition(self.engine):
            t_timeout.cancel()

        self.verify_final_state(self.engine)

        self.engine.sync()

        self.finish_simulation()

        return self.engine

    def increment_error_ctr(self) -> None:
        self.engine.sync()

        with Condition(self.engine, self.error_ctr != 0xFFFF):
            self.engine.set(self.error_ctr, self.error_ctr + 1)
        with ElseCondition(self.engine):
            pass

        self.engine.sync()

    def finish_simulation(self) -> None:
        self.engine.sync()

        with Condition(self.engine, self.error_ctr == 0):
            self.engine.set(self.state_flag, 1)
        with ElseCondition(self.engine):
            self.engine.set(self.state_flag, 0)

        self.engine.set(self.finish_flag, 1)
        self.engine.sync()

    def print_line(self, frame: FrameType) -> None:
        fi = getframeinfo(frame)
        if fi.code_context is None:
            return
        code_context = fi.code_context[0]
        code_context = re.sub('#.*', '', code_context)
        code_context = code_context.lstrip().rstrip()
        self.engine.print(f'Assertion \\"{code_context}\\" failed at {fi.filename}:{frame.f_lineno}')

    def assertTrue(self, condition: Renderable | int) -> None:  # noqa: N802
        with Condition(self.engine, UnregisteredRead(~to_renderable(condition))):
            frame = currentframe()
            if frame is not None:
                frame = frame.f_back
                if frame is not None:
                    self.print_line(frame)
            self.increment_error_ctr()
            self.finish_simulation()
        with ElseCondition(self.engine):
            pass
        self.engine.sync()

    def assertEqual(self, value1: Renderable | int, value2: Renderable | int) -> None:  # noqa: N802
        with Condition(self.engine, UnregisteredRead(to_renderable(value1) != to_renderable(value2))):
            frame = currentframe()
            if frame is not None:
                frame = frame.f_back
                if frame is not None:
                    self.print_line(frame)

            self.engine.print('Left-hand side: 0x%h', to_renderable(value1))
            self.engine.print('Right-hand side: 0x%h', to_renderable(value2))
            self.increment_error_ctr()
            self.finish_simulation()
        with ElseCondition(self.engine):
            pass
        self.engine.sync()

    def test_compile_and_run(self) -> None:
        """Automatically executed fixture.

        Process:
        1. Builds the engine
        2. Generates and compiles Verilog
        3. Runs the simulation
        4. Makes results available to test methods

        """
        # Create engine from derived class
        self.engine = self.get_test_engine()

        with TemporaryDirectory() as tempdir_str:
            tmp_path = Path(tempdir_str)

            # Generate Verilog files
            self.verilog_file: Path = tmp_path / 'engine.sv'
            self.testbench_file: Path = Path(__file__).parent / 'templates' / 'testbench.sv'

            renderer = VerilogRenderer(self.engine)
            with open(self.verilog_file, 'w') as fptr:
                fptr.write(renderer.render())

            # Compile with Icarus Verilog
            self.compiled_file: Path = tmp_path / 'engine.vvp'
            compile_result = subprocess.run(
                ['iverilog', '-g2005-sv', '-o', str(self.compiled_file), str(self.verilog_file), str(self.testbench_file)],
                capture_output=True,
                text=True,
            )

            if compile_result.returncode != 0:
                pytest.fail(f'Verilog compilation failed:\n{compile_result.stderr}')

            # Run simulation automatically
            self._run_simulation()
            self.simulation_output: str = self.simulation_result.stdout

            res = re.findall(r'passed=\s*\d+', self.simulation_output)[0]
            print(self.simulation_output)

            pass_state = int(res.split('=')[1]) == 1
            print(pass_state)

            if not pass_state:
                pytest.fail('Verilog simulation discovered errors')

    def _run_simulation(self) -> None:
        """Internal method to execute the simulation."""
        cmd = ['vvp', str(self.compiled_file)]

        self.simulation_result = subprocess.run(cmd, capture_output=True, text=True)
