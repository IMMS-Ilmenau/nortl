import re
import shutil
from pathlib import Path
from subprocess import PIPE, run
from tempfile import TemporaryDirectory

from nortl import Engine
from nortl.components import Timer
from nortl.renderer.verilog_renderer import VerilogRenderer


class VerilogError(Exception):
    pass


class SimulatorError(Exception):
    pass


def execute_test(engine: Engine, tb_filename: str) -> str:
    """Helper function that uses iverilog to simulate the testbench with the engine.

    Args:
        engine (Engine): Engine to be tested
        tb_filename (str): Filename of the testbench
    """

    verilog_file = Path(__file__).parent / 'verilog' / tb_filename

    with TemporaryDirectory() as tempdir_str:
        tempdir = Path(tempdir_str)

        # Copy verilog testbench to tempdir
        shutil.copy(verilog_file, tempdir)

        # Render engine to verilog
        renderer = VerilogRenderer(engine)
        with open(tempdir / 'dut.sv', 'w') as file:
            file.write(renderer.render())

        # Save code as artifact
        with open((Path(__file__).parent / 'artifacts') / 'dut.sv', 'w') as file:
            file.write(renderer.render())

        # Execute icarus verilog
        command = ['iverilog', '-g2005-sv', 'dut.sv', tb_filename]
        result = run(command, cwd=tempdir, stdout=PIPE, stderr=PIPE, universal_newlines=True)

        if result.returncode != 0:
            raise SimulatorError(f'Icarus Verilog Compiler Error: \n {result.stdout} \n {result.stderr}')

        # run simulation
        result = run(['vvp', 'a.out'], cwd=tempdir, stdout=PIPE, stderr=PIPE, universal_newlines=True)

        shutil.copyfile(tempdir / 'out.vcd', (Path(__file__).parent / 'artifacts') / 'out.vcd')

        if result.returncode != 0:
            raise SimulatorError(f'Icarus Verilog Runner Error: \n {result.stdout} \n {result.stderr}')

        return result.stdout


def test_timer() -> None:
    """Only test instantiation and if it really compiles."""
    engine = Engine('my_engine')
    engine.define_input('IN')
    engine.define_output('OUT')
    _ = Timer(engine)

    execute_test(engine, 'tb_timer.sv')


def test_timer_with_parameter() -> None:
    """Test instantiation with passed-through and if it really compiles."""
    engine = Engine('my_engine')
    engine.define_input('IN')
    engine.define_output('OUT')
    width = engine.define_parameter('TIMER_WIDTH', 8)
    _ = Timer(engine, width)

    execute_test(engine, 'tb_timer.sv')


def test_timer_blocking_delay() -> None:
    """Test if the blocking delay works correctly."""

    for i in range(3, 10):
        engine = Engine('my_engine')
        _ = engine.define_input('IN')
        s_out = engine.define_output('OUT')
        timer = Timer(engine)

        engine.set(s_out, 0)
        engine.sync()
        engine.set(s_out, 1)
        timer.wait_delay(i)
        engine.set(s_out, 0)
        engine.sync()

        res = execute_test(engine, 'tb_timer.sv')
        print(res)
        res = re.findall(r'cycles =\s*\d*', res)[0]
        res_value = int(res.split('=')[1])

        assert res_value == i


def test_two_timers() -> None:
    """Test if the blocking delay works correctly."""

    engine = Engine('my_engine')
    _ = engine.define_input('IN')
    s_out = engine.define_output('OUT')
    timer_1 = Timer(engine)
    timer_2 = Timer(engine)

    engine.set(s_out, 0)
    engine.sync()
    engine.set(s_out, 1)
    timer_1.wait_delay(10)
    engine.set(s_out, 0)
    engine.sync()
    engine.set(s_out, 1)
    timer_2.wait_delay(20)
    engine.set(s_out, 0)
    engine.sync()

    res = execute_test(engine, 'tb_timer.sv')
    print(res)
    res = re.findall(r'cycles =\s*\d*', res)[0]
    res_value = int(res.split('=')[1])

    assert res_value == 30
