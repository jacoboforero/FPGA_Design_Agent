module TopModule (
    input  x,
    input  y,
    output z
);

// Submodule A: z = (x ^ y) & x
wire a1_out;
wire a2_out;

assign a1_out = (x ^ y) & x;
assign a2_out = (x ^ y) & x;

// Submodule B: waveform-based combinational wire
// From the waveform, B's output is:
// - 1 if (x==0 && y==0) or (x==1 && y==1)
// - 0 otherwise

wire b1_out;
wire b2_out;

assign b1_out = (~x & ~y) | (x & y);
assign b2_out = (~x & ~y) | (x & y);

// OR and AND combinations
wire or_out;
wire and_out;

assign or_out  = a1_out | b1_out;
assign and_out = a2_out & b2_out;

// Final XOR
assign z = or_out ^ and_out;

endmodule