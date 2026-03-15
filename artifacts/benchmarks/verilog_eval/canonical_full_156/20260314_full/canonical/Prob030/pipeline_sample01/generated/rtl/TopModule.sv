module TopModule (
    input  [254:0] in,
    output [7:0]   out
);

    // Stage 1: sum adjacent bits to get 128 2-bit numbers (except last, which is single bit)
    wire [1:0] sum1 [127:0];
    genvar i;
    generate
        for (i = 0; i < 127; i = i + 1) begin : gen_sum1
            assign sum1[i] = in[2*i] + in[2*i+1];
        end
        // Last bit (since 255 is odd)
        assign sum1[127] = {1'b0, in[254]};
    endgenerate

    // Stage 2: sum pairs of 2-bit numbers to get 64 3-bit numbers (except last, which is 2-bit)
    wire [2:0] sum2 [63:0];
    generate
        for (i = 0; i < 63; i = i + 1) begin : gen_sum2
            assign sum2[i] = sum1[2*i] + sum1[2*i+1];
        end
        // Last one
        assign sum2[63] = sum1[126] + sum1[127];
    endgenerate

    // Stage 3: sum pairs of 3-bit numbers to get 32 4-bit numbers
    wire [3:0] sum3 [31:0];
    generate
        for (i = 0; i < 32; i = i + 1) begin : gen_sum3
            assign sum3[i] = sum2[2*i] + sum2[2*i+1];
        end
    endgenerate

    // Stage 4: sum pairs of 4-bit numbers to get 16 5-bit numbers
    wire [4:0] sum4 [15:0];
    generate
        for (i = 0; i < 16; i = i + 1) begin : gen_sum4
            assign sum4[i] = sum3[2*i] + sum3[2*i+1];
        end
    endgenerate

    // Stage 5: sum pairs of 5-bit numbers to get 8 6-bit numbers
    wire [5:0] sum5 [7:0];
    generate
        for (i = 0; i < 8; i = i + 1) begin : gen_sum5
            assign sum5[i] = sum4[2*i] + sum4[2*i+1];
        end
    endgenerate

    // Stage 6: sum pairs of 6-bit numbers to get 4 7-bit numbers
    wire [6:0] sum6 [3:0];
    generate
        for (i = 0; i < 4; i = i + 1) begin : gen_sum6
            assign sum6[i] = sum5[2*i] + sum5[2*i+1];
        end
    endgenerate

    // Stage 7: sum pairs of 7-bit numbers to get 2 8-bit numbers
    wire [7:0] sum7 [1:0];
    generate
        for (i = 0; i < 2; i = i + 1) begin : gen_sum7
            assign sum7[i] = sum6[2*i] + sum6[2*i+1];
        end
    endgenerate

    // Final stage: sum the two 8-bit numbers to get the total population count
    assign out = sum7[0] + sum7[1];

endmodule