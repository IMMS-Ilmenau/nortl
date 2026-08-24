# Value Capture Module

To emit value capture records and create the value capture files, noRTL requires a **value capture module** to be present in the testbench.

noRTL comes with a default implementation inside the [simulation modules][nortl.verilog_library.sim].
It's usage and requirements are described in the [value capture setup guide](setup.md#simulation-requirements).

You may replace it by your own implementation or customize parts of it, e.g. to customize the output directory.
If you customize or replace the value capture module, please implement the Verilog function listed below.

## Capture

The function `capture` must write a value capture record to the output.

```verilog
function automatic void capture(string key, string value);
```

Arguments:

- `key`: The capture key. It is used as the JSON field name of the record.
- `value`: The captured value as a **verbatim JSON fragment** (e.g. `12`, `"text"`, `[1, 2, 3]`). The value is inserted into the record without any further processing, so the caller is responsible for proper JSON formatting, e.g. via `$sformatf()`.

The record must be written as a JSONL line of the form:

```json
{"type": "value", "test": "<test name>", "<key>": <value>}
```

## Value Capture Files

The default value capture module writes all records to a single file named `values.values.jsonl` in the configured output directory.

Each line is a self-contained JSON object with the following properties:

| Property | Description |
|----------|-------------|
| `type`   | Always `"value"`, to distinguish value capture records from other record types. |
| `test`   | The name of the testbench, as configured via `NORTL_VCAP_TEST_NAME` or `$NORTL_VCAP_TEST_NAME`. |
| `<key>`  | The captured value(s), as a JSON list. The field name is the key passed to `engine.capture()`. |

Example file content:

```json
{"type": "value", "test": "pytest", "count": [1]}
{"type": "value", "test": "pytest", "pair": [1, 42]}
{"type": "value", "test": "pytest", "count": [2]}
{"type": "value", "test": "pytest", "pair": [2, 42]}
```

When parsed by the [noRTL test wrapper](../../tutorial/06_pytest.md), the `type` and `test` properties are removed, and the remaining records are passed to `callback_after_simulation()` as a list of dicts, one dict per `engine.capture()` call, in emission order.
