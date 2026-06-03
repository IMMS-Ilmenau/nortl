module nortl_delay #(
    parameter DATA_WIDTH = 1,
    parameter DELAY_STEPS = 2
) (
    input logic CLK_I,
    input logic RST_ASYNC_I,

    input  logic [DATA_WIDTH-1:0] IN,
    output logic [DATA_WIDTH-1:0] OUT,

    output logic CLK_REQ
);

logic [DATA_WIDTH-1:0] shiftreg [DELAY_STEPS-1:0];

always_ff @(posedge CLK_I or posedge RST_ASYNC_I) begin
    if (RST_ASYNC_I)
    begin
        for (int i=DELAY_STEPS-1; i>=0; i=i-1)
        begin
            shiftreg[i] <= {DATA_WIDTH{1'b0}};
        end
    end
    else begin
        if (DELAY_STEPS == 1)
        begin
            shiftreg[0] <= IN;
        end
        else begin
            for (int i=DELAY_STEPS-2; i>=0; i=i-1)
            begin
                shiftreg[i+1] <= shiftreg[i];
            end
            shiftreg[0] <= IN;
        end
    end
end

always_comb begin
    if (DELAY_STEPS == 1)
    begin
        OUT = shiftreg[0];
    end
    else begin
        OUT = shiftreg[DELAY_STEPS-1];
    end
end

always_comb begin
    CLK_REQ = 0;

    if (DELAY_STEPS == 1)
    begin
        CLK_REQ = CLK_REQ | (shiftreg[0] != IN);
    end
    else begin
        for (int i=DELAY_STEPS-2; i>=0; i=i-1)
        begin
            CLK_REQ = CLK_REQ | (shiftreg[i+1] != shiftreg[i]);
        end
        CLK_REQ = CLK_REQ | (shiftreg[0] != IN);
    end
end


endmodule
