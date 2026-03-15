module TopModule (
    input  [2:0] y,
    input        w,
    output reg   Y1
);

    // Next-state wire for y[1]
    wire y1_next;

    // State encoding:
    // A: 000
    // B: 001
    // C: 010
    // D: 011
    // E: 100
    // F: 101

    // Next-state logic for y[1] based on FSM transitions
    assign y1_next =
        // State A: 000
        (~y[2] & ~y[1] & ~y[0]) ? ((w == 1'b0) ? 1'b0 : 1'b0) :
        // State B: 001
        (~y[2] & ~y[1] &  y[0]) ? ((w == 1'b0) ? 1'b1 : 1'b0) :
        // State C: 010
        (~y[2] &  y[1] & ~y[0]) ? ((w == 1'b0) ? 1'b1 : 1'b1) :
        // State D: 011
        (~y[2] &  y[1] &  y[0]) ? ((w == 1'b0) ? 1'b0 : 1'b0) :
        // State E: 100
        ( y[2] & ~y[1] & ~y[0]) ? ((w == 1'b0) ? 1'b1 : 1'b0) :
        // State F: 101
        ( y[2] & ~y[1] &  y[0]) ? ((w == 1'b0) ? 1'b0 : 1'b0) :
        1'b0;

    always @(*) begin
        Y1 = y1_next;
    end

endmodule