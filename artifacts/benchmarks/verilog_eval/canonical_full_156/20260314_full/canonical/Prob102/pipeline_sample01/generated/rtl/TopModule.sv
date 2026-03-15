module TopModule (
    input  wire a,
    input  wire b,
    input  wire c,
    input  wire d,
    output wire q
);

assign q = (b & (d | c)) | (a & (d | c));

endmodule