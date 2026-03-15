module TopModule (
    input  wire a,
    input  wire b,
    input  wire c,
    input  wire d,
    output wire out
);

assign out =
    // ab=00, cd=10,11 -> out=1
    (~a & ~b &  c) | (~a & ~b &  d) |
    // ab=01, cd=none (all 0 or d)
    // ab=10, cd=00,10,11 -> out=1
    ( a & ~b & ~c & ~d) | ( a & ~b &  c) | ( a & ~b &  d) |
    // ab=11, cd=00,10,11 -> out=1
    ( a &  b & ~c & ~d) | ( a &  b &  c) | ( a &  b &  d);

endmodule