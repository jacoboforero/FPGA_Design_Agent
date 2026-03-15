module TopModule (
    input clk,
    input reset,
    output reg [2:0] ena,
    output reg [15:0] q
);

    // Internal wires for carry/enable between digits
    wire ones_rollover;
    wire tens_rollover;
    wire hundreds_rollover;

    // Assign enable signals for upper three digits
    // ena[0]: increment tens (when ones rolls over from 9 to 0)
    // ena[1]: increment hundreds (when tens rolls over from 9 to 0)
    // ena[2]: increment thousands (when hundreds rolls over from 9 to 0)
    assign ones_rollover     = (q[3:0] == 4'd9);
    assign tens_rollover     = (q[7:4] == 4'd9) && ones_rollover;
    assign hundreds_rollover = (q[11:8] == 4'd9) && tens_rollover;

    always @ (posedge clk) begin
        if (reset) begin
            q   <= 16'd0;
            ena <= 3'b000;
        end else begin
            // Default ena to 0, set below if rollover occurs
            ena <= 3'b000;

            // Ones digit
            if (q[3:0] == 4'd9) begin
                q[3:0] <= 4'd0;
                ena[0] <= 1'b1; // Enable tens
            end else begin
                q[3:0] <= q[3:0] + 4'd1;
            end

            // Tens digit
            if (ones_rollover) begin
                if (q[7:4] == 4'd9) begin
                    q[7:4] <= 4'd0;
                    ena[1] <= 1'b1; // Enable hundreds
                end else begin
                    q[7:4] <= q[7:4] + 4'd1;
                end
            end

            // Hundreds digit
            if (tens_rollover) begin
                if (q[11:8] == 4'd9) begin
                    q[11:8] <= 4'd0;
                    ena[2] <= 1'b1; // Enable thousands
                end else begin
                    q[11:8] <= q[11:8] + 4'd1;
                end
            end

            // Thousands digit
            if (hundreds_rollover) begin
                if (q[15:12] == 4'd9) begin
                    q[15:12] <= 4'd0;
                end else begin
                    q[15:12] <= q[15:12] + 4'd1;
                end
            end
        end
    end

endmodule