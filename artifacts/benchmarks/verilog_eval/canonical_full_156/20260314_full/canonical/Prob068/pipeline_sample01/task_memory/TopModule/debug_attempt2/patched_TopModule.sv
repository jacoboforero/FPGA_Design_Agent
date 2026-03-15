module TopModule (
    input clk,
    input reset,
    output reg [2:0] ena,
    output reg [15:0] q
);

    // Internal registers for BCD digits
    reg [3:0] ones, tens, hundreds, thousands;

    // Combinational signals for increment enables
    wire inc_ones = 1'b1;
    wire inc_tens = (ones == 4'd9);
    wire inc_hundreds = (tens == 4'd9) && (ones == 4'd9);
    wire inc_thousands = (hundreds == 4'd9) && (tens == 4'd9) && (ones == 4'd9);

    always @(posedge clk) begin
        if (reset) begin
            ones <= 4'd0;
            tens <= 4'd0;
            hundreds <= 4'd0;
            thousands <= 4'd0;
        end else begin
            // Ones digit
            if (ones == 4'd9) begin
                ones <= 4'd0;
            end else begin
                ones <= ones + 4'd1;
            end

            // Tens digit
            if (ones == 4'd9) begin
                if (tens == 4'd9) begin
                    tens <= 4'd0;
                end else begin
                    tens <= tens + 4'd1;
                end
            end

            // Hundreds digit
            if ((tens == 4'd9) && (ones == 4'd9)) begin
                if (hundreds == 4'd9) begin
                    hundreds <= 4'd0;
                end else begin
                    hundreds <= hundreds + 4'd1;
                end
            end

            // Thousands digit
            if ((hundreds == 4'd9) && (tens == 4'd9) && (ones == 4'd9)) begin
                if (thousands == 4'd9) begin
                    thousands <= 4'd0;
                end else begin
                    thousands <= thousands + 4'd1;
                end
            end
        end
    end

    // ena[0]: pulse high when ones digit rolls over (i.e., about to increment tens)
    // ena[1]: pulse high when tens digit rolls over (i.e., about to increment hundreds)
    // ena[2]: pulse high when hundreds digit rolls over (i.e., about to increment thousands)
    always @(*) begin
        ena[0] = (ones == 4'd9);
        ena[1] = (tens == 4'd9) && (ones == 4'd9);
        ena[2] = (hundreds == 4'd9) && (tens == 4'd9) && (ones == 4'd9);
    end

    // Output q as concatenation of BCD digits
    always @(*) begin
        q = {thousands, hundreds, tens, ones};
    end

endmodule