module TopModule (
    input clk,
    input a,
    input b,
    output reg q,
    output reg state
);

reg next_state;

// Explicitly initialize state and q to 0 at simulation start
initial begin
    state = 0;
    q = 0;
end

always @(*) begin
    next_state = (a ^ b) ^ state;
end

always @(posedge clk) begin
    state <= next_state;
    q <= next_state;
end

endmodule