module TopModule (
    input clk,
    input x,
    output reg z
);

    reg ff_xor;
    reg ff_and;
    reg ff_or;

    wire xor_in;
    wire and_in;
    wire or_in;

    // Combinational wire for D inputs
    assign xor_in = x ^ ff_xor;
    assign and_in = x & ~ff_and;
    assign or_in  = x | ~ff_or;

    // Sequential wire for D flip-flops
    always @(posedge clk) begin
        ff_xor <= xor_in;
        ff_and <= and_in;
        ff_or  <= or_in;
    end

    // Output wire: 3-input NOR of flip-flop outputs
    always @(*) begin
        z = ~(ff_xor | ff_and | ff_or);
    end

endmodule