module testbench();

logic CLK, RST;

initial begin
    CLK = 0;
    while(1)
    begin
        #(10);
        CLK = ~CLK;
    end
end

logic IN;
logic OUT;

my_engine DUT(
    .RST_ASYNC_I(RST),
    .CLK_I(CLK),
    .IN(IN),
    .OUT(OUT)
);


int cycle_counter;

initial begin
    $dumpfile("out.vcd");
    $dumpvars(5);

    RST = 1;
    cycle_counter = 0;
    IN = 0;
    #(100);
    RST = 0;
    #(100000);

    $display("cycles = %d", cycle_counter);
    $finish();
end

always @(posedge CLK)
begin
    if (OUT == 1)
    begin
        cycle_counter = cycle_counter + 1;
    end
end


endmodule
