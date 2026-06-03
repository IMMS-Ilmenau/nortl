# Coverage Writer

To emit coverage records and create the coverage files, noRTL requires a **coverage writer** to be present in the testbench.

noRTL comes with a default implementation inside the [simulation modules][nortl.verilog_library.sim].
It's usage and requirements are described in the [coverage setup guide](setup.md#simulation-requirements).

You may replace it by your own implementation or customize parts of it, e.g. to customize the output directory.
If you customize or replace the coverage writer, please implement the Verilog functions listed below.

## Write Raw Record

The function `write_record` must write a raw JSON record (already serialized to a Verilog string) to the output.

This low-level function is used, if the [CoverageWriter][nortl.renderer.verilog_utils.print_handlers.CoverageWriter] is set to **raw mode**.

```verilog
function automatic void write_record(string target, string record, logic clear = 1'b0);
```

Arguments:

- `target`: Coverage target identifier. Typically, this is the name of the noRTL engine. The function must separate data sent to different targets.
- `record`: The record to write as a JSON string.
- `clear`: If this bit is high, the write shall clear all previous data.
    E.g., when writing to a file, open it with `$fopen(..., "w")`, if clear is high, and `$fopen(..., "a")` if it is low.

## Emit Info Record

The function `emit_info` emits an [Info record](coverage_files.md#info-record).
The test information property is not included in the call signature. It may get added by the coverage writer.

```verilog
function automatic void emit_info(
    string coverage_target,
    string engine [string]
);
```

Arguments:

- `coverage_target`: Coverage target identifier. See description for `target` of the [`write_record` function](#write-raw-record).
- `engine`: Associative array of data for the `engine` property of the Info record. For example, the function may get called like this:

    ```verilog
    coverage_writer.emit_info("my_engine", '{
        "name": "my_engine",
        "sha256sum": "1234..."
    });
    ```

## Emit State Coverage Record

The function `emit_state_coverage` emits an [State coverage record](coverage_files.md#state-coverage).

```verilog
function automatic void emit_state_coverage(
    string coverage_target,
    string state,
    logic covered = 1'b1
);
```

Arguments:

- `coverage_target`: Coverage target identifier. See description for `target` of the [`write_record` function](#write-raw-record).
- `state`: Name of the state, e.g. `"WORKER_1_STATE_123"`.
- `covered`: Coverage value, indicates if the state was visited.

## Emit Transition Coverage Record

The function `emit_transition_coverage` emits an [Transition coverage record](coverage_files.md#transition-coverage).

```verilog
function automatic void emit_transition_coverage(
    string coverage_target,
    string source,
    string target,
    logic covered = 1'b1
);
```

Arguments:

- `coverage_target`: Coverage target identifier. See description for `target` of the [`write_record` function](#write-raw-record).
- `source`: Name of the source state.
- `target`: Name of the target state.
- `covered`: Coverage value, indicates if the transition has occured.

## Emit Cover Point Record

The function `emit_cover_point` emits an [cover point record](coverage_files.md#cover-point).

```verilog
function automatic void emit_cover_point(
    string coverage_target,
    string state,
    string condition,
    string point_name,
    string group_name = "",
    int group_coords [] = {},
    logic covered = 1'b1
);
```

Arguments:

- `coverage_target`: Coverage target identifier. See description for `target` of the [`write_record` function](#write-raw-record).
- `state`: Name of the state of the coverpoint.
- `condition`: Condition of the coverpoint, e.g. `"adr > 0"`. The condition is rendered by noRTL in Python.
- `point_name`: Name of the coverpoint.
- `group_name`: Optional name of the covergroup, to which the coverpoint belongs.
    If the string is empty, it must be set to `null` or omitted in the JSON record.
- `group_coords`: Optional array of coordinates inside the covergroup.
    If the array is empty, it must be set to `null` or ommitted in the JSON record.
- `covered`: Coverage value, indicates if the transition has occured.

## Emit Cover Group Record

The function `emit_cover_group` emits an [cover group record](coverage_files.md#cover-group).

```verilog
function automatic void emit_cover_group(
    string coverage_target,
    string name,
    string axis [],
    int limits [][]
);
```
Arguments:

- `coverage_target`: Coverage target identifier. See description for `target` of the [`write_record` function](#write-raw-record).
- `name`: Name of the covergroup.
- `axis`: Array of names for the axis of the covergroup.
- `limits`: Array of lower and upper limits for each axis of the covergroup.
    Each entry in the array is an array of length 2.
    Due to technical reasons of the SystemVerilog implementation, the inner array length must be set dynamic.
