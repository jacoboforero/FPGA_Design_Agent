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

// out_sop: 1 for 2, 7, 15; 0 for 0,1,4,5,6,9,10,13,14; 0 for don't-cares (3,8,11,12)
assign out_sop = (in == 4'd2)  ? 1'b1 :
                 (in == 4'd7)  ? 1'b1 :
                 (in == 4'd15) ? 1'b1 :
                 1'b0;

// out_pos: 1 for 2, 7, 15; 0 for 0,1,4,5,6,9,10,13,14; 0 for don't-cares (3,8,11,12)
assign out_pos = (in == 4'd2)  ? 1'b1 :
                 (in == 4'd7)  ? 1'b1 :
                 (in == 4'd15) ? 1'b1 :
                 1'b0;

endmodule