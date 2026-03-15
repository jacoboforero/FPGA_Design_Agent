module TopModule (
    input  d,
    input  done_counting,
    input  ack,
    input  [9:0] state,
    output B3_next,
    output S_next,
    output S1_next,
    output Count_next,
    output Wait_next,
    output done,
    output counting,
    output shift_ena
);

// State bit indices (one-hot encoding)
wire S     = state[0];
wire S1    = state[1];
wire S11   = state[2];
wire S110  = state[3];
wire B0    = state[4];
wire B1    = state[5];
wire B2    = state[6];
wire B3    = state[7];
wire Count = state[8];
wire Wait  = state[9];

// Next-state wire
assign S_next      = (S & ~d) | (S1 & ~d) | (S110 & ~d) | (Wait & ack);
assign S1_next     = (S & d);
assign S11_next    = (S1 & d) | (S11 & d);
wire S110_next     = (S11 & ~d);
wire B0_next       = (S110 & d);
wire B1_next       = B0;
wire B2_next       = B1;
assign B3_next     = B2;
assign Count_next  = B3 | (Count & ~done_counting);
assign Wait_next   = (Count & done_counting) | (Wait & ~ack);

// Output wire
assign shift_ena = B0 | B1 | B2 | B3;
assign counting  = Count;
assign done      = Wait;

endmodule