module TopModule (
    input  wire a,
    input  wire b,
    input  wire c,
    input  wire d,
    output wire out_sop,
    output wire out_pos
);

// Inputs as a 4-bit vector for easier minterm/maxterm mapping
wire [3:0] in;
assign in = {a, b, c, d};

// Explicitly enumerate all 16 input combinations for deterministic outputs
reg sop_reg, pos_reg;
always @(*) begin
    case (in)
        4'd2:  begin sop_reg = 1'b1; pos_reg = 1'b1; end
        4'd7:  begin sop_reg = 1'b1; pos_reg = 1'b1; end
        4'd15: begin sop_reg = 1'b1; pos_reg = 1'b1; end
        default: begin sop_reg = 1'b0; pos_reg = 1'b0; end
    endcase
end

assign out_sop = sop_reg;
assign out_pos = pos_reg;

endmodule