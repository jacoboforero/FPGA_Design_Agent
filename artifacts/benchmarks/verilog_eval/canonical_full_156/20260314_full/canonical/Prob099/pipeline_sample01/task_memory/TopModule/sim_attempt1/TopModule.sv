module TopModule (
    input  [5:0] y,
    input        w,
    output       Y1,
    output       Y3
);

// State encoding (one-hot):
// y[0] = A
// y[1] = B
// y[2] = C
// y[3] = D
// y[4] = E
// y[5] = F

// Next-state wire for Y1 (next value for y[1], i.e., state B):
// From state A, go to B if w==0: y[0] & ~w
// No other transitions into B
assign Y1 = y[0] & ~w;

// Next-state wire for Y3 (next value for y[3], i.e., state D):
// From state B, go to D if w==1: y[1] & w
// From state C, go to D if w==1: y[2] & w
// From state E, go to D if w==1: y[4] & w
// From state F, go to D if w==1: y[5] & w
assign Y3 = (y[1] & w) | (y[2] & w) | (y[4] & w) | (y[5] & w);

endmodule