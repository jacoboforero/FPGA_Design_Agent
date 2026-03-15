module TopModule (
    input clk,
    input load,
    input [1:0] ena,
    input [99:0] data,
    output reg [99:0] q
);

always @(posedge clk) begin
    if (load) begin
        q <= data;
    end else begin
        case (ena)
            2'b01: begin // Rotate right by 1
                q <= {q[0], q[99:1]};
            end
            2'b10: begin // Rotate left by 1
                q <= {q[98:0], q[99]};
            end
            default: begin // Hold value
                // No assignment needed; retain q
            end
        endcase
    end
end

endmodule