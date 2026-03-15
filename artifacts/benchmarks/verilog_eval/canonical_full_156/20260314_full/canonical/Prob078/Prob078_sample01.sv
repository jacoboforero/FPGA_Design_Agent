module TopModule (
    input clk,
    input d,
    output reg q
);

reg q_pos;
reg q_neg;

// Sample d on rising edge
always @(posedge clk) begin
    q_pos <= d;
end

// Sample d on falling edge
always @(negedge clk) begin
    q_neg <= d;
end

// Output the correct sampled value based on clk level
always @(*) begin
    if (clk)
        q = q_pos;
    else
        q = q_neg;
end

endmodule