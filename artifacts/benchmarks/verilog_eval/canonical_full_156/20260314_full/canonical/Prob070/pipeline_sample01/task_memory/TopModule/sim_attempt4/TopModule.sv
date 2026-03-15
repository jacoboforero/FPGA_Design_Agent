module TopModule (
    input  wire a,
    input  wire b,
    input  wire c,
    input  wire d,
    output wire out_sop,
    output wire out_pos
);

// Minimum SOP for out_sop: 2, 7, 15
// 2: 0010 (a=0,b=0,c=1,d=0)
// 7: 0111 (a=0,b=1,c=1,d=1)
// 15:1111 (a=1,b=1,c=1,d=1)
// out_sop = (~a & ~b & c & ~d) | (~a & b & c & d) | (a & b & c & d)
assign out_sop = (~a & ~b & c & ~d) | (~a & b & c & d) | (a & b & c & d);

// Minimum POS for out_pos: 2, 7, 15
// out_pos = (a | ~b | ~c | d) & (a | ~b | c | ~d) & (a | b | ~c | ~d)
assign out_pos = (a | ~b | ~c | d) & (a | ~b | c | ~d) & (a | b | ~c | ~d);

endmodule