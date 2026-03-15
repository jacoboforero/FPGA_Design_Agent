module TopModule (
    input  [3:0] x,
    output       f
);
// Correct mapping: columns = x[1:0], rows = x[3:2] (per prompt: x[0]x[1] col, x[2]x[3] row)
wire [1:0] col = {x[1], x[0]};
wire [1:0] row = {x[3], x[2]};
reg f_reg;
always @(*) begin
    case (row)
        2'b00: begin
            case (col)
                2'b00: f_reg = 1'b1;
                2'b01: f_reg = 1'b0;
                2'b11: f_reg = 1'b0;
                2'b10: f_reg = 1'b1;
                default: f_reg = 1'b0;
            endcase
        end
        2'b01: begin
            case (col)
                2'b00: f_reg = 1'b0;
                2'b01: f_reg = 1'b0;
                2'b11: f_reg = 1'b0;
                2'b10: f_reg = 1'b0;
                default: f_reg = 1'b0;
            endcase
        end
        2'b11: begin
            case (col)
                2'b00: f_reg = 1'b1;
                2'b01: f_reg = 1'b1;
                2'b11: f_reg = 1'b1;
                2'b10: f_reg = 1'b0;
                default: f_reg = 1'b0;
            endcase
        end
        2'b10: begin
            case (col)
                2'b00: f_reg = 1'b1;
                2'b01: f_reg = 1'b1;
                2'b11: f_reg = 1'b0;
                2'b10: f_reg = 1'b1;
                default: f_reg = 1'b0;
            endcase
        end
        default: f_reg = 1'b0;
    endcase
end
assign f = f_reg;
endmodule