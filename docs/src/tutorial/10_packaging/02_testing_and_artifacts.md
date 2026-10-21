# Testing and Artifacts

Now we verify that the engine works correctly. Following [Pytest](../06_pytest.md), we use `NoRTLTestBase` to create tests that compile and simulate the generated Verilog.

## Writing Simulation Tests

A simulation test in noRTL has three parts, each living in its own method:

- **`init_sequence()`** — creates and configures the engine. This is where you set up ports, parameters, and anything else the DUT needs before it starts running.
- **`dut()`** — describes the design under test. For us, this is simply `engine.build()`, which sets up the entire state machine.
- **`the_testbench()`** — runs in parallel with the DUT. It drives inputs, waits for expected outputs, and uses assertions to verify correctness.

There's also a fourth optional method:

- **`verify_final_state()`** — optional state sequence placed after the DUT and testbench threads in the generated FSM. It runs during simulation, not as Python after `vvp`. Use `self.assertTrue` / `self.assertEqual`.

Let's walk through the first test: verifying that the traffic light cycles through its phases correctly.

### Test 1: The Normal Cycle

This is the simplest and most important test — it checks that the engine transitions through NS_GREEN, NS_YELLOW, EW_GREEN, and EW_YELLOW in the right order.

```python title="tests/test_engine.py"
"""Tests for the traffic light engine using NoRTLTestBase."""

from nortl.utils.test_wrapper import NoRTLTestBase
from nortl import Engine


class TestNormalCycle(NoRTLTestBase[Engine]):
    """Verify the traffic light cycles through all four phases."""

    def init_sequence(self) -> Engine:
        from traffic_light import TrafficLightEngine
        engine = TrafficLightEngine("my_engine")

        # Speed up simulation: each "second" becomes one clock cycle.
        # Without this, a 10-second green phase would take 10 million
        # simulation cycles — doable but unnecessarily slow for a test.
        engine.fclk = 1

        # We need a way to stop the DUT after one cycle. The engine's
        # main loop is infinite in hardware, but the simulation needs
        # both threads to finish. We create a local signal that the
        # testbench will assert when it's done verifying.
        self.stop_signal = engine.define_local("TEST_STOP", 1, 0)

        # The DUT and the testbench are separate forks. A signal that one
        # writes and the other reads raises NonIdenticalRWError unless this
        # check is disabled. assertTrue wraps its condition in
        # UnregisteredRead, so it does not need the same exception.
        for signal in (
            engine.emergency,
            engine.ped_request,
            engine.status,
            self.stop_signal,
        ):
            signal.access_checker.disable_check("identical_rw")
        return engine

    def dut(self, engine: Engine) -> None:
        # Pass the stop signal so the engine knows when to exit.
        # In production (without a stop signal), the loop runs forever.
        engine.build(stop_signal=self.stop_signal)

    def the_testbench(self, engine: Engine) -> None:
        # First, make sure no external signals interfere.
        engine.set(engine.emergency, 0)
        engine.set(engine.ped_request, 0)
        engine.sync()

        # Wait until the engine reaches NS_GREEN (status == 0b0001).
        # wait_for() blocks the testbench until the condition is true,
        # letting the DUT advance its state machine.
        engine.wait_for(engine.status == 0b0001)

        # Now check that the outputs match what we expect for NS_GREEN.
        # assertTrue() is noRTL's assertion method — it checks that the
        # given condition is true and records an error if not. It's like
        # Python's unittest.TestCase.assertTrue, but the error is captured
        # in the Verilog simulation (not raised as a Python exception),
        # so it works correctly inside the hardware testbench.
        self.assertTrue(engine.north_en == 1)
        self.assertTrue(engine.south_en == 1)
        self.assertTrue(engine.east_en == 0)
        self.assertTrue(engine.west_en == 0)

        # Advance a couple of cycles and wait for NS_YELLOW (status == 0b0010).
        engine.sync()
        engine.sync()
        engine.wait_for(engine.status == 0b0010)

        # NS_YELLOW is an all-red gap, and it only lasts a few cycles.
        # assertTrue() syncs, so four separate asserts would run past the
        # phase and see the next one. Check every enable in one cycle.
        self.assertTrue(
            (engine.north_en == 0)
            & (engine.south_en == 0)
            & (engine.east_en == 0)
            & (engine.west_en == 0)
        )

        # We've verified enough for this test. Signal the DUT to stop
        # so both threads finish and the simulation ends cleanly.
        engine.set(self.stop_signal, 1)
        engine.sync()

```

A few things to note:

- **`assertTrue` vs `assertEqual`**: noRTL's testbench provides `assertTrue()` for boolean conditions (e.g., `self.assertTrue(signal == 1)`) and `assertEqual()` for comparing values (e.g., `self.assertEqual(engine.status, 0b0001)`). Both work the same way. They're translated into Verilog assertions that get checked during simulation. Use `assertTrue` for simple true/false checks and `assertEqual` when you want to verify an exact value; `assertEqual` gives a clearer error message because it shows both the expected and actual values.

- **The stop signal pattern**: The engine's main loop is infinite, that's how hardware works. But simulation needs both threads to finish so `NoRTLTestBase` can check results. The stop signal is a testing convenience: it doesn't change the production behavior (call `build()` without it and the loop runs forever), but it lets the test end cleanly after verifying one cycle.

- **Why only verify two phases?** This test checks NS_GREEN and NS_YELLOW to keep things simple. In a real project you'd verify all four phases, and you might also add tests for edge cases like pedestrian requests. The point here is to show the pattern.

### Running the Test

Install the package in development mode and run pytest:

```bash
uv pip install -e .
uv pip install pytest
pytest tests/test_engine.py::TestNormalCycle -v
```

The `-e` flag installs the package in editable mode, meaning changes to `src/traffic_light/` are immediately reflected without reinstalling. When you run pytest, `NoRTLTestBase` automatically:

1. Calls `init_sequence()` to build the engine
2. Renders the engine to Verilog
3. Compiles with `iverilog`
4. Runs the simulation with `vvp`
5. Checks the `passed` flag and raises `pytest.fail` if errors occurred

If the test passes, you've verified that your hardware description behaves correctly *in simulation*.

## Exporting Verilog Artifacts for Synthesis Flows

Simulation tests answer the question "does my design behave correctly?" but they don't produce the files you need for hardware. For that, you need Verilog artifacts — the `.sv` files that synthesis tools consume.

Here's the key insight: **you can generate these artifacts as part of your test suite**. Instead of maintaining a separate script or manual build step, create a test that renders the engine to an `artifacts/` directory. This ties the Verilog export to your pytest flow, ensuring the artifact always reflects the last-tested design.

### The Artifact Test

This test is fundamentally different from the simulation tests. It doesn't compile or run Verilog — it only renders the engine and writes the output to a file:

```python title="tests/test_artifacts.py"
"""Generate Verilog artifacts for synthesis flows.

This test does not run any simulation. It renders the engine to
Verilog and writes the output to an artifacts directory. The
generated files can then be used with command-line synthesis tools
(e.g., Yosys, Vivado, Quartus) to produce FPGA bitstreams.
"""

from pathlib import Path

import pytest

from nortl.renderer.verilog_renderer import VerilogRenderer


# Where generated Verilog files will be written
ARTIFACTS_DIR = Path(__file__).parent / "artifacts"


@pytest.fixture(autouse=True)
def setup_artifacts_dir():
    """Ensure the artifacts directory exists before each test.

    The autouse=True means this runs automatically for every test
    in this file, so you don't need to request it explicitly.
    """
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    yield
```

```python title="tests/test_artifacts.py (continued)"

def test_export_traffic_light_verilog() -> None:
    """Render the traffic light engine to Verilog and save as artifact.

    This is the core artifact generation test. It builds the engine,
    renders it to Verilog, and writes the result to the artifacts
    directory. The assertion at the end ensures the file was actually
    created and contains data.
    """
    from traffic_light import TrafficLightEngine

    # Build the engine with a fixed module name matching the target hardware
    eng = TrafficLightEngine("traffic_light")
    eng.fclk = 1  # irrelevant for rendering, but keeps init consistent
    eng.build()

    # Render to Verilog — this is where noRTL generates the state machine
    renderer = VerilogRenderer(eng)
    verilog_code = renderer.render()

    # Write to artifacts directory
    artifact_path = ARTIFACTS_DIR / "traffic_light.sv"
    artifact_path.write_text(verilog_code)

    # Verify the file was created and is non-empty
    assert artifact_path.exists()
    assert len(verilog_code) > 0

    # Print path for CI/CD pipelines and debugging
    print(f"Artifact written to: {artifact_path.resolve()}")
```

**Why a separate test instead of a script?** There are three reasons:

1. **Consistency**: The artifact is generated by the same code path as the simulation tests. If you change the engine, both the simulation and the artifact update together.
2. **CI/CD integration**: A pytest run produces both simulation results *and* Verilog files. You don't need separate build commands — `pytest` is the single entry point.
3. **Version tracking**: When you commit artifacts to git (optional, see below), they're guaranteed to match the code that generated them because the test runs as part of the same pipeline.

### Integrating with Synthesis Toolchains

Once you have the artifact files, you can feed them into any synthesis flow. The simplest approach is to add a **post-test synthesis check** — a pytest fixture that runs synthesis automatically after all simulation tests pass. This catches synthesis errors early in your CI pipeline without requiring any separate build scripts.

Add this fixture to `tests/conftest.py`:

```python tests="tests/conftest.py"
import subprocess
from pathlib import Path

import pytest


@pytest.fixture(autouse=True, scope="session")
def check_synthesis_after_tests():
    """After all tests pass, run a quick synthesis check.

    This fixture runs automatically after every test in the session.
    If the artifact exists, it invokes Yosys to synthesize the design.
    A non-zero exit code fails the entire test session with a clear error.
    """
    yield  # Run all tests first

    artifacts_dir = Path(__file__).parent / "artifacts"
    verilog_file = artifacts_dir / "traffic_light.sv"

    if verilog_file.exists():
        result = subprocess.run(
            ["yosys", "-p", "read_verilog traffic_light.sv; synth", str(verilog_file)],
            cwd=artifacts_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            pytest.fail(f"Synthesis failed:\n{result.stderr}")
```

This fixture runs *after* all tests complete. If simulation passes but synthesis fails, you get a clear error message pointing to the exact issue — no separate scripts or manual steps needed.

For more complex flows (full place-and-route, multiple target devices), you can extend this pattern by calling additional tools in the fixture or by creating a dedicated CI job that runs after `pytest` succeeds.

### Managing Artifacts in Version Control

The artifacts directory can grow quickly, especially with parametric generation. You have two choices:

- **Exclude from git** (recommended): Add `tests/artifacts/*.sv` to `.gitignore`. Artifacts are regenerated on each test run, so there's no need to track them. This keeps your repository clean and ensures artifacts always match the current code.
- **Commit artifacts**: If you want to track design evolution over time (e.g., "how did resource usage change after this optimization?"), commit the artifacts. This is useful for academic or certification contexts where you need a record of each design revision.

## Standalone Verilog Generation

While the artifact test is the recommended approach, you may occasionally need to generate Verilog outside of pytest — for example, during interactive development or as part of a manual build process. A simple script suffices:

```python test="generate.py"
from traffic_light import TrafficLightEngine
from nortl.renderer.verilog_renderer import VerilogRenderer

engine = TrafficLightEngine("traffic_light")
engine.build()

renderer = VerilogRenderer(engine)
with open("traffic_light.sv", "w") as f:
    f.write(renderer.render())

print("Generated traffic_light.sv")
```

Run it with `python generate.py`. This is useful for quick iteration, but remember: the artifact test (above) is preferred for production workflows because it ties generation to your test suite.

## Best Practices

### 1. Keep Controllers Stateless (Except for Signals)

Your controller classes should manage signals via the engine but avoid holding mutable Python state that affects hardware behavior. The engine's state machine is the single source of truth. Python variables that change during execution don't map to hardware and can lead to confusing bugs.

```python
# Good: signal-based state management.
class PumpController:
    def __init__(self, engine: Engine, timer: Timer):
        self.engine = engine
        self.timer = timer
        self.pump_en = engine.define_local("PUMP_EN", 1, 0)

    def start(self, duration: int):
        self.engine.sync()  # The reset value is already 0. Do not assign 1 in that same state.
        self.engine.set(self.pump_en, 1)
        self.engine.sync()
        self.timer.wait_delay(duration)
        self.engine.set(self.pump_en, 0)
```

### 2. Use `engine.define_scratch()` for Intermediate Values

When your controllers need temporary variables for calculations, use scratch signals instead of Python variables. Scratch signals are managed by noRTL's internal memory manager and automatically allocated from a shared scratch pad. This avoids polluting the signal namespace and ensures resources are released when their scope ends.

```python
@Segment
def compute_checksum(engine: EngineProto, data: Renderable) -> None:
    checksum = engine.define_scratch(8)
    for i in range(8):
        engine.set(checksum, checksum ^ data[i])
```

### 3. Separate DUT and Testbench Logic

Follow the separation established in `NoRTLTestBase`. The DUT (`dut()`) describes the hardware; the testbench (`the_testbench()`) drives inputs and checks outputs. Mixing them makes tests harder to read and debug.

| Method                 | Purpose                                         |
| ---------------------- | ----------------------------------------------- |
| `init_sequence()`      | Create and configure the engine                 |
| `dut()`                | The hardware design under test                  |
| `the_testbench()`      | Stimulus and verification logic                 |
| `verify_final_state()` | In-simulation checks after both threads finish  |

### 4. Parameterize Your Engine

Make your engine configurable so it can be reused across different designs. Instead of hardcoding durations, expose them as constructor parameters:

```python
class TrafficLightEngine(Engine):
    def __init__(
        self,
        module_name: str = "traffic_light",
        green_duration: int = 10,
        yellow_duration: int = 3,
    ):
        super().__init__(module_name)
        self.green_duration = green_duration
        self.yellow_duration = yellow_duration
```

This allows you to instantiate the same engine with different timing for different target platforms.

### 5. Bundle Verilog IP with Your Package

If you have custom Verilog modules, ship them alongside your Python package and register them in `verilog_ip/__init__.py`. This keeps all hardware description — both Python-generated and hand-written Verilog — in one place, making the package self-contained.

### 6. Use Artifact Tests for Synthesis Integration

Keep your Verilog export tied to the pytest flow by using artifact tests (above). This ensures the generated Verilog always reflects the last-tested design, CI/CD pipelines can run synthesis immediately after tests pass, and multiple encoding variants can be generated and compared automatically — all through a single `pytest` command.

## Summary

Packaging a noRTL engine as a Python library gives you:

- **Reusability**: import your engine in other projects like any Python package
- **Testability**: separate simulation tests from artifact generation, each with a clear purpose
- **Synthesis integration**: generate Verilog files as part of your test flow, ready for e.g. Yosys
- **Dependency clarity**: `pyproject.toml` makes it explicit what your design needs
- **Version control**: track design changes alongside your code

The key insight is that noRTL engines are pure Python objects. They don't require any special runtime, the Verilog is generated at render time. This means standard Python packaging tools work out of the box, and your entire hardware development workflow  can be driven by a single `pytest` command.
