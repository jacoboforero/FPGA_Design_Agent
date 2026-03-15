module TopModule (
    input clk,
    input reset,
    output reg [2:0] ena,
    output reg [15:0] q
);

    // Internal registers for BCD digits
    reg [3:0] ones, tens, hundreds, thousands;

    // Internal rollover flags (combinational)
    wire ones_rollover = (ones == 4'd9);
    wire tens_rollover = (tens == 4'd9) && ones_rollover;
    wire hundreds_rollover = (hundreds == 4'd9) && tens_rollover;

    // Registered rollover flags to generate ena pulses
    reg ones_rollover_d, tens_rollover_d, hundreds_rollover_d;

    always @(posedge clk) begin
        if (reset) begin
            ones <= 4'd0;
            tens <= 4'd0;
            hundreds <= 4'd0;
            thousands <= 4'd0;
            ena <= 3'b000;
            ones_rollover_d <= 1'b0;
            tens_rollover_d <= 1'b0;
            hundreds_rollover_d <= 1'b0;
        end else begin
            // Update BCD digits
            if (ones == 4'd9) begin
                ones <= 4'd0;
            end else begin
                ones <= ones + 4'd1;
            end

            if (ones == 4'd9) begin
                if (tens == 4'd9) begin
                    tens <= 4'd0;
                end else begin
                    tens <= tens + 4'd1;
                end
            end

            if ((tens == 4'd9) && (ones == 4'd9)) begin
                if (hundreds == 4'd9) begin
                    hundreds <= 4'd0;
                end else begin
                    hundreds <= hundreds + 4'd1;
                end
            end

            if ((hundreds == 4'd9) && (tens == 4'd9) && (ones == 4'd9)) begin
                if (thousands == 4'd9) begin
                    thousands <= 4'd0;
                end else begin
                    thousands <= thousands + 4'd1;
                end
            end

            // Register rollover events for ena pulse generation
            ones_rollover_d <= ones_rollover;
            tens_rollover_d <= tens_rollover;
            hundreds_rollover_d <= hundreds_rollover;

            // Generate ena pulses: pulse high for one cycle after rollover
            ena[0] <= ones_rollover_d;
            ena[1] <= tens_rollover_d;
            ena[2] <= hundreds_rollover_d;
        end
    end

    // Output q as concatenation of BCD digits
    always @(*) begin
        q = {thousands, hundreds, tens, ones};
    end

endmodule