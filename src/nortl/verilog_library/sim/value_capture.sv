// noRTL Value Capture

/**
 * The value capture module can be configured with the following define macros:
 * NORTL_INTEGRATED_TEST:       If this define is set, will read the output directory from `NORTL_VCAP_OUTPUT_DIRECTORY
 *                              and the test name from `NORTL_VCAP_TEST_NAME.
 *                              If the define is unset, will instead check the environment variables:
 *                              - $NORTL_VCAP to check if value capture should be enabled.
 *                              - $NORTL_VCAP_OUTPUT_DIRECTORY or $TB_OUTDIR for the output directory.
 *                              - $NORTL_VCAP_TEST_NAME or $TEST_NAME for the test name.
 *                              The first non-empty environment variable of each pair is used. This requires SystemVerilog DPI-C.
 *
 * NORTL_VCAP:                   Enables value capture emission. Only used if `NORTL_INTEGRATED_TEST is set.
 * NORTL_VCAP_OUTPUT_DIRECTORY:  Output directory for value capture files. Only used, if `NORTL_INTEGRATED_TEST is set.
 * NORTL_VCAP_TEST_NAME:         Test name, saved in the value capture files. Only used if `NORTL_INTEGRATED_TEST is set.
 *
 * Values are emitted as JSONL records of the form:
 * {"type": "value", "test": "<test name>", "<key>": <value>}
 *
 * The value is inserted verbatim and must already be a properly formatted JSON
 * fragment (e.g. 12, "text", [1, 2, 3]). Callers are responsible for formatting,
 * e.g. via $sformatf().
 *
 * Icarus Verilog compatibility:
 * - The environment variable branch requires DPI-C and unpacked array localparams, which Icarus does not support.
 *   Use `NORTL_INTEGRATED_TEST mode (define-based configuration) when simulating with Icarus.
 */
module value_capture;

string output_dir = "";
string test_name = "";
string enabled = "";

/**
* Resolution of environment variables
*/
`ifdef NORTL_INTEGRATED_TEST
    // Retrieve variables from defines

    localparam string ENABLED_KEY = `ifdef NORTL_VCAP "true" `else "false" `endif;
    localparam string OUTPUT_DIRECTORY_KEY = `NORTL_VCAP_OUTPUT_DIRECTORY;
    localparam string TEST_NAME_KEY = `NORTL_VCAP_TEST_NAME;

    function automatic string resolve_var(string key, string name, logic boolean = 1'b0);
        return key;
    endfunction
`else
    // Retrieve variables from environment

    // Potential environment variables to enable value capture.
    localparam string ENABLED_KEY [] = {"NORTL_VCAP"};

    // List of environment variables for output directory.
    localparam string OUTPUT_DIRECTORY_KEY [] = {"NORTL_VCAP_OUTPUT_DIRECTORY", "TB_OUTDIR"};

    // Potential environment variables for test name.
    localparam string TEST_NAME_KEY [] = {"NORTL_VCAP_TEST_NAME", "TEST_NAME"};

    import "DPI-C" function string getenv(input string env_name);

    function automatic string resolve_var(string keys [], string name, logic boolean = 1'b0);
        string value;

        foreach (keys[index]) begin
            value = getenv(keys[index]);

            if (value != "") begin
                if (boolean) begin
                    return "true";
                end
                else begin
                    return value;
                end
            end
        end

        if (boolean) begin
            return "false";
        end

        $fatal(1, "Failed to resolve %s! The following environment variables were tested: %s. Please set one of them or disable the collection of noRTL value capture information.", name, join_strings(keys, ", "));
    endfunction
`endif

/**
 * Resolve path of output file
 */
function automatic string resolve_output_file(string target);
    string path;

    if (output_dir == "") begin
        output_dir = resolve_var(OUTPUT_DIRECTORY_KEY, "output directory");
    end

    path = output_dir;
    if ((output_dir != "") & (output_dir[-1] != "/")) begin
        path = {path, "/"};
    end

    return {path, target, ".values.jsonl"};
endfunction

/**
 * Capture a value
 *
 * Emits a single JSONL record of the form:
 * {"type": "value", "test": "<test name>", "<key>": <value>}
 *
 * The value is inserted verbatim and must already be a properly formatted JSON
 * fragment (e.g. 12, "text", [1, 2, 3]). Callers are responsible for formatting,
 * e.g. via $sformatf().
 */
function automatic void capture(string key, string value);
    string record;

    if (enabled == "") begin
        enabled = resolve_var(ENABLED_KEY, "enabled", 1'b1);
    end

    if (enabled == "true") begin
        if (test_name == "") begin
            test_name = resolve_var(TEST_NAME_KEY, "test name");
        end

        record = $sformatf("{\"type\": \"value\", \"test\": %s, %s: %s}", to_string(test_name), to_string(key), value);

        write_record(record);
    end
endfunction

/**
 * Write value capture record to target
 */
function automatic void write_record(string record);
    int fd;

    fd = $fopen(resolve_output_file("values"), "a");
    $fdisplay(fd, record);
    $fclose(fd);
endfunction

/**
* Verilog to JSON serialization
*/

// Convert Verilog string to JSON string
// If nullable is high, empty strings are converted to null
function automatic string to_string(string value, logic nullable = 1'b0);
    string result;

    if ((value.len() == 0) && nullable) begin
        result = "null";
    end
    else begin
        result = $sformatf("\"%s\"", value);
    end

    return result;
endfunction

// Join multiple strings
function automatic string join_strings(string values [], string separator = "");
    string result;

    result = "";
    foreach (values[index]) begin
        if (index < values.size() - 1) begin
            result = {result, values[index], separator};
        end
        else begin
            result = {result, values[index]};
        end
    end
    return result;
endfunction

endmodule
