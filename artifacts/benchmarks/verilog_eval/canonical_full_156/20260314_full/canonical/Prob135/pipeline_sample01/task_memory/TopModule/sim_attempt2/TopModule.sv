module TopModule (
    input  [2:0] y,
    input        w,
    output reg   Y1
);

    // Next-state wire for y[1]
    wire y1_next;

    assign y1_next =
        // State A: y=000
        (~y[2] & ~y[1] & ~y[0]) ? 1'b0 :
        // State B: y=001
        (~y[2] & ~y[1] &  y[0]) ? (w ? 1'b1 : 1'b0) :
        // State C: y=010
        (~y[2] &  y[1] & ~y[0]) ? (w ? 1'b1 : 1'b1) :
        // State D: y=011
        (~y[2] &  y[1] &  y[0]) ? (w ? 1'b0 : 1'b1) :
        // State E: y=100
        ( y[2] & ~y[1] & ~y[0]) ? (w ? 1'b1 : 1'b0) :
        // State F: y=101
        ( y[2] & ~y[1] &  y[0]) ? (w ? 1'b1 : 1'b1) :
        1'b0;

    // Output wire
    always @(*) begin
        Y1 = y1_next;
    end

endmodule