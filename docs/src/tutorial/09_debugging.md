# Debugging Features

When developing hardware descriptions, being able to observe the internal state of your design during simulation is invaluable. noRTL provides two built-in debugging mechanisms that seamlessly integrate with Verilog simulation frameworks. The idea of these features is that you can debug your circuit without necessarily looking at waveforms

## `engine.print()` - Console Output

The `engine.print()` method allows you to emit diagnostic messages to the console during simulation. These messages are ultimatively rendered as Verilog `$display` statements and will appear in your simulation output when running with any Verilog simulator (e.g., Icarus Verilog, Verilator, or commercial tools).

```python
engine.print("Button pressed! State: %d", state)
engine.print("Counter value: %d", counter)
```

### How It Works

When you call `engine.print(line, *args)`, noRTL stores the format string and arguments in the current state. During Verilog generation, these are translated into calls to a [logger](../debugging/logging/logger.md) instance, placed inside an `always_ff` block.
The logger typically calls `$display` system tasks.
This means the print statement executes on every clock cycle while the state machine is in that state.

```verilog
// Generated Verilog (simplified)
// synthesis translate_off
always_ff @(posedge CLK_I or posedge RST_ASYNC_I) begin
    // ... other logic ...
    if (state == PROCESSING) begin
        logger.info($sformatf("Button pressed! State: %d", state));
        logger.info($sformatf("Counter value: %d", counter));
    end
end
// synthesis translate_on
```

Refer to the [logger](../debugging/logging/setup.md) setup guide for more details.

### Format Strings

The format string uses standard Verilog `%` placeholders, similar to C's `printf`:

| Format | Description |
|--------|-------------|
| `%d`   | Signed decimal integer |
| `%h`   | Hexadecimal |
| `%b`   | Binary |
| `%s`   | String (for literal text) |

You can mix literal text with format specifiers:

```python
engine.print("Processing state %d, counter = %d", state, counter)
```

### Common Pitfalls

**Verilog vs. Python:** Remember that `engine.print()` generates Verilog code, not Python code. The format specifiers follow Verilog conventions, not Python's f-string syntax. Also, the arguments are rendered as Verilog expressions, so you pass signal names or expressions, not their current values.

**Execution timing:** Since `$display` is inside an `always_ff` block, it executes on the clock edge, not immediately when the state is entered. If you need to print a value that changes within a state, ensure you understand the clocking behavior.

**Simulation-only:** These print statements are synthesized into Verilog but are typically ignored by synthesis tools. They are meant for simulation and debugging only — they do not affect the final hardware. By default, the print statements are wrapped in `// synthesis translate_off` guards. They can be [customized](../debugging/logging/setup.md#synthesis-guards) to match your synthesis tool.
