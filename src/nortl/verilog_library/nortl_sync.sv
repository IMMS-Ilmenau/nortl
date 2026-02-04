module nortl_sync #(
    parameter DATA_WIDTH = 1
) (
    input  logic CLK_I,
    input  logic RST_ASYNC_I,

    input  logic [DATA_WIDTH-1:0] IN,
    output logic [DATA_WIDTH-1:0] OUT,

    output logic CLK_REQ
);

always @(posedge CLK_I or posedge RST_ASYNC_I)
begin
    if (RST_ASYNC_I)
    begin
        OUT <= {DATA_WIDTH{1'b0}};
    end
    else begin
        OUT <= IN;
    end
end

always_comb begin
    CLK_REQ = OUT != IN;
end

endmodule
