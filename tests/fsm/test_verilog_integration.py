# ruff: noqa: N802

import re
import shutil
from pathlib import Path
from subprocess import PIPE, run
from tempfile import TemporaryDirectory
from typing import Tuple

import pytest

from nortl import Engine
from nortl.core.constructs import Condition, Fork, ForLoop
from nortl.core.constructs.loop import WhileLoop
from nortl.core.operations import Concat, Const
from nortl.core.protocols import SignalProto
from nortl.renderer.verilog_renderer import VerilogRenderer
from nortl.renderer.verilog_utils import ENCODINGS


class VerilogError(Exception):
    pass


class SimulatorError(Exception):
    pass


STATE_ENCODINGS = ['binary', 'one-hot', 'multi-hot']


def execute_test(engine: Engine, clock_gating: bool = False, encoding: ENCODINGS = 'binary') -> str:
    """Helper function that uses iverilog to simulate the testbench with the engine.

    Args:
        engine: engine to be tested
        clock_gating: If clock gating should be used in this test
        encoding: state encoding used for the test
    """

    verilog_file = Path(__file__).parent / 'verilog' / 'testbench.sv'

    with TemporaryDirectory() as tempdir_str:
        tempdir = Path(tempdir_str)

        # Copy verilog testbench to tempdir
        shutil.copy(verilog_file, tempdir)

        # Render engine to verilog
        renderer = VerilogRenderer(engine, clock_gating=clock_gating, encoding=encoding)
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


@pytest.mark.parametrize('encoding', STATE_ENCODINGS)
def test_simulation_setup(encoding: ENCODINGS) -> None:
    """Test that the engine can be simulated by using an empty engine."""
    engine = Engine('my_engine')
    _ = engine.define_input('IN')
    _ = engine.define_output('OUT', 8)
    _ = execute_test(engine, encoding=encoding)


@pytest.mark.parametrize('encoding', STATE_ENCODINGS)
def test_output_probe(encoding: ENCODINGS) -> None:
    """Tests, if the output values can actually be probed."""
    engine = Engine('my_engine')
    _ = engine.define_input('IN')
    output = engine.define_output('OUT', 8)
    engine.set(output, 0)
    engine.sync()
    engine.set(output, 55)
    engine.wait_for(output == 1)  # Stop execution

    result = execute_test(engine, encoding=encoding)

    print(result)

    assert 'OUT= 55' in result


@pytest.mark.parametrize('encoding', STATE_ENCODINGS)
def test_output_combinational(encoding: ENCODINGS) -> None:
    """Tests, if the output values can actually be probed."""
    engine = Engine('my_engine')
    _ = engine.define_input('IN')
    output_old = engine.define_output('OUT2', 8)
    _ = engine.define_output('OUT', 8, value=output_old)
    engine.set(output_old, 0)
    engine.sync()
    engine.set(output_old, 55)
    engine.wait_for(output_old == 1)  # Stop execution

    result = execute_test(engine, encoding=encoding)

    print(result)

    assert 'OUT= 55' in result


@pytest.mark.parametrize('encoding', STATE_ENCODINGS)
def test_output_count(encoding: ENCODINGS) -> None:
    """Tests, if the output values can actually be probed."""
    engine = Engine('my_engine')
    _ = engine.define_input('IN')
    output = engine.define_output('OUT', 8)
    for i in range(16):
        engine.set(output, i)
        engine.sync()
    engine.wait_for(output == 1)  # Stop execution

    result = execute_test(engine, encoding=encoding)

    res = re.findall(r'OUT=\s*\d+', result)
    res = [re.sub(r'\s*', '', r) for r in res]

    expected = [f'OUT={i}' for i in range(16)]

    assert res == expected


@pytest.mark.parametrize('encoding', STATE_ENCODINGS)
def test_output_count_ForLoop(encoding: ENCODINGS) -> None:
    """Tests, if the output values can actually be probed."""
    engine = Engine('my_engine')
    _ = engine.define_input('IN')
    output = engine.define_output('OUT', 8)

    engine.sync()

    with ForLoop(engine, 0, 16) as ptr:
        engine.set(output, ptr)

    engine.wait_for(output == 1)  # Stop execution

    result = execute_test(engine, encoding=encoding)

    res = re.findall(r'OUT=\s*\d+', result)
    res = [re.sub(r'\s*', '', r) for r in res]

    expected = [f'OUT={i}' for i in range(16)]

    assert res == expected


@pytest.mark.parametrize('encoding', STATE_ENCODINGS)
def test_WhileLoop(encoding: ENCODINGS) -> None:
    engine = Engine('my_engine')
    IN = engine.define_input('IN')  # noqa: N806
    OUT = engine.define_output('OUT', 8)  # noqa: N806

    engine.sync()

    with WhileLoop(engine, OUT < 4):
        engine.wait_for(IN == 1)
        engine.set(OUT, OUT + 1)
        engine.sync()
        engine.wait_for(IN == 0)

    result = execute_test(engine, encoding=encoding)

    res = re.findall(r'OUT=\s*\d+', result)
    res = [re.sub(r'\s*', '', r) for r in res]

    expected = [f'OUT={i}' for i in range(5)]

    assert res == expected


@pytest.mark.parametrize('encoding', STATE_ENCODINGS)
def test_slicing(encoding: ENCODINGS) -> None:
    """Tests, if renderables are sliced correctly."""
    engine = Engine('my_engine')
    _ = engine.define_input('IN')
    output = engine.define_output('OUT', 8)
    a = engine.define_local('a', 8, 6)
    b = engine.define_local('b', 8, 5)

    for i in range(16):
        engine.set(output, i)
        engine.sync()

    engine.set(output, (a + b)[3:0])
    engine.sync()

    engine.wait_for(output == 11)  # Stop execution

    result = execute_test(engine, encoding=encoding)

    res = re.findall(r'OUT=\s*\d+', result)
    res = [re.sub(r'\s*', '', r) for r in res]

    expected = [f'OUT={i}' for i in range(16)] + ['OUT=11']
    print(res)

    assert res == expected


@pytest.mark.parametrize('encoding', STATE_ENCODINGS)
def test_slicing_of_concat(encoding: ENCODINGS) -> None:
    """Tests, if a Concat is sliced correctly."""
    engine = Engine('my_engine')
    _ = engine.define_input('IN')
    output = engine.define_output('OUT', 8)
    a = engine.define_local('a', 8, 6)
    b = engine.define_local('b', 8, 5)

    for i in range(16):
        engine.set(output, i)
        engine.sync()

    engine.set(output, Concat(a, b)[3:0])
    engine.sync()

    engine.wait_for(output == 11)  # Stop execution

    result = execute_test(engine, encoding=encoding)

    res = re.findall(r'OUT=\s*\d+', result)
    res = [re.sub(r'\s*', '', r) for r in res]

    expected = [f'OUT={i}' for i in range(16)] + ['OUT=5']
    print(res)

    assert res == expected


@pytest.mark.parametrize('encoding', STATE_ENCODINGS)
def test_output_count_CG(encoding: ENCODINGS) -> None:
    """Tests, if the output values can actually be probed -- with enabled clock gating."""
    engine = Engine('my_engine')
    _ = engine.define_input('IN')

    engine.current_state.set_metadata('Clock_gating', True)

    output = engine.define_output('OUT', 8)
    for i in range(16):
        engine.set(output, i)
        engine.sync()
    engine.wait_for(output == 1)  # Stop execution

    result = execute_test(engine, clock_gating=True, encoding=encoding)

    res = re.findall(r'OUT=\s*\d+', result)
    res = [re.sub(r'\s*', '', r) for r in res]

    expected = [f'OUT={i}' for i in range(16)]

    assert res == expected


@pytest.mark.parametrize('encoding', STATE_ENCODINGS)
def test_rising_edge(encoding: ENCODINGS) -> None:
    """Tests, if the rising-edge detection works."""
    engine = Engine('my_engine')
    input = engine.define_input('IN')
    output = engine.define_output('OUT', 8)

    for i in range(16):
        engine.wait_for(input.rising())
        engine.set(output, i)
    engine.wait_for(output == 1)  # Stop execution

    result = execute_test(engine, encoding=encoding)

    res = re.findall(r'OUT=\s*\d+', result)
    res = [re.sub(r'\s*', '', r) for r in res]

    expected = [f'OUT={i}' for i in range(6)]

    print(res)
    assert res == expected


@pytest.mark.parametrize('encoding', STATE_ENCODINGS)
def test_falling_edge(encoding: ENCODINGS) -> None:
    """Tests, if the falling-edge detection works."""
    engine = Engine('my_engine')
    input = engine.define_input('IN')
    output = engine.define_output('OUT', 8)

    for i in range(16):
        engine.wait_for(input.falling())
        engine.set(output, i)
    engine.wait_for(output == 1)  # Stop execution

    result = execute_test(engine, encoding=encoding)

    res = re.findall(r'OUT=\s*\d+', result)
    res = [re.sub(r'\s*', '', r) for r in res]

    expected = [f'OUT={i}' for i in range(5)]

    print(res)
    assert res == expected


@pytest.mark.parametrize('encoding', STATE_ENCODINGS)
def test_delay_1(encoding: ENCODINGS) -> None:
    """Tests, if the falling-edge detection concetenated with a delay works."""
    engine = Engine('my_engine')
    input = engine.define_input('IN')
    output = engine.define_output('OUT', 8)

    delayed_input = input.delayed(1)

    for i in range(16):
        engine.wait_for(delayed_input.falling())
        engine.set(output, i)
    engine.wait_for(output == 1)  # Stop execution

    result = execute_test(engine, encoding=encoding)
    print(result)

    res = re.findall(r'OUT=\s*\d+', result)
    res = [re.sub(r'\s*', '', r) for r in res]

    expected = [f'OUT={i}' for i in range(5)]

    print(res)
    assert res == expected


@pytest.mark.parametrize('encoding', STATE_ENCODINGS)
def test_delay_2(encoding: ENCODINGS) -> None:
    """Tests, if the falling-edge detection concetenated with a delay works."""
    engine = Engine('my_engine')
    input = engine.define_input('IN')
    output = engine.define_output('OUT', 8)
    delayed_input = input.delayed(2)
    for i in range(16):
        engine.wait_for(delayed_input.falling())
        engine.set(output, i)
    engine.wait_for(output == 1)  # Stop execution

    result = execute_test(engine, encoding=encoding)

    res = re.findall(r'OUT=\s*\d+', result)
    res = [re.sub(r'\s*', '', r) for r in res]

    expected = [f'OUT={i}' for i in range(5)]

    print(res)
    assert res == expected


@pytest.mark.parametrize('encoding', STATE_ENCODINGS)
def test_synchronized(encoding: ENCODINGS) -> None:
    """Tests, if the falling-edge detection concetenated with a delay works."""
    engine = Engine('my_engine')
    input = engine.define_input('IN')
    output = engine.define_output('OUT', 8)

    delayed_input = input.synchronized()

    for i in range(16):
        engine.wait_for(delayed_input.falling())
        engine.set(output, i)
    engine.wait_for(output == 1)  # Stop execution

    result = execute_test(engine, encoding=encoding)
    print(result)

    res = re.findall(r'OUT=\s*\d+', result)
    res = [re.sub(r'\s*', '', r) for r in res]

    expected = [f'OUT={i}' for i in range(5)]

    print(res)
    assert res == expected


@pytest.mark.parametrize('encoding', STATE_ENCODINGS)
def test_scratch_pad(encoding: ENCODINGS) -> None:
    """Tests, if the output values can actually be probed."""
    engine = Engine('my_engine')
    _ = engine.define_input('IN')
    output = engine.define_output('OUT', 8, reset_value=0)
    engine.sync()

    with Fork(engine, 'Timeouttimer') as proc:
        test = engine.define_scratch(8)
        test.access_checker.disable_check('exclusive_read')
        test.access_checker.disable_check('identical_rw')
        engine.set(test, test + 1)

        with Condition(engine, test == 100):
            proc.finish()

        test.release()

    engine.set(output, test)
    with Condition(engine, output == 9):
        proc.cancel()

    result = execute_test(engine, encoding=encoding)

    print(result)

    res = re.findall(r'OUT=\s*\d+', result)
    res = [re.sub(r'\s*', '', r) for r in res]

    expected = [f'OUT={i}' for i in range(10)]

    assert res == expected


@pytest.mark.parametrize('encoding', STATE_ENCODINGS)
def test_multiple_workers(encoding: ENCODINGS) -> None:
    """Tests manually instantiating multiple workers.

    This is normally not recommended, users should use a Fork instead.
    """

    # Main worker - controls the counter in the second worker
    def build_main(engine: Engine) -> Tuple[SignalProto, SignalProto]:
        # Internal control signals between main and secondary worker
        adr_incr = engine.define_local('adr_incr', reset_value=0)
        end_of_addresses = engine.define_local('end_of_addresses', reset_value=0)

        # Allow adr_incr and end_of_addresses to be shared between threads
        adr_incr.access_checker.disable_check('identical_rw')
        end_of_addresses.access_checker.disable_check('identical_rw')

        # Move out of reset
        engine.sync()

        # Increment address
        loop = engine.current_state
        engine.set_once(adr_incr, 1)
        engine.sync()

        # Loop (State 4)
        # Normally, the FSM should loop back to reset_state, but then the test would never complete
        engine.jump_if(end_of_addresses != 1, loop, engine.next_state)
        engine.current_state = engine.next_state

        return adr_incr, end_of_addresses

    # Second worker - implements the counter
    # In practice, this could run in the same worker.
    def build_counter(engine: Engine, adr_incr: SignalProto, end_of_addresses: SignalProto) -> SignalProto:
        # Local signals
        # They must be defined while the address_counter thread is selected, otherwise a IDENTICAL_RW violation will be caused
        address_counter = engine.define_local('address_counter', width=ADDRESS_COUNTER_WIDTH, reset_value=0)
        address_counter_nxt = engine.define_local('address_counter_nxt', width=ADDRESS_COUNTER_WIDTH, value=address_counter + 1)

        engine.wait_for(adr_incr)
        engine.set(address_counter, address_counter_nxt)
        engine.set(end_of_addresses, address_counter_nxt == N_ADDRESSES - 1)
        engine.jump_if(Const(True), engine.reset_state)

        return address_counter

    # Build the engine
    engine = Engine('my_engine')

    # Parameters
    N_ADDRESSES = engine.define_parameter('N_ADDRESSES', 50)  # noqa: N806
    ADDRESS_COUNTER_WIDTH = engine.define_parameter('ADDRESS_COUNTER_WIDTH', 6)  # noqa: N806

    # Signals are passed around between the two build functions
    adr_incr, end_of_addresses = build_main(engine)

    engine.current_worker = engine.create_worker('address_counter')
    engine.current_worker.create_thread()
    engine.current_thread.active = True  # FIXME thread should not need manual activation

    address_counter = build_counter(engine, adr_incr, end_of_addresses)

    # All test engines require IN and OUT
    _ = engine.define_input('IN')
    _ = engine.define_output('OUT', 8, value=address_counter)

    # Execute the test
    result = execute_test(engine, encoding=encoding)

    print(result)

    res = re.findall(r'OUT=\s*\d+', result)
    res = [re.sub(r'\s*', '', r) for r in res]

    expected = [f'OUT={i}' for i in range(N_ADDRESSES.default_value)]

    assert res == expected


@pytest.mark.parametrize('encoding', STATE_ENCODINGS)
def test_selector_assignment(encoding: ENCODINGS) -> None:
    """Tests selector assignment."""
    engine = Engine('my_engine')

    _ = engine.define_input('IN')
    sig_out = engine.define_output('OUT', 8)
    sel = engine.define_local('sel', 2, reset_value=0)
    engine.sync()

    for x in range(4):
        engine.set(sel, x)
        engine.sync()

        # Effectively, the output just mirrors X, counting from 0 to 3
        # The selector uses two styles: one with default
        engine.set_when(
            sig_out,
            {
                ~sel[1]: {
                    ~sel[0]: 0,
                    'default': 1,
                },
                sel[1]: {
                    ~sel[0]: 2,
                    'default': 3,
                },
            },
        )
        engine.sync()

    result = execute_test(engine, encoding=encoding)

    print(result)

    res = re.findall(r'OUT=\s*\d+', result)
    res = [re.sub(r'\s*', '', r) for r in res]

    expected = [f'OUT={i}' for i in range(4)]

    assert res == expected
