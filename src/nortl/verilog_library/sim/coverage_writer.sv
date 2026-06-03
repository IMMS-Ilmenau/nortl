// noRTL Coverage Writer

/**
 * The coverage writer can be configured with the following define macros:
 * NORTL_INTEGRATED_TEST:       If this define is set, will read the output directory from `NORTL_COV_OUTPUT_DIRECTORY
 *                              and the test name from `NORTL_COV_TEST_NAME.
 *                              If the define is unset, will instead check the environment variables:
 *                              - $NORTL_COV to check if coverage should be enabled.
 *                              - $NORTL_COV_OUTPUT_DIRECTORY or $TB_OUTDIR for the output directory.
 *                              - $NORTL_COV_TEST_NAME or $TEST_NAME for the test name.
 *                              The first non-empty environment variable of each pair is used. This requires SystemVerilog DPI-C.
 *
 * NORTL_COV:                   Enables coverage emission. Only used if `NORTL_INTEGRATED_TEST is set.
 * NORTL_COV_OUTPUT_DIRECTORY:  Output directory for coverage files. Only used, if `NORTL_INTEGRATED_TEST is set.
 * NORTL_COV_TEST_NAME:         Test name, saved in the coverage files. Only used if `NORTL_INTEGRATED_TEST is set.
 * NORTL_RAW_MODE:              If this define is set, only the function write_record() is available for emission of pre-rendered coverage records.
 *                              If this define is unset, all functions are available.
 *                              The coverage writer uses SystemVerilog features, that are not supported by all simulators, e.g. Icarus Verilog.
 *                              Using `NORTL_RAW_MODE avoids these features.
 *                              The CoverageWriter print handler in Python must be configured to raw_mode.
 */
module coverage_writer;

string output_dir = "";
string test_name = "";
string enabled = "";

/**
* Resolution of environment variables
*/
`ifdef NORTL_INTEGRATED_TEST
    // Retrieve variables from defines

    localparam string ENABLED_KEY = `ifdef NORTL_COV "true" `else "false" `endif;
    localparam string OUTPUT_DIRECTORY_KEY = `NORTL_COV_OUTPUT_DIRECTORY;
    localparam string TEST_NAME_KEY = `NORTL_COV_TEST_NAME;

    function automatic string resolve_var(string key, string name, logic boolean = 1'b0);
        return key;
    endfunction
`else
    // Retrieve variables from environment

    // Potential environment variables to enabled coverage.
    localparam string ENABLED_KEY [] = {"NORTL_COV"};

    // List of environment variables for output directoy.
    localparam string OUTPUT_DIRECTORY_KEY [] = {"NORTL_COV_OUTPUT_DIRECTORY", "TB_OUTDIR"};

    // Potential environment variables for test name.
    localparam string TEST_NAME_KEY [] = {"NORTL_COV_TEST_NAME", "TEST_NAME"};

    import "DPI-C" function string getenv(input string env_name);

    function automatic string resolve_var(string keys [], string name, logic boolean = 1'b0);
        string value;

        foreach (keys[index]) begin
            value = getenv(keys[index]);

            if (value != "") begin
                return boolean ? "true" : value;
            end
        end

        if (boolean) begin
            return "false";
        end

        $fatal(1, "Failed to resolve %s! The following environment variables were tested: %s. Please set one of them or disable the collection of noRTL coverage information.", name, join_strings(keys, ", "));
    endfunction
`endif

/**
 * Resolve path of output file
 */
function automatic string resolve_output_file(string target);
    if (output_dir == "") begin
        output_dir = resolve_var(OUTPUT_DIRECTORY_KEY, "output directory");
    end

    return {output_dir, (output_dir != "") & (output_dir[-1] != "/") ? "/" : "", target, ".coverage.jsonl"};
endfunction

/**
 * Write coverage record to target
 */
function automatic void write_record(string target, string record, logic clear = 1'b0);
    int fd;

    if (enabled == "") begin
        enabled = resolve_var(ENABLED_KEY, "enabled", 1'b1);
    end

    if (enabled == "true") begin
        fd = $fopen(resolve_output_file(target), clear ? "w" : "a");
        $fdisplay(fd, record);
        $fclose(fd);
    end
endfunction

/**
* Coverage emission
*/

`ifndef NORTL_RAW_MODE
    // Icarus Verilog supports a very limited feature set of SystemVerilog.
    // Therefore, only the raw emission of coverage records via write_record() is supported.

    function automatic void emit_info(string coverage_target, string engine [string]);
        string record;

        if (test_name == "") begin
            test_name = resolve_var(TEST_NAME_KEY, "test name");
        end

        record = to_object('{
            "type": to_string("info"),
            "engine": to_object('{
                "name": to_string(engine["name"]),
                "sha256sum": to_string(engine["sha256sum"])
            }),
            "test": to_object('{
                "name": to_string(test_name),
                "start_time": to_string("...")  // TODO inject wall time
            })
        });

        write_record(coverage_target, record, 1'b1);
    endfunction

    function automatic void emit_state_coverage(string coverage_target, string state, logic covered = 1'b1);
        string record;

        record = to_object('{
            "type": to_string("state"),
            "state": to_string(state),
            "covered": to_boolean(covered)
        });

        write_record(coverage_target, record);
    endfunction

    function automatic void emit_transition_coverage(string coverage_target, string source, string target, logic covered = 1'b1);
        string record;

        record = to_object('{
            "type": to_string("transition"),
            "source": to_string(source),
            "target": to_string(target),
            "covered": to_boolean(covered)
        });

        write_record(coverage_target, record);
    endfunction

    function automatic void emit_cover_point(
        string coverage_target,
        string state,
        string condition,
        string point_name,
        string group_name = "",
        int group_coords [] = {},
        logic covered = 1'b1
    );
        string record;

        record = to_object('{
            "type": to_string("coverpoint"),
            "state": to_string(state),
            "condition": to_string(condition),
            "point_name": to_string(point_name),
            "group_name": to_string(group_name, 1'b1),
            "group_coords": to_number_array(group_coords, 1'b1),
            "covered": to_boolean(covered)
        });

        write_record(coverage_target, record);
    endfunction

    function automatic void emit_cover_group(string coverage_target, string name, string axis [], int limits [][]);
        string record;

        record = to_object('{
            "type": to_string("covergroup"),
            "name": to_string(name),
            "axis": to_string_array(axis),
            "limits": to_2d_number_array(limits)
        });

        write_record(coverage_target, record);
    endfunction

    /**
    * Verilog to JSON serialization
    */

    // Convert Verilog logic to JSON boolean
    function automatic string to_boolean(logic value);
        return value ? "true" : "false";
    endfunction

    // Convert Verilog string to JSON string
    // If nullable is high, empty strings are converted to null
    function automatic string to_string(string value, logic nullable = 1'b0);
        return (value.len() == 0) && nullable ? "null" : $sformatf("\"%s\"", value);
    endfunction

    // Convert Verilog integer to JSON number
    function automatic string to_number(int value);
        return $sformatf("%d", value);
    endfunction

    // Convert array of Verilog strings to JSON array of strings
    // If nullable is high, empty arrays are converted to null
    function automatic string to_string_array(string values [], logic nullable = 1'b0);
        string entries [];

        if ((values.size() == 0) && nullable) begin
            return "null";
        end

        entries = new [values.size()];
        foreach (values[index]) begin
            entries[index] = to_string(values[index]);
        end

        return $sformatf("[%s]", join_strings(entries, ", "));
    endfunction

    // Convert array of Verilog integers to JSON array of numbers
    // If nullable is high, empty arrays are converted to null
    function automatic string to_number_array(int values [], logic nullable = 1'b0);
        string entries [];

        if ((values.size() == 0) && nullable) begin
            return "null";
        end

        entries = new [values.size()];
        foreach (values[index]) begin
            entries[index] = to_number(values[index]);
        end

        return $sformatf("[%s]", join_strings(entries, ", "));
    endfunction

    // Convert 2D array of Verilog integers to JSON array of numbers
    // If nullable is high, empty arrays are converted to null
    function automatic string to_2d_number_array(int values [][], logic nullable = 1'b0);
    string entries [];

        if ((values.size() == 0) && nullable) begin
            return "null";
        end

        entries = new [values.size()];
        foreach (values[index]) begin
            entries[index] = to_number_array(values[index]);
        end

        return $sformatf("[%s]", join_strings(entries, ", "));
    endfunction

    // Convert associative data array to JSON object
    // If nullable is high, empty objects are converted to null
    function automatic string to_object(string data [string], logic nullable = 1'b0);
        string entries [];
        int index;

        if ((data.size() == 0) && nullable) begin
            return "null";
        end

        entries = new [data.size()];
        index = 0;
        foreach (data[key]) begin
            entries[index] = $sformatf("%s: %s", to_string(key), data[key]);
            index += 1;
        end

        return $sformatf("{%s}", join_strings(entries, ", "));
    endfunction

    // Join multiple strings
    function automatic string join_strings(string values [], string separator = "");
        string result;

        result = "";
        foreach (values[index]) begin
            result = {result, values[index], index < values.size() - 1 ? separator : ""};
        end
        return result;
    endfunction
`endif

endmodule
