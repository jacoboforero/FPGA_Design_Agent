module TopModule (
    input  c,
    input  d,
    output [3:0] mux_in
);

    // mux_in[0]: ab=00 row: cd=00:0, 01:0, 11:0, 10:1
    // F = 1 when cd=10 (c=1, d=0) or cd=01 (c=0, d=1)
    assign mux_in[0] = (c & ~d) | (~c & d);

    // mux_in[1]: ab=01 row: cd=00:1, 01:0, 11:0, 10:0
    // F = 1 only when cd=00 (c=0, d=0)
    assign mux_in[1] = (~c & ~d);

    // mux_in[2]: ab=10 row: cd=00:1, 01:0, 11:0, 10:1
    // F = 1 when cd=00 (c=0, d=0), cd=10 (c=1, d=0), or cd=11 (c=1, d=1)
    assign mux_in[2] = (~c & ~d) | (c & ~d) | (c & d);

    // mux_in[3]: ab=11 row: cd=00:1, 01:0, 11:1, 10:1
    // F = 1 when cd=00 (c=0, d=0), cd=10 (c=1, d=0), or cd=11 (c=1, d=1)
    assign mux_in[3] = (~c & ~d) | (c & ~d) | (c & d);

endmodule