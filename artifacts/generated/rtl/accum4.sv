module accum4 (
    input clk,
    input rst_n,
    input en,
    input [3:0] in_data,
    output reg [3:0] accum
);

always @(posedge clk or negedge rst_n) begin
    if (!rst_n)
        accum <= 4'b0;
    else if (en)
        accum <= in_data;
end

endmodule