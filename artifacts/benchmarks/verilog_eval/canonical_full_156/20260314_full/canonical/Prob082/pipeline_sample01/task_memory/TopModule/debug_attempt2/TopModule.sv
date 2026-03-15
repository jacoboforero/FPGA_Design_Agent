module TopModule (
    input clk,
    input reset,
    output reg [31:0] q
);

    always @(posedge clk) begin
        if (reset) begin
            q <= 32'h1;
        end else begin
            reg [31:0] next_q;
            next_q = q;
            next_q = {q[30:0], 1'b0};
            if (q[0]) begin
                next_q[31] = next_q[31] ^ 1'b1; // tap at 32
                next_q[21] = next_q[21] ^ 1'b1; // tap at 22
                next_q[1]  = next_q[1]  ^ 1'b1; // tap at 2
                next_q[0]  = next_q[0]  ^ 1'b1; // tap at 1
            end
            q <= next_q;
        end
    end

endmodule