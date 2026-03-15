module TopModule (
    input clk,
    input d,
    output q
);
    reg q_reg;
    assign q = q_reg;
    always @(posedge clk) begin
        q_reg <= d;
    end
endmodule