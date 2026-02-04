module nortl_edge_detector(
    input  logic CLK_I,
    input  logic RST_ASYNC_I,

    input  logic SIGNAL,
    output logic RISING,
    output logic FALLING,

    output logic CLK_REQ
);

logic [1:0] sr;

always_ff @(posedge CLK_I or posedge RST_ASYNC_I)
begin
    if (RST_ASYNC_I)
    begin
        sr <= 2'b00;
    end
    else begin
        sr <= {sr[0], SIGNAL};
    end
end

always_comb begin
    RISING = (sr == 2'b01);
    FALLING = (sr == 2'b10);
end

always_comb begin
    CLK_REQ = sr != {sr[0], SIGNAL};
end

endmodule
