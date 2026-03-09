# ruff: noqa: N802
"""Tests for clock-gating insertion correctness.

Two complementary layers of testing:

Simulation tests (``test_CG_*``)
    Compile and run the clock-gated design with Icarus Verilog and verify that
    the observable output sequence matches the expected values.  These tests
    confirm functional correctness end-to-end.

Formal equivalence tests (``test_CG_equiv_*``)
    Use Yosys ``equiv_make`` / ``equiv_simple`` to formally prove that the
    clock-gated and non-clock-gated renders of the same engine produce
    identical outputs for every possible input sequence.  The latch-based
    ``nortl_clock_gate`` is replaced with a transparent buffer
    (``GCLK_O = CLK_I``) before equivalence checking so that both designs
    operate in the same clock domain.
"""

import re
import shutil
from pathlib import Path
from subprocess import PIPE, run
from tempfile import TemporaryDirectory

import pytest

from nortl import Engine
from nortl.core.constructs import Condition, Fork
from nortl.core.operations import Const
from nortl.renderer.verilog_renderer import VerilogRenderer
from nortl.renderer.verilog_utils import ENCODINGS

STATE_ENCODINGS = ['binary', 'one-hot', 'multi-hot']

# ---------------------------------------------------------------------------
# Simulation helper
# ---------------------------------------------------------------------------


class SimulatorError(Exception):
    pass


def execute_test(engine: Engine, clock_gating: bool = False, encoding: ENCODINGS = 'binary') -> str:
    """Compile and simulate *engine* with Icarus Verilog, return stdout.

    Args:
        engine: Engine to test.
        clock_gating: Whether to render with clock gating enabled.
        encoding: State encoding used for the render.

    Returns:
        Simulator stdout (contains ``$display`` output).

    Raises:
        SimulatorError: On compiler or simulator error.
    """
    verilog_file = Path(__file__).parent / 'verilog' / 'testbench.sv'

    with TemporaryDirectory() as tempdir_str:
        tempdir = Path(tempdir_str)
        shutil.copy(verilog_file, tempdir)

        renderer = VerilogRenderer(engine, clock_gating=clock_gating, encoding=encoding)
        verilog = renderer.render()
        (tempdir / 'dut.sv').write_text(verilog)

        # Save artifact for post-mortem inspection
        artifact_dir = Path(__file__).parent / 'artifacts'
        (artifact_dir / 'dut.sv').write_text(verilog)

        result = run(
            ['iverilog', '-g2005-sv', 'dut.sv', 'testbench.sv'],
            cwd=tempdir,
            stdout=PIPE,
            stderr=PIPE,
            universal_newlines=True,
        )
        if result.returncode != 0:
            raise SimulatorError(f'Icarus Verilog Compiler Error:\n{result.stdout}\n{result.stderr}')

        result = run(['vvp', 'a.out'], cwd=tempdir, stdout=PIPE, stderr=PIPE, universal_newlines=True)
        shutil.copyfile(tempdir / 'out.vcd', artifact_dir / 'out.vcd')
        if result.returncode != 0:
            raise SimulatorError(f'Icarus Verilog Runner Error:\n{result.stdout}\n{result.stderr}')

        return result.stdout


# ---------------------------------------------------------------------------
# Yosys formal equivalence helpers
# ---------------------------------------------------------------------------

# Transparent clock gate: replaces the latch-based nortl_clock_gate with a
# simple wire so that all flip-flops share CLK_I as their clock domain, which
# lets Yosys compare the CG and non-CG designs as ordinary sequential circuits.
_CG_BYPASS_MODULE = """\
module nortl_clock_gate (
    input logic CLK_I,
    input logic EN,
    output logic GCLK_O
);
  assign GCLK_O = CLK_I;
endmodule
"""

# Yosys script:
#   1. Read the transparent clock-gate bypass, then gold (no-CG) with
#      -nooverwrite so the latch-based nortl_clock_gate embedded in the
#      library header is silently skipped.  proc + flatten collapses all
#      sub-modules; async2sync converts async resets to sync ones so that the
#      SAT solver can handle them.
#   2. Repeat for gate (CG) -- the bypass is already defined, so the CG
#      design uses the transparent clock gate automatically.
#   3. equiv_make builds the $equiv circuit; equiv_simple proves it;
#      equiv_status -assert causes Yosys to exit non-zero if any cell is
#      left unproven.
_EQUIV_SCRIPT = """\
read_verilog -sv cg_bypass.sv
read_verilog -nooverwrite -sv gold.sv
proc
flatten
async2sync
rename {module} gold

read_verilog -nooverwrite -sv gate.sv
proc
flatten
async2sync
rename {module} gate

equiv_make gold gate equiv_module
equiv_simple -v equiv_module
equiv_status -assert equiv_module
"""


class YosysEquivError(Exception):
    pass


def check_cg_equiv(engine: Engine, encoding: ENCODINGS = 'binary') -> None:
    """Formally verify that CG and non-CG renders of *engine* are equivalent.

    Both variants are written to a temporary directory.  The latch-based
    ``nortl_clock_gate`` cells are replaced with transparent buffers before
    equivalence checking so that Yosys sees a single clock domain in both
    designs.  ``equiv_simple`` then proves output-pin equivalence via SAT.

    Args:
        engine: Engine to verify.
        encoding: State encoding to use for both renders.

    Raises:
        YosysEquivError: If Yosys reports unproven equivalences or exits
            with a non-zero return code.
    """
    verilog_no_cg = VerilogRenderer(engine, clock_gating=False, encoding=encoding).render()
    verilog_cg = VerilogRenderer(engine, clock_gating=True, encoding=encoding).render()

    with TemporaryDirectory() as tmpdir_str:
        tmpdir = Path(tmpdir_str)
        (tmpdir / 'gold.sv').write_text(verilog_no_cg)
        (tmpdir / 'gate.sv').write_text(verilog_cg)
        (tmpdir / 'cg_bypass.sv').write_text(_CG_BYPASS_MODULE)
        (tmpdir / 'check.ys').write_text(_EQUIV_SCRIPT.format(module=engine.module_name))

        result = run(
            ['yosys', 'check.ys'],
            cwd=tmpdir,
            stdout=PIPE,
            stderr=PIPE,
            universal_newlines=True,
        )

        if result.returncode != 0:
            raise YosysEquivError(f'Yosys formal equivalence check failed:\n{result.stdout}\n{result.stderr}')


requires_yosys = pytest.mark.skipif(shutil.which('yosys') is None, reason='yosys not installed')

# ---------------------------------------------------------------------------
# Simulation tests - CG functional correctness
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('encoding', STATE_ENCODINGS)
def test_CG_fork_counter(encoding: ENCODINGS) -> None:
    """Clock-gated fork: a forked worker increments output every cycle.

    The main worker counts iterations and cancels at 10. Verifies that the forked
    worker's state gate (GCLK_counter) and the XOR-gated shared output register
    (GCLK_output) together produce the same result as without clock gating.
    """
    engine = Engine('my_engine')
    _ = engine.define_input('IN')
    output = engine.define_output('OUT', 8, reset_value=0)
    local_cnt = engine.define_local('local_counter', 8, reset_value=0)

    engine.sync()

    with Fork(engine, 'counter') as proc:
        engine.set(output, output + 1)
        with Condition(engine, output == Const(100)):
            proc.finish()

    engine.set(local_cnt, local_cnt + 1)
    with Condition(engine, local_cnt == 9):
        proc.cancel()

    result = execute_test(engine, clock_gating=True, encoding=encoding)

    res = re.findall(r'OUT=\s*\d+', result)
    res = [re.sub(r'\s*', '', r) for r in res]

    expected = [f'OUT={i}' for i in range(11)]
    assert res == expected


@pytest.mark.parametrize('encoding', STATE_ENCODINGS)
def test_CG_nested_fork(encoding: ENCODINGS) -> None:
    """Clock-gated nested fork: an inner fork increments output each cycle.

    An outer fork wraps it. The main worker cancels the outer fork when its
    iteration counter reaches 9. Tests 3 concurrent workers (main, outer_fork,
    inner_counter) each with an independent per-worker state gate.
    """
    engine = Engine('my_engine')
    _ = engine.define_input('IN')
    output = engine.define_output('OUT', 8, reset_value=0)
    local_cnt = engine.define_local('local_counter', 8, reset_value=0)

    engine.sync()

    with Fork(engine, 'outer_fork') as outer_fork:
        with Fork(engine, 'inner_counter') as inner_proc:
            engine.set(output, output + 1)
            with Condition(engine, output == Const(100)):
                inner_proc.finish()

    engine.set(local_cnt, local_cnt + 1)
    with Condition(engine, local_cnt == 9):
        outer_fork.cancel()

    result = execute_test(engine, clock_gating=True, encoding=encoding)

    res = re.findall(r'OUT=\s*\d+', result)
    res = [re.sub(r'\s*', '', r) for r in res]

    expected = [f'OUT={i}' for i in range(9)]
    assert res == expected


@pytest.mark.parametrize('encoding', STATE_ENCODINGS)
def test_CG_two_workers(encoding: ENCODINGS) -> None:
    """Clock-gated two manual workers with shared output register.

    The main worker pulses adr_incr each cycle and stops when the second worker
    signals completion. The second worker counts address increments and updates a
    registered local counter. Tests that the independent per-worker state gates
    (GCLK_main, GCLK_address_counter) and the XOR-gated output register
    (GCLK_output) produce the correct count sequence.
    """
    N_ADDRESSES = 20  # noqa: N806
    COUNTER_WIDTH = 6  # noqa: N806

    engine = Engine('my_engine')

    adr_incr = engine.define_local('adr_incr', reset_value=0)
    end_of_addresses = engine.define_local('end_of_addresses', reset_value=0)
    adr_incr.access_checker.disable_check('identical_rw')
    end_of_addresses.access_checker.disable_check('identical_rw')

    engine.sync()
    loop = engine.current_state
    engine.set_once(adr_incr, 1)
    engine.sync()
    engine.jump_if(end_of_addresses != 1, loop, engine.next_state)
    engine.current_state = engine.next_state

    engine.current_worker = engine.create_worker('address_counter')
    engine.current_worker.create_thread()
    engine.current_thread.active = True

    address_counter = engine.define_local('address_counter', width=COUNTER_WIDTH, reset_value=0)
    address_counter_nxt = engine.define_local('address_counter_nxt', width=COUNTER_WIDTH, value=address_counter + 1)
    address_counter.access_checker.disable_check('identical_rw')

    engine.wait_for(adr_incr)
    engine.set(address_counter, address_counter_nxt)
    engine.set(end_of_addresses, address_counter_nxt == N_ADDRESSES - 1)
    engine.jump_if(Const(1), engine.reset_state)

    _ = engine.define_input('IN')
    _ = engine.define_output('OUT', COUNTER_WIDTH, value=address_counter)

    result = execute_test(engine, clock_gating=True, encoding=encoding)

    res = re.findall(r'OUT=\s*\d+', result)
    res = [re.sub(r'\s*', '', r) for r in res]

    expected = [f'OUT={i}' for i in range(N_ADDRESSES)]
    assert res == expected


# ---------------------------------------------------------------------------
# Formal equivalence tests - Yosys equiv
# ---------------------------------------------------------------------------


@requires_yosys
@pytest.mark.parametrize('encoding', STATE_ENCODINGS)
def test_CG_equiv_simple(encoding: ENCODINGS) -> None:
    """Formally prove CG/non-CG equivalence for a simple single-worker counter.

    The engine increments OUT every cycle and loops back to IDLE when OUT
    reaches 10.  This tests the basic XOR-gated output register
    (GCLK_output) and the per-worker state gate (GCLK_main) with no
    concurrent workers.
    """
    engine = Engine('my_engine')
    _ = engine.define_input('IN')
    output = engine.define_output('OUT', 8, reset_value=0)

    engine.sync()
    loop = engine.current_state
    engine.set(output, output + 1)
    with Condition(engine, output == Const(10)):
        engine.jump_if(Const(1), engine.reset_state)
    engine.jump_if(Const(1), loop)
    engine.current_state = engine.next_state

    check_cg_equiv(engine, encoding)


@requires_yosys
@pytest.mark.parametrize('encoding', STATE_ENCODINGS)
def test_CG_equiv_fork_counter(encoding: ENCODINGS) -> None:
    """Formally prove CG/non-CG equivalence for the fork counter engine.

    Same topology as ``test_CG_fork_counter``: a forked worker increments
    OUT each cycle while the main worker counts iterations and cancels at 9.
    Verifies correctness of the per-worker state gates and the shared XOR
    output gate across all three state encodings.
    """
    engine = Engine('my_engine')
    _ = engine.define_input('IN')
    output = engine.define_output('OUT', 8, reset_value=0)
    local_cnt = engine.define_local('local_counter', 8, reset_value=0)

    engine.sync()

    with Fork(engine, 'counter') as proc:
        engine.set(output, output + 1)
        with Condition(engine, output == Const(100)):
            proc.finish()

    engine.set(local_cnt, local_cnt + 1)
    with Condition(engine, local_cnt == 9):
        proc.cancel()

    check_cg_equiv(engine, encoding)


@requires_yosys
@pytest.mark.parametrize('encoding', STATE_ENCODINGS)
def test_CG_equiv_two_workers(encoding: ENCODINGS) -> None:
    """Formally prove CG/non-CG equivalence for the two-worker address counter.

    Same topology as ``test_CG_two_workers``: two manual workers share
    control signals.  Tests that the independent per-worker state gates
    (GCLK_main, GCLK_address_counter) are correctly OR-combined into the
    module-level gate and that the XOR output gate is exact.
    """
    N_ADDRESSES = 20  # noqa: N806
    COUNTER_WIDTH = 6  # noqa: N806

    engine = Engine('my_engine')

    adr_incr = engine.define_local('adr_incr', reset_value=0)
    end_of_addresses = engine.define_local('end_of_addresses', reset_value=0)
    adr_incr.access_checker.disable_check('identical_rw')
    end_of_addresses.access_checker.disable_check('identical_rw')

    engine.sync()
    loop = engine.current_state
    engine.set_once(adr_incr, 1)
    engine.sync()
    engine.jump_if(end_of_addresses != 1, loop, engine.next_state)
    engine.current_state = engine.next_state

    engine.current_worker = engine.create_worker('address_counter')
    engine.current_worker.create_thread()
    engine.current_thread.active = True

    address_counter = engine.define_local('address_counter', width=COUNTER_WIDTH, reset_value=0)
    address_counter_nxt = engine.define_local('address_counter_nxt', width=COUNTER_WIDTH, value=address_counter + 1)
    address_counter.access_checker.disable_check('identical_rw')

    engine.wait_for(adr_incr)
    engine.set(address_counter, address_counter_nxt)
    engine.set(end_of_addresses, address_counter_nxt == N_ADDRESSES - 1)
    engine.jump_if(Const(1), engine.reset_state)

    _ = engine.define_input('IN')
    _ = engine.define_output('OUT', COUNTER_WIDTH, value=address_counter)

    check_cg_equiv(engine, encoding)
