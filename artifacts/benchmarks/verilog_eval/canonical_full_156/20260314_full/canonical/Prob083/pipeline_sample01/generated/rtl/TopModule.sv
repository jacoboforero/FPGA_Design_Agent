module TopModule (
    input wire x,
    input wire y,
    output wire z
);

assign z = (x == 0 && y == 0) ? 1'b1 :
           (x == 1 && y == 1) ? 1'b1 :
           1'b0;

endmodule