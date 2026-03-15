module TopModule (
    input  [7:0] a,
    input  [7:0] b,
    output [7:0] s,
    output       overflow
);

wire [7:0] sum;
assign sum = a + b;
assign s = sum;

// Overflow detection for 2's complement addition:
// Overflow occurs if the sign of a and b are the same, but the sign of the result differs.
assign overflow = (~a[7] & ~b[7] & sum[7]) | (a[7] & b[7] & ~sum[7]);

endmodule