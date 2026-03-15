module TopModule (
    input clk,
    input in,
    output reg out
);

    wire xor_in;

    assign xor_in = in ^ out;

    always @(posedge clk) begin
        out <= xor_in;
    end

    initial begin
        out = 0;
    end

endmodule