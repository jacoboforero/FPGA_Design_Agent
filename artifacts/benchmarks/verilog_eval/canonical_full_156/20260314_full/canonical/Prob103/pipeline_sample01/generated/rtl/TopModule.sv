module TopModule (
    input  wire a,
    input  wire b,
    input  wire c,
    input  wire d,
    output wire q
);

// q = odd parity of (a,b,c,d) OR all inputs zero
assign q = (a ^ b ^ c ^ d) | (~a & ~b & ~c & ~d);

endmodule