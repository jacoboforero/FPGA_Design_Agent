module TopModule (
    input  wire a,
    input  wire b,
    input  wire c,
    input  wire d,
    output wire out_sop,
    output wire out_pos
);

// Inputs as a 4-bit vector for easier minterm/maxterm mapping
wire [3:0] in;
assign in = {a, b, c, d};

// out_sop: Minimum Sum-of-Products for 2, 7, 15
// 2  = 0 0 1 0
// 7  = 0 1 1 1
// 15 = 1 1 1 1
// Variables: a = in[3], b = in[2], c = in[1], d = in[0]

// Minterms:
// 2:  ~a & ~b &  c & ~d
// 7:  ~a &  b &  c &  d
// 15:  a &  b &  c &  d

assign out_sop = (~a & ~b &  c & ~d) |
                 (~a &  b &  c &  d) |
                 ( a &  b &  c &  d);

// out_pos: Minimum Product-of-Sums for 2, 7, 15
// The maxterms for outputs 0 are for 0,1,4,5,6,9,10,13,14
// 0:  0 0 0 0
// 1:  0 0 0 1
// 4:  0 1 0 0
// 5:  0 1 0 1
// 6:  0 1 1 0
// 9:  1 0 0 1
// 10: 1 0 1 0
// 13: 1 1 0 1
// 14: 1 1 1 0

// Each maxterm is (a + b + c + d) with appropriate inversion
// out_pos = (a + b + c + d) for each 0 output, ANDed together

assign out_pos =
    ( a |  b |  c |  d ) & // 0: 0 0 0 0
    ( a |  b |  c | ~d ) & // 1: 0 0 0 1
    ( a | ~b |  c |  d ) & // 4: 0 1 0 0
    ( a | ~b |  c | ~d ) & // 5: 0 1 0 1
    ( a | ~b | ~c |  d ) & // 6: 0 1 1 0
    (~a |  b |  c | ~d ) & // 9: 1 0 0 1
    (~a |  b | ~c |  d ) & //10: 1 0 1 0
    (~a | ~b |  c | ~d ) & //13: 1 1 0 1
    (~a | ~b | ~c |  d );  //14: 1 1 1 0

endmodule