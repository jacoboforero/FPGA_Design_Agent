module TopModule (
    input  wire a,
    input  wire b,
    input  wire c,
    input  wire d,
    output wire out,
    output wire out_n
);

wire and1_out;
wire and2_out;

assign and1_out = a & b;
assign and2_out = c & d;
assign out      = and1_out | and2_out;
assign out_n    = ~out;

endmodule