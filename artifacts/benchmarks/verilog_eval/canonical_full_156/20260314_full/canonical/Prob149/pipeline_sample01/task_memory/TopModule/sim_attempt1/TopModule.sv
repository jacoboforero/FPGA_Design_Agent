module TopModule (
    input clk,
    input reset,
    input [2:0] s,
    output reg fr2,
    output reg fr1,
    output reg fr0,
    output reg dfr
);

    // State encoding for water level
    localparam LEVEL_BELOW_S0      = 2'd0; // No sensors asserted
    localparam LEVEL_BETWEEN_S1_S0 = 2'd1; // Only s[0] asserted
    localparam LEVEL_BETWEEN_S2_S1 = 2'd2; // s[0] and s[1] asserted
    localparam LEVEL_ABOVE_S2      = 2'd3; // s[0], s[1], s[2] asserted

    reg [1:0] curr_level;
    reg [1:0] prev_level;

    // Combinational wire to determine current water level from sensors
    always @(*) begin
        case (s)
            3'b000: curr_level = LEVEL_BELOW_S0;
            3'b001: curr_level = LEVEL_BETWEEN_S1_S0;
            3'b011: curr_level = LEVEL_BETWEEN_S2_S1;
            3'b111: curr_level = LEVEL_ABOVE_S2;
            default: curr_level = LEVEL_BELOW_S0; // treat all other cases as below s[0]
        endcase
    end

    // Sequential wire for prev_level and outputs
    always @(posedge clk) begin
        if (reset) begin
            prev_level <= LEVEL_BELOW_S0;
            fr2 <= 1'b1;
            fr1 <= 1'b1;
            fr0 <= 1'b1;
            dfr <= 1'b1;
        end else begin
            // Update prev_level only when water level changes
            if (curr_level != prev_level)
                prev_level <= curr_level;

            // Default outputs
            fr2 <= 1'b0;
            fr1 <= 1'b0;
            fr0 <= 1'b0;
            dfr <= 1'b0;

            case (curr_level)
                LEVEL_ABOVE_S2: begin
                    // Above s[2]: No flow
                    fr2 <= 1'b0;
                    fr1 <= 1'b0;
                    fr0 <= 1'b0;
                    dfr <= 1'b0;
                end
                LEVEL_BETWEEN_S2_S1: begin
                    // Between s[2] and s[1]: fr0
                    fr2 <= 1'b0;
                    fr1 <= 1'b0;
                    fr0 <= 1'b1;
                    // dfr: open supplemental if previous level was lower
                    if (prev_level < curr_level)
                        dfr <= 1'b1;
                end
                LEVEL_BETWEEN_S1_S0: begin
                    // Between s[1] and s[0]: fr0, fr1
                    fr2 <= 1'b0;
                    fr1 <= 1'b1;
                    fr0 <= 1'b1;
                    // dfr: open supplemental if previous level was lower
                    if (prev_level < curr_level)
                        dfr <= 1'b1;
                end
                LEVEL_BELOW_S0: begin
                    // Below s[0]: fr0, fr1, fr2
                    fr2 <= 1'b1;
                    fr1 <= 1'b1;
                    fr0 <= 1'b1;
                    dfr <= 1'b1;
                end
                default: begin
                    fr2 <= 1'b0;
                    fr1 <= 1'b0;
                    fr0 <= 1'b0;
                    dfr <= 1'b0;
                end
            endcase
        end
    end

endmodule