module TopModule (
    input clk,
    input reset,
    output reg [4:0] q
);

reg [4:0] lfsr_next;

always @(posedge clk) begin
    if (reset) begin
        q <= 5'b00001;
    end else begin
        lfsr_next[0] = q[4];
        lfsr_next[1] = q[0];
        lfsr_next[2] = q[1] ^ q[0]; // Tap at bit 3 (q[2])
        lfsr_next[3] = q[2];
        lfsr_next[4] = q[3] ^ q[0]; // Tap at bit 5 (q[4])
        q <= lfsr_next;
    end
end

endmodule