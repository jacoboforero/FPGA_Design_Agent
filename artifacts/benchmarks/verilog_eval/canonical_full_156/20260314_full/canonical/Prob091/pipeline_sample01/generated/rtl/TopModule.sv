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

// Y1: input to state flip-flop y[1] (B)
// From FSM:
// - A --1--> B: y[0] & w
// So, Y1 = y[0] & w

assign Y1 = y[0] & w;

// Y3: input to state flip-flop y[3] (D)
// From FSM:
// - B --0--> D: y[1] & ~w
// - C --0--> D: y[2] & ~w
// - E --0--> D: y[4] & ~w
// - F --0--> D: y[5] & ~w
// So, Y3 = (y[1] | y[2] | y[4] | y[5]) & ~w

assign Y3 = (y[1] | y[2] | y[4] | y[5]) & ~w;

endmodule