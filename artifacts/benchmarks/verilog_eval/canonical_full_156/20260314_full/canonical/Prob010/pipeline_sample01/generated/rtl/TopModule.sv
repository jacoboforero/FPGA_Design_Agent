module TopModule (
    input  wire x,
    input  wire y,
    output wire z
);

assign z = (x ^ y) & x;

endmodule