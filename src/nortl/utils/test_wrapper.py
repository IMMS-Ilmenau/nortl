import re
import subprocess
from abc import ABC, abstractmethod
from inspect import currentframe, getframeinfo
from pathlib import Path
from tempfile import TemporaryDirectory
from types import FrameType
from typing import Union

import pytest

from nortl.core import IfThenElse, Volatile
from nortl.core.constructs import Condition, ElseCondition, Fork
from nortl.core.modifiers import UnregisteredRead
from nortl.core.operations import Var, to_renderable
from nortl.core.protocols import EngineProto, Renderable
from nortl.renderer.verilog_renderer import VerilogRenderer
from nortl.renderer.verilog_utils.print_handlers import CoverageWriter
from nortl.verilog_library import HDL_MODULES, SIM_MODULES

__all__ = [
    'NoRTLTestBase',
]


class NoRTLTestBase[T: EngineProto](ABC):
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
    def init_sequence(self) -> T:
        """Initializes the engine that is to be tested.

        Its intention is to create and configure an instance of the Engine that will be tested.

        Example:
        ```python
        class MyTest(NoRTLTestBase):
            def init_sequence(self) -> T:
                engine = Engine("my_test_engine")
                output = engine.define_output("result", width=8)
                return engine
        ```

        Returns:
            Engine: Initialized engine
        """
        pass

    def verify_final_state(self, engine: T) -> None:
        """Verifies the final state of the engine after simulation.

        This state-sequence is called after the dut and testbench threads have ended.
        It can be used to verify the final state of the dut.

        Arguments:
            engine (EngineProto): The engine instance to verify
        """
        pass

    def the_testbench(self, engine: T) -> None:
        """The state sequence that is run in parallel to the engine-under-Test.

        This may use the self.assert* functions to verify the behavior.

        Arguments:
            engine (T): engine instance
        """
        pass

    @abstractmethod
    def dut(self, engine: T) -> None:
        """The dut function is the state sequence that is to be tested.

        It is executed in parallel to the testbench. A call to self.assert* is not forbidden
        but not advised to create a good separation between dut and test code.

        Arguments:
            engine (T): The engine instance
        """
        pass

    def callback_before_rendering(self, engine: T) -> T:
        return engine

    def callback_after_execution(self, engine: T) -> None:
        pass

    def get_test_engine(self) -> T:
        self.engine = self.init_sequence()

        self.finish_flag = self.engine.define_output('finish', 1, 0)
        self.state_flag = self.engine.define_output('passed', 1, 0)
        self.error_ctr = self.engine.define_local('error_ctr', 16, 0)
        self.timeout = self.engine.define_output('timeout', 1, 0)
        ctr = self.engine.define_local('timeout_ctr', 16, 0)
        self._reset_timeout = Volatile(self.engine.define_local('reset_timeout', 1, 0))

        # The test threads should be able to write on inputs. This is why we convert them to local signals
        # FIXME check if this can be replaced with a cleaner solution
        for signal in self.engine.signals.values():
            if signal.type == 'input':
                signal._type = 'local'  # type: ignore[attr-defined]

        self.engine.sync()

        with Fork(self.engine, 'DUT') as t_dut:
            self.dut(self.engine)
        with Fork(self.engine, 'testbench') as t_tb:
            self.the_testbench(self.engine)
        with Fork(self.engine, 'timeout') as t_timeout:
            self.engine.sync()
            self.engine.set(ctr, IfThenElse(self._reset_timeout, 0, ctr + 1))
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
        """Finalizes the simulation by setting flags.

        This method sets the state and finish flags based on the error counter.
        If no errors occurred, the state flag is set to 1 (passed), otherwise 0 (failed).
        """
        self.engine.sync()

        with Condition(self.engine, self.error_ctr == 0):
            self.engine.set(self.state_flag, 1)
        with ElseCondition(self.engine):
            self.engine.set(self.state_flag, 0)

        self.engine.set(self.finish_flag, 1)
        self.engine.sync()

    def print_line(self, frame: FrameType) -> None:
        """Prints an assertion failure message with context.

        Extracts the source code line where the assertion failed and prints it
        along with the file and line number.

        Arguments:
            frame (FrameType): The frame object containing the code context
        """
        fi = getframeinfo(frame)
        if fi.code_context is None:
            return
        code_context = fi.code_context[0]
        code_context = re.sub('#.*', '', code_context)
        code_context = code_context.lstrip().rstrip()
        self.engine.print(f'Assertion \\"{code_context}\\" failed at {fi.filename}:{frame.f_lineno}', level='error')

    def reset_timeout(self) -> None:
        self.engine.set(self._reset_timeout, 1)
        self.engine.sync()
        self.engine.set(self._reset_timeout, 0)
        self.engine.sync()

    def assertTrue(self, condition: Renderable | int) -> None:  # noqa: N802
        """Asserts that a condition is true.

        If the condition is false, prints the assertion line and fails the simulation.

        Example:
        ```python
        self.assertTrue(output_signal == 5)
        ```

        Arguments:
            condition (Renderable | int): The condition to assert as true
        """
        if isinstance(condition, int):
            # Condition must be a Var, to bypass the constant-value check for the conditional transition.
            condition = Var(condition, 1)

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
        """Asserts that two values are equal.

        If the values are not equal, prints both values from within the simulation and fails the simulation.

        Example:
        ```python
        self.assertEqual(output_signal, expected_value)
        ```

        Arguments:
            value1 (Renderable | int): The first value to compare
            value2 (Renderable | int): The second value to compare
        """
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
        """Automatically executed test method.

        This method runs before each test and performs the following steps:

        1. Builds the engine by calling init_sequence()
        2. Generates and compiles Verilog files
        3. Runs the simulation
        4. Makes results available to test methods

        The method raises pytest.fail if the simulation fails.
        """
        # Create engine from derived class and force name to match instantiation in testbench
        self.engine = self.callback_before_rendering(self.get_test_engine())

        if self.engine.module_name != 'my_engine':
            raise RuntimeError("Engine for test wrapper must be named 'my_engine'!")

        with TemporaryDirectory() as tempdir_str:
            tmp_path = Path(tempdir_str)

            # Render engine
            self.verilog_file = self.render(tmp_path, self.engine)

            # Collect other source files
            hdl_lib_files = [str(module.filepath) for module in HDL_MODULES.values()]
            sim_lib_files = [str(module.filepath) for module in SIM_MODULES.values()]

            # Add additional custom modules
            for module_name, module in self.engine.modules.items():
                if module_name not in HDL_MODULES:
                    module_path = tmp_path / f'{module_name}.sv'
                    module_path.write_text(module.hdl_code)
                    hdl_lib_files.append(str(module_path))

            # Compile and run simulation
            self.compiled_file = self.compile(tmp_path, self.verilog_file, *hdl_lib_files, *sim_lib_files)
            self.simulation_result = self.run(self.compiled_file)

            self.simulation_output: str = self.simulation_result.stdout

            res = re.findall(r'passed=\s*\d+', self.simulation_output)[0]
            print(self.simulation_output)

            pass_state = int(res.split('=')[1]) == 1
            print(pass_state)

            if not pass_state:
                pytest.fail('Verilog simulation discovered errors')

            # Save path to coverage file
            self.coverage_file = tmp_path / (self.engine.module_name + '.coverage.jsonl')

            self.callback_after_execution(self.engine)

    def render(self, working_dir: Path, engine: T) -> Path:
        """Render engine."""
        verilog_file: Path = working_dir / (engine.module_name + '.sv')

        # Switch coverage writer to raw mode
        # Icarus Verilog does not support normal mode
        CoverageWriter.RAW_MODE = True

        renderer = VerilogRenderer(engine, include_modules=False, synthesis_guard=None)

        with open(verilog_file, 'w') as fptr:
            fptr.write(renderer.render())
        return verilog_file

    def create_command_file(self, working_dir: Path, *source_files: Union[Path, str]) -> str:
        """Create command file for Icarus Verilog."""
        testbench_file: Path = Path(__file__).parent / 'templates' / 'testbench.sv'

        # NOTE: the command file is required, because Icarus doesn't like the string defines on the command line

        lines = [
            '+define+NORTL_INTEGRATED_TEST',
            '+define+NORTL_RAW_MODE',
            '+define+NORTL_COV' if self.engine.coverage.enabled else '',
            f'+define+NORTL_COV_OUTPUT_DIRECTORY="{working_dir.as_posix()}"',
            '+define+NORTL_COV_TEST_NAME="pytest"',
            str(testbench_file),
            *(str(file) for file in source_files),
        ]

        return '\n'.join(lines) + '\n'

    def compile(self, working_dir: Path, *source_files: Union[Path, str]) -> Path:
        """Compile with Icarus Verilog."""
        command_file: Path = working_dir / 'args.f'
        compiled_file: Path = working_dir / 'testbench.vvp'

        # Build command file
        command_file_text = self.create_command_file(working_dir, *source_files)
        command_file.write_text(command_file_text)

        # Compile
        args = ['iverilog', '-g2012', '-f', str(command_file), '-o', str(compiled_file)]
        compile_result = subprocess.run(args, capture_output=True, text=True)

        if compile_result.returncode != 0:
            pytest.fail(f'Verilog compilation failed:\n{compile_result.stderr}')
        return compiled_file

    def run(self, compiled_file: Path) -> subprocess.CompletedProcess[str]:
        """Executes the compiled Verilog simulation."""
        cmd = ['vvp', str(compiled_file)]

        return subprocess.run(cmd, capture_output=True, text=True)
