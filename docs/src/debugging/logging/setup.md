# Setup

noRTL allows emiting diagnostic messages to the console during simulation.

The print statements either trigger when a certain state is reached or optionally, only when a certain condition is met in the state. The messages support "lazy" string replacement in Verilog.

## Adding prints

Print messages are added with [`Engine.print()`][nortl.core.engine.CoreEngine.print] or [`Engine.print_if()`][nortl.core.engine.CoreEngine.print_if].

=== "Unconditional Prints"

    Unconditional prints can be created with `engine.print()`.
    They are triggered for every clock cycle, where a state is reached.

    ```python hl_lines="9 12"
    from nortl import Const, Engine

    # Create engine
    engine = Engine("coffee_maker")
    start = engine.define_input("start")
    # ... define other signals

    engine.wait_for(start)
    engine.print("Starting to brew coffee!")
    # ... make coffee

    engine.print("Finished brewing coffee")
    engine.jump_if(Const(True), engine.reset_state)
    ```

=== "Conditional Prints"

    Conditional prints are only triggered, when their condition is reached.
    They are still bound to a specific state.

    ```python hl_lines="10 11 12 13 14"
    from nortl import Engine

    # Create engine
    engine = Engine("coffee_maker")
    start = engine.define_input("start")
    cup_size = engine.define_input("cup_size", width=2)
    # ... define other signals

    engine.wait_for(start)
    engine.print_if(
        cup_size > 2,
        "Received invalid cup size %0d, clipping to 2 to avoid overflow.",
        cup_size,  # (1)!
        level="warning"
    )
    ```

    1. For a more helpful message, the actual value of the `cup_size` will be inserted into the `%0d` format specifier.

### Print levels

The default logger provided with noRTL supports three print levels, `"info`, `"warning"` and `"error"`. They can be provided with the `level` keyword argument.

If no level is provided, the logger defaults to `"info"` level.

```python
engine.print("Hello world", level="info")
engine.print("Warning!", level="warning")
engine.print("Check engine!", level="error")
```

### String replacement

The print method supports string replacement, to insert the value of noRTL signals into the message.

The format string uses standard **Verilog `%`** placeholders. Some examples are shown in the table below:

| Format | Description               |
|--------|---------------------------|
| `%d`   | Signed decimal integer    |
| `%h`   | Hexadecimal               |
| `%b`   | Binary                    |
| `%s`   | String (for literal text) |

The number format specifiers can be prepended with a 0, e.g. `%0d` to remove padding.

The values for string replacement must be provided as positional arguments, following the message.

You can mix literal text with format specifiers:

```python
engine.print("Processing state %d, counter = %d", state, counter)
```

## Simulation Requirements

If a noRTL engine contains print statements, you need to provide a [logger](logger.md) for the testbench.

### noRTL Test Wrapper

When using the [noRTL test wrapper](../../tutorial/06_pytest.md), the logger is already included in the simulation environment.

### Custom Simulator

The logger must be available as a **toplevel instance** named `logger`, to allow all noRTL engines to reach it.
For example, the noRTL engine will call a function `logger.info(...)`.

Depending on your simulator, you may need to explicitely set the logger as a second toplevel, next to the testbench.
For example, with Xcelium use `xrun -top <testbench_name> -top logger ...`.

???+ info "Changing the Instance Name"

    It is possible to override the instance name of the logger through a class attribute on the [Logger][nortl.renderer.verilog_utils.print_handlers.Logger].

    This must be done before rendering the engine to Verilog.

    ```python hl_lines="6"
    from nortl.renderer.verilog_utils.print_handlers import Logger

    # ...

    # Change name from 'logger' to 'nortl_logger'
    Logger.INSTANCE_NAME = 'nortl_logger'

    # Render the engine
    renderer = VerilogRenderer(engine)
    Path("my_engine.sv").write_text(renderer.render())
    ```

## Synthesis Guards

When rendering a noRTL engine with print statements, the Verilog file will include non-synthesizable code.

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
