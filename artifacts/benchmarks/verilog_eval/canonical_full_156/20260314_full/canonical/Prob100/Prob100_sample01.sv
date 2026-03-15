module TopModule (
    input  wire        in,
    input  wire [1:0]  state,
    output wire [1:0]  next_state,
    output wire        out
);

    // State encoding
    // A = 2'b00
    // B = 2'b01
    // C = 2'b10
    // D = 2'b11

    // Next state wire
    assign next_state =
        (state == 2'b00) ? (in ? 2'b01 : 2'b00) : // A: in=0->A, in=1->B
        (state == 2'b01) ? (in ? 2'b01 : 2'b10) : // B: in=0->C, in=1->B
        (state == 2'b10) ? (in ? 2'b11 : 2'b00) : // C: in=0->A, in=1->D
        (state == 2'b11) ? (in ? 2'b01 : 2'b10) : // D: in=0->C, in=1->B
        2'b00;

    // Output wire (Moore: output depends only on state)
    assign out = (state == 2'b11) ? 1'b1 : 1'b0;

endmodule