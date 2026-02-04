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
logic [7:0] OUT;

my_engine DUT(
    .RST_ASYNC_I(RST),
    .CLK_I(CLK),
    .IN(IN),
    .OUT(OUT)
);

initial begin
    $dumpfile("out.vcd");
    $dumpvars(5);

    RST = 1;
    IN = 0;
    #(100);
    RST = 0;
    repeat (11)
    begin
        #(1000);
        IN = ~IN;
    end
    #(1000);
    $finish();
end

always @(OUT)
begin
    $display("OUT=%d", OUT);
end



endmodule
