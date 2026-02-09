import re
import shutil
from pathlib import Path
from subprocess import PIPE, run
from tempfile import TemporaryDirectory

from nortl import Engine
from nortl.core import Const
from nortl.core.constructs import Condition, Fork
from nortl.renderer.verilog_renderer import VerilogRenderer


class SimulatorError(Exception):
    pass


def execute_test(engine: Engine, clock_gating: bool = False) -> str:
    """Helper function that uses iverilog to simulate the testbench with the engine.

    Args:
        engine (Engine): Engine to be tested
        clock_gating (bool): If clock gating should be used in this test
    """

    verilog_file = Path(__file__).parent / 'verilog' / 'testbench.sv'

    with TemporaryDirectory() as tempdir_str:
        tempdir = Path(tempdir_str)

        # Copy verilog testbench to tempdir
        shutil.copy(verilog_file, tempdir)

        # Render engine to verilog
        renderer = VerilogRenderer(engine, clock_gating=clock_gating)
        with open(tempdir / 'dut.sv', 'w') as file:
            file.write(renderer.render())

        # Save code as artifact
        with open((Path(__file__).parent / 'artifacts') / 'dut.sv', 'w') as file:
            file.write(renderer.render())

        # Execute icarus verilog
        command = ['iverilog', '-g2005-sv', 'dut.sv', 'testbench.sv']
        result = run(command, cwd=tempdir, stdout=PIPE, stderr=PIPE, universal_newlines=True)

        if result.returncode != 0:
            raise SimulatorError(f'Icarus Verilog Compiler Error: \n {result.stdout} \n {result.stderr}')

        # run simulation
        result = run(['vvp', 'a.out'], cwd=tempdir, stdout=PIPE, stderr=PIPE, universal_newlines=True)

        shutil.copyfile(tempdir / 'out.vcd', (Path(__file__).parent / 'artifacts') / 'out.vcd')

        if result.returncode != 0:
            raise SimulatorError(f'Icarus Verilog Runner Error: \n {result.stdout} \n {result.stderr}')

        return result.stdout


def test_forked_timeout() -> None:
    """Tests, if the output values can actually be probed."""
    engine = Engine('my_engine')
    _ = engine.define_input('IN')
    output = engine.define_output('OUT', 8, reset_value=0)
    engine.sync()

    local_cnt = engine.define_local('local_counter', 8, reset_value=0)

    with Fork(engine, 'Timeouttimer') as proc:
        engine.set(output, output + 1)

        with Condition(engine, output == Const(100)):
            proc.finish()

    engine.set(local_cnt, local_cnt + 1)
    with Condition(engine, local_cnt == 9):
        proc.cancel()

    result = execute_test(engine)

    print(result)

    res = re.findall(r'OUT=\s*\d+', result)
    res = [re.sub(r'\s*', '', r) for r in res]

    expected = [f'OUT={i}' for i in range(11)]

    assert res == expected


def test_wait_for_join() -> None:
    """Tests, if the output values can actually be probed."""
    engine = Engine('my_engine')
    _ = engine.define_input('IN')
    output = engine.define_output('OUT', 8, reset_value=0)
    engine.sync()

    with Fork(engine, 'Timeouttimer') as proc:
        engine.set(output, output + 1)

        with Condition(engine, output == Const(100)):
            proc.finish()

    proc.join()
    print(proc.call_stack)
    print(engine.current_thread.call_stack)

    print([t.active for t in proc.call_stack])
    print(engine.current_thread.call_stack)

    assert not proc.running

    engine.set(output, 255)

    result = execute_test(engine)

    res = re.findall(r'OUT=\s*\d+', result)
    res = [re.sub(r'\s*', '', r) for r in res]

    expected = [f'OUT={i}' for i in range(101)] + ['OUT=255']

    assert res == expected


def test_subsequent_fork() -> None:
    engine = Engine('my_engine')
    _ = engine.define_input('IN')
    output = engine.define_output('OUT', 8, reset_value=0)
    engine.sync()

    with Fork(engine, 'dummy_to_use_worker_once') as pre_proc:
        engine.sync()

    pre_proc.join()

    with Fork(engine, 'Timeouttimer') as proc:
        engine.set(output, output + 1)

        with Condition(engine, output == Const(100)):
            proc.finish()

    proc.join()

    engine.set(output, 255)

    result = execute_test(engine)

    res = re.findall(r'OUT=\s*\d+', result)
    res = [re.sub(r'\s*', '', r) for r in res]

    expected = [f'OUT={i}' for i in range(101)] + ['OUT=255']

    assert res == expected


def test_nested_join() -> None:
    engine = Engine('my_engine')
    _ = engine.define_input('IN')
    output = engine.define_output('OUT', 8, reset_value=0)

    local_cnt = engine.define_local('local_counter', 8, reset_value=0)

    engine.sync()

    with Fork(engine, 'outer_fork') as outer_fork:
        with Fork(engine, 'Timeouttimer') as proc:
            engine.set(output, output + 1)

            with Condition(engine, output == Const(100)):
                proc.finish()

    engine.set(local_cnt, local_cnt + 1)
    with Condition(engine, local_cnt == 9):
        outer_fork.cancel()

    assert not proc.active
    assert not outer_fork.active

    result = execute_test(engine)

    print(result)

    res = re.findall(r'OUT=\s*\d+', result)
    res = [re.sub(r'\s*', '', r) for r in res]

    expected = [f'OUT={i}' for i in range(9)]

    assert res == expected


def test_current_thread_logic_in_engine() -> None:
    engine = Engine('my_engine')
    _ = engine.define_input('IN')

    engine.sync()

    with Fork(engine, 'Timeouttimer') as proc:
        engine.current_thread == proc

    proc.join()

    assert engine.current_thread == engine.main_thread


def test_correct_link_of_main_thread() -> None:
    engine = Engine('my_engine')
    _ = engine.define_input('IN')

    assert engine.current_thread == engine.main_thread
    assert engine.main_worker.threads[0] == engine.main_thread


def test_call_stack() -> None:
    engine = Engine('my_engine')
    _ = engine.define_input('IN')

    engine.sync()

    with Fork(engine, 'f1') as proc1:
        with Fork(engine, 'f2') as proc2:
            with Fork(engine, 'f3') as proc3:
                assert proc3.call_stack == [proc2, proc1, engine.main_thread]


def test_subsequent_nested_fork_worker_assign() -> None:
    engine = Engine('my_engine')

    engine.sync()

    with Fork(engine, 'f1') as proc1:
        with Fork(engine, 'f2') as proc2:
            pass

        proc2.join()

    assert engine.current_thread.call_stack == []
    assert proc2.running  # We dont know here, if proc2 has joined

    with Fork(engine, 'f3') as proc3:
        with Fork(engine, 'f4') as proc4:
            pass

    print('Proc 1 ' + proc1.worker.name)
    print('Proc 2 ' + proc2.worker.name)
    print('Proc 3 ' + proc3.worker.name)
    print('Proc 4 ' + proc4.worker.name)

    assert proc1.worker.name != proc2.worker.name
    assert proc1.worker.name != proc3.worker.name
    assert proc1.worker.name != proc4.worker.name

    assert proc2.worker.name != proc3.worker.name
    assert proc2.worker.name != proc4.worker.name

    assert proc3.worker.name != proc4.worker.name


def test_fork_metadata() -> None:
    engine = Engine('my_engine')
    _ = engine.define_input('IN')

    engine.sync()

    start_state = engine.current_state

    with Fork(engine, 'f1'):
        assert engine.current_state.get_metadata('Fork Select ID', 1)

    assert start_state.has_metadata('Forked Processes')
    assert start_state.get_metadata('Forked Processes') == [('WORKER_1', 1)]
