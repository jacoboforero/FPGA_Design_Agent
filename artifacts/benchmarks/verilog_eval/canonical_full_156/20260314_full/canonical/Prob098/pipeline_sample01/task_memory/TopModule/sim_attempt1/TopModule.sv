module TopModule (
    input clk,
    input a,
    output reg q
);

    reg state;

    always @(posedge clk) begin
        if (a == 0)
            state <= 1'b1;
        else
            state <= 1'b0;
        q <= state;
    end

endmodule