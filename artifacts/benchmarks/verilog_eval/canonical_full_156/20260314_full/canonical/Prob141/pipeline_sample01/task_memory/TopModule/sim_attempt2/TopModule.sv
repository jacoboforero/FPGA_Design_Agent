module TopModule (
    input clk,
    input reset,
    input ena,
    output reg pm,
    output reg [7:0] hh,
    output reg [7:0] mm,
    output reg [7:0] ss
);

    // Internal BCD digits for seconds, minutes, hours
    reg [3:0] sec_ones;
    reg [3:0] sec_tens;
    reg [3:0] min_ones;
    reg [3:0] min_tens;
    reg [3:0] hour_ones;
    reg [3:0] hour_tens;

    always @(posedge clk) begin
        if (reset) begin
            // Reset to 12:00:00 AM
            sec_ones  <= 4'd0;
            sec_tens  <= 4'd0;
            min_ones  <= 4'd0;
            min_tens  <= 4'd0;
            hour_ones <= 4'd2;
            hour_tens <= 4'd1;
            pm        <= 1'b0;
        end else if (ena) begin
            // Seconds increment
            if (sec_ones == 4'd9) begin
                sec_ones <= 4'd0;
                if (sec_tens == 4'd5) begin
                    sec_tens <= 4'd0;
                    // Minutes increment
                    if (min_ones == 4'd9) begin
                        min_ones <= 4'd0;
                        if (min_tens == 4'd5) begin
                            min_tens <= 4'd0;
                            // Hours increment
                            // PM toggles at 11:59:59 -> 12:00:00
                            if ((hour_tens == 4'd1) && (hour_ones == 4'd1)) begin
                                hour_ones <= 4'd2;
                                hour_tens <= 4'd1;
                                pm <= ~pm;
                            end else if ((hour_tens == 4'd1) && (hour_ones == 4'd2)) begin
                                // 12 -> 1
                                hour_ones <= 4'd1;
                                hour_tens <= 4'd0;
                            end else if ((hour_tens == 4'd0) && (hour_ones == 4'd9)) begin
                                // 9 -> 10
                                hour_ones <= 4'd0;
                                hour_tens <= 4'd1;
                            end else begin
                                // Normal increment
                                hour_ones <= hour_ones + 4'd1;
                            end
                        end else begin
                            min_tens <= min_tens + 4'd1;
                        end
                    end else begin
                        min_ones <= min_ones + 4'd1;
                    end
                end else begin
                    sec_tens <= sec_tens + 4'd1;
                end
            end else begin
                sec_ones <= sec_ones + 4'd1;
            end
        end
    end

    // Output assignments
    always @* begin
        hh = {hour_tens, hour_ones};
        mm = {min_tens, min_ones};
        ss = {sec_tens, sec_ones};
    end

endmodule