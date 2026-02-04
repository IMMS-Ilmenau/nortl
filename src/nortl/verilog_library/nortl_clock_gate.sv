module nortl_clock_gate (
    input logic CLK_I,
    input logic EN,
    output logic GCLK_O
);

logic enable_latch;

always_latch begin
    if (~CLK_I)
    begin
        enable_latch = EN;
    end
end

always_comb begin
    GCLK_O = enable_latch & CLK_I;
end

endmodule
