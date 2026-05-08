# Debugging Features

When developing hardware descriptions, being able to observe the internal state of your design during simulation is invaluable. noRTL provides two built-in debugging mechanisms that seamlessly integrate with Verilog simulation frameworks. The idea of these features is that you can debug your circuit without necessarily looking at waveforms

## `engine.print()` - Console Output

The `engine.print()` method allows you to emit diagnostic messages to the console during simulation. These messages are rendered as Verilog `$display` statements and will appear in your simulation output when running with any Verilog simulator (e.g., Icarus Verilog, Verilator, or commercial tools).

```python
engine.print("Button pressed! State: %d", state)
engine.print("Counter value: %d", counter)
```

### How It Works

When you call `engine.print(line, *args)`, noRTL stores the format string and arguments in the current state. During Verilog generation, these are translated into `$display` system tasks placed inside an `always_ff` block. This means the print statement executes on every clock cycle while the state machine is in that state.

```verilog
// Generated Verilog (simplified)
always_ff @(posedge CLK_I or posedge RST_ASYNC_I) begin
    // ... other logic ...
    if (state == PROCESSING) begin
        $display("Button pressed! State: %d", state);
        $display("Counter value: %d", counter);
    end
end
```

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

**Simulation-only:** These print statements are synthesized into Verilog but are typically ignored by synthesis tools. They are meant for simulation and debugging only — they do not affect the final hardware.

## `engine.printf()` - File Output

For more detailed or large-volume debugging data, `engine.printf()` writes output to a file during simulation. This is useful when you need to log many values, export data for analysis, or avoid cluttering the console.

```python
engine.printf("log.txt", "Time: %d, Value: %d", time, value)
```

### Multiple Log Files

You can use `engine.printf()` with different filenames to create separate log files:

```python
engine.printf("errors.txt", "Error detected at state %d", state)
engine.printf("metrics.txt", "Metric: %d", metric_value)
```

Each unique filename results in a separate file being created during simulation.

### Important Notes

**File opening overhead:** Each simulation cycle that triggers a `printf` opens, writes to, and closes the file. For high-frequency logging, this can significantly impact simulation performance. Consider gating your prints with conditions to reduce overhead.

**Simulator behavior:** The exact behavior of file operations (e.g., whether files are overwritten or appended to) depends on your Verilog simulator. Check your simulator's documentation for details on file handling.

**Path handling:** The filename is passed as a string literal in Verilog. Use relative paths from your simulation working directory. Some simulators may require absolute paths or have restrictions on special characters in filenames.
