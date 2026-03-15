module TopModule (
    input clk,
    input load,
    input [511:0] data,
    output reg [511:0] q
);

    integer i;
    reg [511:0] next_q;

    always @* begin
        // Compute next_q based on Rule 110
        for (i = 0; i < 512; i = i + 1) begin
            // Get left, center, right bits with boundary conditions
            // left: q[i+1] if i < 511, else 0
            // center: q[i]
            // right: q[i-1] if i > 0, else 0
            // Rule 110: next = (left & ~center & ~right) | (left & ~center & right) | (~left & center & ~right) | (~left & center & right) | (~left & ~center & right)
            // But more simply, Rule 110: next = (left & ~center) | (center ^ right)
            // But to match the table, use the explicit mapping:
            // 111 -> 0
            // 110 -> 1
            // 101 -> 1
            // 100 -> 0
            // 011 -> 1
            // 010 -> 1
            // 001 -> 1
            // 000 -> 0

            // Get neighbors
            wire left   = (i < 511) ? q[i+1] : 1'b0;
            wire center = q[i];
            wire right  = (i > 0)   ? q[i-1] : 1'b0;

            case ({left, center, right})
                3'b111: next_q[i] = 1'b0;
                3'b110: next_q[i] = 1'b1;
                3'b101: next_q[i] = 1'b1;
                3'b100: next_q[i] = 1'b0;
                3'b011: next_q[i] = 1'b1;
                3'b010: next_q[i] = 1'b1;
                3'b001: next_q[i] = 1'b1;
                3'b000: next_q[i] = 1'b0;
                default: next_q[i] = 1'b0;
            endcase
        end
    end

    always @(posedge clk) begin
        if (load)
            q <= data;
        else
            q <= next_q;
    end

endmodule