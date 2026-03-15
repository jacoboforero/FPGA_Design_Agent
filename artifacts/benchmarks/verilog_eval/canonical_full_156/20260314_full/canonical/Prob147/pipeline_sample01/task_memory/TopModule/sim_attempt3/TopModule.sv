module TopModule (
    input clk,
    input a,
    input b,
    output reg q,
    output reg state
);

// Explicitly initialize state and q to 0 at simulation start
initial begin
    state = 0;
    q = 0;
end

always @(posedge clk) begin
    if (a == 0 && b == 0)
        state <= ~state;
    else
        state <= state;
    q <= state ^ b;
end

endmodule