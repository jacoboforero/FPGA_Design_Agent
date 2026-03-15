module TopModule (
    input  wire a,
    input  wire b,
    input  wire c,
    input  wire d,
    output wire out
);

assign out =
    // ab = 00
    (~a & ~b & ~c & ~d) | // cd = 00
    (~a & ~b & ~c &  d) | // cd = 01
    (~a & ~b &  c & ~d) | // cd = 10

    // ab = 01
    (~a &  b & ~c & ~d) | // cd = 00
    (~a &  b &  c & ~d) | // cd = 10

    // ab = 11
    ( a &  b & ~c &  d) | // cd = 01
    ( a &  b &  c & ~d) | // cd = 10
    ( a &  b &  c &  d) | // cd = 11

    // ab = 10
    ( a & ~b & ~c & ~d) | // cd = 00
    ( a & ~b & ~c &  d);  // cd = 01

endmodule