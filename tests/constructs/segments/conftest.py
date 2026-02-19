import shutil
from pathlib import Path
from subprocess import PIPE, run
from tempfile import TemporaryDirectory
from typing import Protocol

import pytest

from nortl import Engine
from nortl.renderer.verilog_renderer import VerilogRenderer


class SimulatorError(Exception):
    pass


class TestExecutor(Protocol):
    def __call__(self, engine: Engine, clock_gating: bool = False) -> str: ...


@pytest.fixture
def execute_test() -> TestExecutor:
    def execute_test(engine: Engine, clock_gating: bool = False) -> str:
        """Helper function that uses iverilog to simulate the testbench with the engine.

        Args:
            engine (Engine): Engine to be tested
            clock_gating (bool): If clock gating should be used in this test
        """

        verilog_file = Path(__file__).parent.parent / 'verilog' / 'testbench.sv'

        with TemporaryDirectory() as tempdir_str:
            tempdir = Path(tempdir_str)

            # Copy verilog testbench to tempdir
            shutil.copy(verilog_file, tempdir)

            # Render engine to verilog
            renderer = VerilogRenderer(engine, clock_gating=clock_gating)
            with open(tempdir / 'dut.sv', 'w') as file:
                file.write(renderer.render())

            # Save code as artifact
            with open((Path(__file__).parent.parent / 'artifacts') / 'dut.sv', 'w') as file:
                file.write(renderer.render())

            # Execute icarus verilog
            command = ['iverilog', '-g2005-sv', 'dut.sv', 'testbench.sv']
            result = run(command, cwd=tempdir, stdout=PIPE, stderr=PIPE, universal_newlines=True)

            if result.returncode != 0:
                raise SimulatorError(f'Icarus Verilog Compiler Error: \n {result.stdout} \n {result.stderr}')

            # run simulation
            result = run(['vvp', 'a.out'], cwd=tempdir, stdout=PIPE, stderr=PIPE, universal_newlines=True)

            shutil.copyfile(tempdir / 'out.vcd', (Path(__file__).parent.parent / 'artifacts') / 'out.vcd')

            if result.returncode != 0:
                raise SimulatorError(f'Icarus Verilog Runner Error: \n {result.stdout} \n {result.stderr}')

            return result.stdout

    return execute_test
