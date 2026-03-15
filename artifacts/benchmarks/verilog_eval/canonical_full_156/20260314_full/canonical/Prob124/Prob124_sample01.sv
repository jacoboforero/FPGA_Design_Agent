module TopModule (
    input clk,
    input load,
    input [511:0] data,
    output reg [511:0] q
);

    integer i;
    reg [511:0] next_q;
    reg left, center, right;

    always @* begin
        // Compute next_q based on Rule 110
        for (i = 0; i < 512; i = i + 1) begin
            // Get neighbors
            if (i < 511) left = q[i+1]; else left = 1'b0;
            center = q[i];
            if (i > 0) right = q[i-1]; else right = 1'b0;

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