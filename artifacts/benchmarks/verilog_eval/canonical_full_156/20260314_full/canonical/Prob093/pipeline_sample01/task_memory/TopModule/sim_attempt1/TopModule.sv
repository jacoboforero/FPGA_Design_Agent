module TopModule (
    input  c,
    input  d,
    output [3:0] mux_in
);

    // mux_in[0]: ab=00
    // mux_in[1]: ab=01
    // mux_in[2]: ab=10
    // mux_in[3]: ab=11

    // According to the K-map:
    // ab\cd | 00 | 01 | 11 | 10
    //   00  |  0 |  0 |  0 |  1
    //   01  |  1 |  0 |  0 |  0
    //   11  |  1 |  0 |  1 |  1
    //   10  |  1 |  0 |  0 |  1

    // Each mux_in[x] is a function of c and d only.

    // mux_in[0]: ab=00, cd=00, value=0
    // mux_in[1]: ab=01, cd=00, value=1
    // mux_in[2]: ab=10, cd=00, value=1
    // mux_in[3]: ab=11, cd=00, value=1
    // But the K-map is for the output of the 4:1 mux, not mux_in[x].
    // We need to assign mux_in[0] = F(ab=00, c, d)
    // That is, for ab=00, F = 1 when cd=10 (i.e., c=1, d=0), else 0
    // For ab=01, F = 1 when cd=00 (c=0, d=0), else 0
    // For ab=10, F = 1 when cd=00 (c=0, d=0) or cd=10 (c=1, d=0), else 0
    // For ab=11, F = 1 when cd=00 (c=0, d=0), cd=10 (c=1, d=0), or cd=11 (c=1, d=1), else 0

    // Let's implement each mux_in[x] using only multiplexers.

    // mux_in[0]: ab=00
    // F = 1 only when c=1, d=0
    // F = (c & ~d)
    assign mux_in[0] = (c & ~d);

    // mux_in[1]: ab=01
    // F = 1 only when c=0, d=0
    // F = (~c & ~d)
    assign mux_in[1] = (~c & ~d);

    // mux_in[2]: ab=10
    // F = 1 when (c=0, d=0) or (c=1, d=0)
    // That is, d=0
    assign mux_in[2] = ~d;

    // mux_in[3]: ab=11
    // F = 1 when (c=0, d=0), (c=1, d=0), (c=1, d=1)
    // That is, (c=0, d=0): 1, (c=1, d=0): 1, (c=1, d=1): 1, (c=0, d=1): 0
    // So, F = c | (~c & ~d) = c + (~c & ~d)
    // This can be implemented as a 2:1 mux: if c==1, output 1; else output (~d)
    assign mux_in[3] = c ? 1'b1 : ~d;

endmodule