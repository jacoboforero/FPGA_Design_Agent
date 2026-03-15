module TopModule (
    input  wire        in,
    input  wire [3:0]  state,
    output wire [3:0]  next_state,
    output wire        out
);

// One-hot state encoding
// A = 4'b0001
// B = 4'b0010
// C = 4'b0100
// D = 4'b1000

// Next state wire
assign next_state[0] = (state[0] & ~in) | (state[2] & ~in); // A: stay in A if in A and in=0, or from C if in=0
assign next_state[1] = (state[0] &  in) | (state[1] &  in) | (state[3] &  in); // B: from A, B, or D if in=1
assign next_state[2] = (state[1] & ~in) | (state[3] & ~in); // C: from B or D if in=0
assign next_state[3] = (state[2] &  in); // D: from C if in=1

// Output wire (Moore: output depends only on state)
assign out = state[3];

endmodule