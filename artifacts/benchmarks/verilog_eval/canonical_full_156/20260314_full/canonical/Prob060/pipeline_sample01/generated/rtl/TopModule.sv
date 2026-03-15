module TopModule (
    input clk,
    input resetn,
    input in,
    output reg out
);

reg [2:0] shift_reg;

always @(posedge clk) begin
    if (!resetn) begin
        shift_reg <= 3'b000;
        out <= 1'b0;
    end else begin
        out <= shift_reg[2];
        shift_reg <= {shift_reg[1:0], in};
    end
end

endmodule