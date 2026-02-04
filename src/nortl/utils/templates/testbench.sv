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

logic finish, passed, timeout;

my_engine DUT(
    .RST_ASYNC_I(RST),
    .CLK_I(CLK),
    .timeout(timeout),
    .passed(passed),
    .finish(finish)
);

initial begin
    RST = 1;
    #(100);
    RST = 0;

    @(posedge finish);

    // variable dump section

    $display("timeout=%d;\n", timeout);
    $display("errors=%d;\n", DUT.error_ctr);
    $display("passed=%d;\n", passed);

    $finish();
end


endmodule
