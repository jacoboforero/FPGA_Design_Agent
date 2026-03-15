module TopModule (
    input clk,
    input a,
    input b,
    output reg q,
    output reg state
);

reg next_state;

always @(*) begin
    // Next state wire
    // next_state = (a ^ b) ^ state;
    next_state = (a ^ b) ^ state;
end

always @(posedge clk) begin
    state <= next_state;
    q <= next_state;
end

endmodule