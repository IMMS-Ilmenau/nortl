module nortl_count_down_timer #(
    parameter DATA_WIDTH = 16
) (
    input  logic CLK_I,
    input  logic RST_ASYNC_I,

    input  logic RELOAD,
    input  logic [DATA_WIDTH-1:0] DELAY,
    output logic ZERO,

    output logic CLK_REQ
);

logic [DATA_WIDTH-1:0] counter;

always_ff @(posedge CLK_I or posedge RST_ASYNC_I)
begin
    if (RST_ASYNC_I)
    begin
        counter <= 0;
    end
    else begin
        if (RELOAD)
        begin
            if (DELAY > 2)
            begin
                counter <= DELAY - 2;
            end
        end
        else if (counter != 0) begin
            counter <= counter - 1;
        end
    end
end

always_comb begin
    ZERO = (counter == 0) & ~RELOAD;

    if (DELAY == 1)
    begin
        ZERO = ~RELOAD;
    end
    if (DELAY == 0)
    begin
        ZERO = ~RELOAD;
    end
end

always_comb begin
    CLK_REQ = RELOAD | (counter > 0);
end

endmodule
