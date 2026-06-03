# Setup

This guide describes how to measure coverage for noRTL engines.

## Monitoring coverage

Coverage monitoring must be enabled before renderering the engine to Verilog.

Call the `monitor_state_coverage()` and `monitor_transition_coverage()` methods of the [coverage manager][nortl.core.coverage.manager.CoverageManager] after building your engine.

=== "Standalone Engine"

    ```python hl_lines="10 11"
    from pathlib import Path
    from nortl import Engine
    from nortl.renderer import VerilogRenderer

    # Create engine
    engine = Engine("my_engine")
    # ... build the engine

    # Enable state and transition monitoring
    engine.coverage.monitor_state_coverage()
    engine.coverage.monitor_transition_coverage()

    # Render the engine
    renderer = VerilogRenderer(engine)
    Path("my_engine.sv").write_text(renderer.render())
    ```

=== "Test Wrapper"

    If you want to enable coverage monitoring inside the [noRTL test wrapper](../../tutorial/06_pytest.md), do so in the `callback_before_rendering()` method.

    ```python hl_lines="4 5"
    class MyTest(NoRTLTestBase[Engine]):
        # ...
        def callback_before_rendering(self, engine: Engine) -> Engine:
            engine.coverage.monitor_state_coverage()
            engine.coverage.monitor_transition_coverage()
            return engine
    ```

    Alternatively, if you have wrapped the creation of your engine in a builder function, you can also place the calls to `monitor_state_coverage()` and `monitor_transition_coverage()` there.


!!! warning

    Coverage monitoring should be enabled after all engine optimizations are completed!

    Calling `monitor_state_coverage()` or `monitor_transition_coverage()` will add print statements to all states and transitions in the engine.
    If the engine is modified afterwards, e.g. by merging states, the coverage prints may get corrupted.

## Adding Coverpoints and Covergroups

Coverpoints and covergroups are bound to a specific state in the engine. They must be added while building the engine.

=== "Coverpoint"

    ```python hl_lines="5"
    engine.define_local(error_code, width=3)
    # ...

    # Add coverpoint that checks if the engine reacts to an error code
    engine.coverage.coverpoint(error_code != 0, "Checked error handling") #(1)!
    ```

    1. Coverpoints can be named manually (like here) or automatically. If no name is provided, `engine.coverage.coverpoint()` will return the automatically given name.

=== "Covergroup"

    ```python hl_lines="5"
    engine.define_local(error_code, width=3)
    # ...

    # Add a covergroup that checks if the engine has reacted to all error codes
    engine.coverage.covergroup("All errors tested", [(error_code, 0, 7)]) #(1)!
    ```

    1. 0 and 7 span the (inclusive) range of values for `error_code`, that must be covered. Instead of hardcoding the maximum to 7, you could use `(2**error_code.width) - 1`.

## Simulation Requirements

If a noRTL engine was rendered to Verilog with coverage prints, you need to provide a [coverage writer](coverage_writer.md) for the testbench.
It will create a [coverage file](coverage_files.md) for each engine in the simulation run, that can later be parsed and back-annotated.

### noRTL Test Wrapper

When using the [noRTL test wrapper](../../tutorial/06_pytest.md), the coverage writer is already included in the simulation environment.

### Custom Simulator

The coverage writer must be available as a **toplevel instance** named `coverage_writer`, to allow all noRTL engines to reach it.
For example, the noRTL engine will call a function `coverage_writer.emit_info(...)`.

Depending on your simulator, you may need to explicitely set the coverage_writer as a second toplevel, next to the testbench.
For example, with Xcelium use `xrun -top <testbench_name> -top coverage_writer ...`.

???+ info "Changing the Instance Name"

    It is possible to override the instance name of the coverage writer through a class attribute on the [CoverageWriter][nortl.renderer.verilog_utils.print_handlers.CoverageWriter].

    This must be done before rendering the engine to Verilog.

    ```python hl_lines="6"
    from nortl.renderer.verilog_utils.print_handlers import CoverageWriter

    # ...

    # Change name from 'coverage_writer' to 'nortl_coverage_writer'
    CoverageWriter.INSTANCE_NAME = 'nortl_coverage_writer'

    # Render the engine
    renderer = VerilogRenderer(engine)
    Path("my_engine.sv").write_text(renderer.render())
    ```

#### Environment Variables

The coverage writer requires some information, that is either read from environment variables (in default mode) or defines (in integrated test mode):

- If coverage is enabled.
- The output directory for coverage files.
- The name of the testbench, to spearate coverage files from multiple testbenches.

=== "Default Mode"

    By default, all are read from **environment variables**:

    - `$NORTL_COV` defines if coverage emission is enabled. Any non-empty value works, e.g. `export NORTL_COV=1`.
    - `$NORTL_COV_OUTPUT_DIRECTORY` or `$TB_OUTDIR` define the output directory.
    - `$NORTL_COV_TEST_NAME` or `$TEST_NAME` define the test name.

    If there are multiple options, the first non-empty environment variable is used. If no value is found, the coverage writer will stop simulation with a `$fatal` call.

=== "Integrated Test Mode"

    The coverage writer also supports a **integrated test** mode, where the variables are read from define macros instead.
    This is internally used by the noRTL test wrapper, but may also be enabled by custom simulations.

    Notably, it is required when using [Icarus Verilog](https://steveicarus.github.io/iverilog/), because it does not understand dynamic array parameters.

    Integrated test mode is enabled by setting the define macro ``NORTL_INTEGRATED_TEST`.
    Then, the coverage writer will use the following define macros:

    - ``NORTL_COV` enables coverage emission (if defined).
    - ``NORTL_COV_OUTPUT_DIRECTORY` defines the output directory.
    - ``NORTL_COV_TEST_NAME` defines the test name.

    Note that ``NORTL_COV_OUTPUT_DIRECTORY` and ``NORTL_COV_TEST_NAME` must be defined, even if coverage is disabled.

#### Raw Mode

The coverage writer provided with noRTL uses some SystemVerilog features, that are not widely supported by all simulators.
Notably, [Icarus Verilog](https://steveicarus.github.io/iverilog/) does neither understand the associative arrays used to mimic JSON objects, nor some of the dynamic arrays.

If you notice any compilation or simulation errors in the coverage writer, you can switch it to **raw mode**.
This is done by setting the define macro ``NORTL_RAW_MODE`.

In this mode, the coverage writer will only expose a low-level function to write raw JSON strings to the coverage file, while the higher-level functions with possible compatibility issues are omitted.

!!! tip

    If you need to use **raw mode** due to compatibility issues, you may also need to switch to **integrated test mode**.

To use raw mode, you also need to configure the [print handler for coverage][nortl.renderer.verilog_utils.print_handlers.CoverageWriter] before rendering the Verilog output.
This is done via a class attribute:

```python hl_lines="5"
from nortl.renderer.verilog_utils.print_handlers import CoverageWriter
# ...

# Enable raw mode
CoverageWriter.RAW_MODE = True

# Render the engine
renderer = VerilogRenderer(engine)
Path("my_engine.sv").write_text(renderer.render())
```

## Synthesis Guards

When rendering a noRTL engine with coverage monitoring, the Verilog file will include non-synthesizable code.

By default, the entire block of print statements is wrapped in **synthesis guards**: `// synthesis translate_off` and `// synthesis translate_on`.

If these are not supported by your synthesis tool, you can choose other values through the `synthesis_guard` argument of the [VerilogRenderer][nortl.renderer.verilog_renderer.VerilogRenderer]:

```python hl_lines="10"
from nortl.renderer import VerilogRenderer
# ...

# Alternative synthesis guard (tuple of opening and closing line)
SYNTHESIS_GUARD = (
    '`IFDEF SYNTH',
    '`ENDIF'
)

renderer = VerilogRenderer(engine, synthesis_guard=SYNTHESIS_GUARD)
```

## Annotation

After running simulations, the coverage information collected in the coverage files can be back-annotated to the engine.
The coverage files will end up in the output directory of the coverage writer.

If multiple noRTL engines are used in a design, there will be one file per engine.

=== "Standalone Engine"

    ```python hl_lines="10 13 14"
    from pathlib import Path
    from nortl import Engine

    # Create engine
    engine = Engine("my_engine")
    # ... build the engine

    # Annotate a coverage file
    coverage_file = Path("sim/results/my_engine.coverage.jsonl")
    engine.coverage.annotate(coverage_file)

    # Print statistics of state and transition coverage
    print(engine.coverage.state_coverage)
    print(engine.coverage.transition_coverage)
    ```

=== "Test Wrapper"

    If you want to annotate coverage results inside the [noRTL test wrapper](../../tutorial/06_pytest.md), do so in the `callback_after_execution()` method.
    The test wrapper will automatically set the path to the coverage file in `self.coverage_file`.

    ```python hl_lines="4 7 8"
    class MyTest(NoRTLTestBase[Engine]):
        # ...
        def callback_after_execution(self, engine: Engine) -> None:
            engine.coverage.annotate(self.coverage_file)

            # Check that all states and transitions are covered
            assert engine.coverage.state_coverage.covered == engine.coverage.state_coverage.total
            assert engine.coverage.transition_coverage.covered == engine.coverage.transition_coverage.total
    ```

As show in the example, the [coverage manager][nortl.core.coverage.manager.CoverageManager] offers statistics for state and transition coverage.
The objects contain the number of covered, uncovered and total states and transitions in all engines.

!!! experimental

    Coverage annotation is experimental.
    The current implementation uses [pydantic](https://pydantic.dev) to parse the individual JSON records from the coverage files.
    This is extremely slow and needs to be improved in the future.

### Checking Coverpoints and Covergroups

The coverage manager also offers statistics for coverpoints.
This includes all coverpoints, both created via `engine.coverage.coverpoint()` and `engine.coverage.covergroup()`.

```python hl_lines="6 9"
# ...
engine.coverage.annotate(coverage_file)

# Print statistics for coverpoints
# This will include all coverpoints, both individual and those from covergroups
print(engine.coverage.coverpoint_coverage)

# Check if all coverpoints are covered
assert engine.coverage.coverpoint_coverage.covered == engine.coverage.coverpoint_coverage.total
```

You can also check coverage statistics for individual coverpoints and and covergroups:

=== "Coverpoint"

    ```python hl_lines="5"
    # ...
    engine.coverage.annotate(coverage_file)

    # Check a specific coverpoint (by its name)
    assert engine.coverage.coverpoints['Checked error handling'].covered
    ```

=== "Covergroup"

    ```python hl_lines="5 6"
    # ...
    engine.coverage.annotate(coverage_file)

    # Check statistics for a specific covergroup
    stats = engine.coverage.covergroups["All errors tested"].coverage
    assert stats.covered == stats.total
    ```

### Exporting Coverage

After annotating coverage to a noRTL engine, it can be exported in [EngineInfo][nortl.core.serialization.engine_info.EngineInfo] JSON format.

```python hl_lines="9 10"
from pathlib import Path
from nortl.renderer import JsonRenderer

# ...
engine.coverage.annotate(coverage_file)

# Save engine including coverage
output_file = Path('build/my_engine.json')
renderer = JsonRenderer(engine, include_coverage=True)
output_file.write_text(renderer.render())
```
