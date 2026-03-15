module TopModule (
    input  wire in1,
    input  wire in2,
    input  wire in3,
    output wire out
);

wire xnor_out;

assign xnor_out = ~(in1 ^ in2);
assign out = xnor_out ^ in3;

endmodule