// noRTL logger
module logger;

function void info (string message);
    $display("[INFO] %s", message);
endfunction

function void warning (string message);
    $display("[WARNING] %s", message);
endfunction

function void error (string message);
    $display("[ERROR] %s", message);
endfunction

endmodule
