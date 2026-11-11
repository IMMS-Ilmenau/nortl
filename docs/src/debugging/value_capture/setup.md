# Setup

This guide describes how to capture values from noRTL engines during simulation and verify them afterwards.

While [logging](../logging/setup.md) prints diagnostic messages to the console and [coverage](../coverage/setup.md) tracks which states and transitions were visited, **value capture** records the actual values of signals at specific points in the simulation. The captured values are written to a [value capture file](value_capture.md) as JSONL, which can later be parsed and verified — for example, to check a sequence of values over the full course of the simulation.

## Capturing Values

Values are captured with `Engine.capture()`. It takes a key and one or more values, and emits one record per call:

```python hl_lines="6 7"
from nortl import Engine

# Create engine
engine = Engine("my_engine")
counter = engine.define_local("counter", 8, 0)
# ... build the engine

for _ in range(5):
    engine.set(counter, counter + 1)
    engine.capture("count", counter)          # single value
    engine.capture("pair", counter, 42)       # multiple values
    engine.sync()
```

Each call emits a JSONL record of the form:

```json
{"type": "value", "test": "<test name>", "<key>": [value1, value2, ...]}
```

The values are always written as a list, so a single-value capture is recorded as a one-element list, e.g. `{"count": [1]}`.

## Verifying Captured Values

### noRTL Test Wrapper

When using the [noRTL test wrapper](../../tutorial/06_pytest.md), the value capture file is parsed automatically after the simulation. Override the `callback_after_simulation()` method to verify the captured values:

```python hl_lines="4 5 6"
class TestClass(NoRTLTestBase[Engine]):
    # ...
    def callback_after_simulation(self, engine: Engine, captured_values: list) -> None:
        # One dict per engine.capture() call, in emission order
        assert captured_values == [
            {'count': [1]},
            {'pair': [1, 42]},
            {'count': [2]},
            {'pair': [2, 42]},
        ]
```

`captured_values` is a list of dicts — one dict per `engine.capture()` call, in emission order. Each dict maps the capture key to the captured value(s), with the `type` and `test` fields of the JSONL records removed.

!!! note

    `captured_values` contains plain Python data, not engine signals. Use regular Python `assert` statements in this callback, not `self.assertTrue`/`self.assertEqual` (which render Verilog assertions for in-simulation checks).

The parsed data is also available as `self.captured_values`, if you need it in `callback_after_execution()`. The raw JSONL file (`self.value_capture_file`) only exists while the simulation run is active.

### Custom Simulator

If you run the simulation yourself, parse the value capture file (see [value capture files](value_capture.md)) with your preferred tooling. For example, in Python:

```python
import json
from pathlib import Path

captured_values = []
for line in Path("values.values.jsonl").read_text().splitlines():
    if not line.strip():
        continue
    record = json.loads(line)
    if record.get("type") != "value":
        continue
    captured_values.append({key: value for key, value in record.items() if key not in ("type", "test")})
```

## Simulation Requirements

If a noRTL engine contains value capture calls, you need to provide a [value capture module](value_capture.md) for the testbench.

### noRTL Test Wrapper

When using the [noRTL test wrapper](../../tutorial/06_pytest.md), the value capture module is already included in the simulation environment and configured automatically.

### Custom Simulator

The value capture module must be available as a **toplevel instance** named `value_capture`, to allow all noRTL engines to reach it.
For example, the noRTL engine will call a function `value_capture.capture(...)`.

Depending on your simulator, you may need to explicitely set the value capture module as a second toplevel, next to the testbench.
For example, with Xcelium use `xrun -top <testbench_name> -top value_capture ...`.

???+ info "Changing the Instance Name"

    It is possible to override the instance name of the value capture module through a class attribute on the [ValueCapture][nortl.renderer.verilog_utils.print_handlers.ValueCapture] print handler.

    This must be done before rendering the engine to Verilog.

    ```python hl_lines="6"
    from nortl.renderer.verilog_utils.print_handlers import ValueCapture

    # ...

    # Change name from 'value_capture' to 'nortl_value_capture'
    ValueCapture.INSTANCE_NAME = 'nortl_value_capture'

    # Render the engine
    renderer = VerilogRenderer(engine)
    Path("my_engine.sv").write_text(renderer.render())
    ```

#### Environment Variables

The value capture module requires some information, that is either read from environment variables (in default mode) or defines (in integrated test mode):

- If value capture is enabled.
- The output directory for value capture files.
- The name of the testbench, to separate value capture files from multiple testbenches.

=== "Default Mode"

    By default, all are read from **environment variables**:

    - `$NORTL_VCAP` defines if value capture emission is enabled. Any non-empty value works, e.g. `export NORTL_VCAP=1`.
    - `$NORTL_VCAP_OUTPUT_DIRECTORY` or `$TB_OUTDIR` define the output directory.
    - `$NORTL_VCAP_TEST_NAME` or `$TEST_NAME` define the test name.

    If there are multiple options for the output directory or test name, the first non-empty environment variable is used. If no value is found, the value capture module will stop simulation with a `$fatal` call.

    !!! warning

        Reading environment variables requires **SystemVerilog DPI-C**, which is not supported by [Icarus Verilog](https://steveicarus.github.io/iverilog/). Use **integrated test mode** when simulating with Icarus.

=== "Integrated Test Mode"

    The value capture module also supports an **integrated test** mode, where the variables are read from define macros instead.
    This is internally used by the noRTL test wrapper, but may also be enabled by custom simulations.

    Notably, it is required when using [Icarus Verilog](https://steveicarus.github.io/iverilog/).

    Integrated test mode is enabled by setting the define macro ``NORTL_INTEGRATED_TEST`.
    Then, the value capture module will use the following define macros:

    - ``NORTL_VCAP` enables value capture emission (if defined).
    - ``NORTL_VCAP_OUTPUT_DIRECTORY` defines the output directory.
    - ``NORTL_VCAP_TEST_NAME` defines the test name.

    Note that ``NORTL_VCAP_OUTPUT_DIRECTORY` and ``NORTL_VCAP_TEST_NAME` must be defined, even if value capture is disabled.

## Synthesis Guards

When rendering a noRTL engine with value capture calls, the Verilog file will include non-synthesizable code.

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
