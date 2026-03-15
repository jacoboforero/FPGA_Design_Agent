module TopModule (
    input  [3:0] a,
    input  [3:0] b,
    input  [3:0] c,
    input  [3:0] d,
    input  [3:0] e,
    output [3:0] q
);

wire [3:0] f;
assign f = 4'hf;

assign q =
    (c == 4'd0) ? b :
    (c == 4'd1) ? e :
    (c == 4'd2) ? a :
    (c == 4'd3) ? d :
    f;

endmodule