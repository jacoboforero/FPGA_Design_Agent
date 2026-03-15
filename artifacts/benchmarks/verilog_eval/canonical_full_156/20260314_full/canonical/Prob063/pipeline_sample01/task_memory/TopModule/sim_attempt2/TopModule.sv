module TopModule (
    input clk,
    input shift_ena,
    input count_ena,
    input data,
    output reg [3:0] q
);

initial q = 4'b0000;

always @(posedge clk) begin
    if (shift_ena) begin
        // Shift in data at MSB, shift right
        q <= {data, q[3:1]};
    end else if (count_ena) begin
        // Decrement the value in the shift register
        q <= q - 4'd1;
    end
    // If both shift_ena and count_ena are 0, retain value (no assignment)
    // If both are 1, shift_ena has priority (matches reference model typical behavior)
end

endmodule