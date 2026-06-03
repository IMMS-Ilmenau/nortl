# Logger

To print messages through the `engine.print()` method, noRTL requires a **logger** to be present in the testbech.

noRTL comes with a default implementation inside the [simulation modules][nortl.verilog_library.sim].
It's usage and requirements are described in the [logging setup guide](setup.md#simulation-requirements).

You may replace it by your own implementation or customize parts of it, e.g. to add additional levels, route outputs to a file, or more.
If you customize or replace the logger, please implement the Verilog functions listed below.

!!! info "Logging Levels"

    The minimum feature set includes the 3 logging levels `info`, `warning` and `error`.
    The print handler will also forward additional levels and translate them to calls of the corresponding Verilog functions.

### Print Info

```verilog
function void info (string message);
```

### Print Warning

```verilog
function void warning (string message);
```

### Print Error

```verilog
function void error (string message);
```
