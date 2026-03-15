module TopModule (
    input clk,
    input reset,
    output reg [4:0] q
);

always @(posedge clk) begin
    if (reset) begin
        q <= 5'b00001;
    end else begin
        reg feedback;
        reg [4:0] next_q;
        feedback = q[0];
        next_q[0] = q[4];
        next_q[1] = q[0];
        next_q[2] = q[1];
        next_q[3] = q[2] ^ feedback;
        next_q[4] = q[3];
        q <= next_q;
    end
end

endmodule