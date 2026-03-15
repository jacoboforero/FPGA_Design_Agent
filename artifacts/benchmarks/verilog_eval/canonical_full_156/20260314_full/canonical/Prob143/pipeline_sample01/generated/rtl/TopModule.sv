module TopModule (
    input  wire        in,
    input  wire [9:0]  state,
    output wire [9:0]  next_state,
    output wire        out1,
    output wire        out2
);

// Next state wire
assign next_state[0] = 
    // S0: (in==0) -> S0, (in==1) -> S1
    (state[0] & ~in) |
    // S1: (in==0) -> S0, (in==1) -> S2
    (state[1] & ~in) |
    // S2: (in==0) -> S0, (in==1) -> S3
    (state[2] & ~in) |
    // S3: (in==0) -> S0, (in==1) -> S4
    (state[3] & ~in) |
    // S4: (in==0) -> S0, (in==1) -> S5
    (state[4] & ~in) |
    // S7: (in==0) -> S0, (in==1) -> S7
    (state[7] & ~in) |
    // S8: (in==0) -> S0, (in==1) -> S1
    (state[8] & ~in) |
    // S9: (in==0) -> S0, (in==1) -> S1
    (state[9] & ~in);

assign next_state[1] =
    // S0: (in==1) -> S1
    (state[0] & in) |
    // S8: (in==1) -> S1
    (state[8] & in) |
    // S9: (in==1) -> S1
    (state[9] & in);

assign next_state[2] =
    // S1: (in==1) -> S2
    (state[1] & in);

assign next_state[3] =
    // S2: (in==1) -> S3
    (state[2] & in);

assign next_state[4] =
    // S3: (in==1) -> S4
    (state[3] & in);

assign next_state[5] =
    // S4: (in==1) -> S5
    (state[4] & in);

assign next_state[6] =
    // S5: (in==1) -> S6
    (state[5] & in);

assign next_state[7] =
    // S6: (in==1) -> S7
    (state[6] & in) |
    // S7: (in==1) -> S7
    (state[7] & in);

assign next_state[8] =
    // S5: (in==0) -> S8
    (state[5] & ~in);

assign next_state[9] =
    // S6: (in==0) -> S9
    (state[6] & ~in);

// Output wire
assign out1 =
    // S8: (1,0)
    state[8] |
    // S9: (1,1)
    state[9];

assign out2 =
    // S7: (0,1)
    state[7] |
    // S9: (1,1)
    state[9];

endmodule