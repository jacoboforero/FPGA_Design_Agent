module TopModule (
    input  [3:0] in,
    output [3:0] out_both,
    output [3:0] out_any,
    output [3:0] out_different
);

// out_both: out_both[i] = in[i] & in[i+1] for i=0..2, out_both[3]=0
assign out_both[0] = in[0] & in[1];
assign out_both[1] = in[1] & in[2];
assign out_both[2] = in[2] & in[3];
assign out_both[3] = 1'b0;

// out_any: out_any[i] = in[i] | in[i-1] for i=1..3, out_any[0]=0
assign out_any[0] = 1'b0;
assign out_any[1] = in[1] | in[0];
assign out_any[2] = in[2] | in[1];
assign out_any[3] = in[3] | in[2];

// out_different: out_different[i] = in[i] ^ in[(i+1)%4]
assign out_different[0] = in[0] ^ in[3];
assign out_different[1] = in[1] ^ in[0];
assign out_different[2] = in[2] ^ in[1];
assign out_different[3] = in[3] ^ in[2];

endmodule