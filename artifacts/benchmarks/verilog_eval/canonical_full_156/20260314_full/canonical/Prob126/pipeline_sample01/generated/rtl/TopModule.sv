module TopModule (
    input  [2:0] a,
    output [15:0] q
);

assign q =
    (a == 3'd0) ? 16'h1232 :
    (a == 3'd1) ? 16'haee0 :
    (a == 3'd2) ? 16'h27d4 :
    (a == 3'd3) ? 16'h5a0e :
    (a == 3'd4) ? 16'h2066 :
    (a == 3'd5) ? 16'h64ce :
    (a == 3'd6) ? 16'hc526 :
    (a == 3'd7) ? 16'h2f19 :
    16'h0000;

endmodule