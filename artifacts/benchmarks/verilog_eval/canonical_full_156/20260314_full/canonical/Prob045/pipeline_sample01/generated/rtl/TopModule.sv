module TopModule (
    input clk,
    input [7:0] in,
    output reg [7:0] anyedge
);

reg [7:0] in_d;

always @(posedge clk) begin
    anyedge <= in ^ in_d;
    in_d <= in;
end

endmodule