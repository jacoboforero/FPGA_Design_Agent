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
    reg dfr_active;

    // Combinational logic to decode sensor input to level
    function [1:0] decode_level;
        input [2:0] s_in;
        begin
            case (s_in)
                3'b000: decode_level = LEVEL_BELOW_S0;
                3'b001: decode_level = LEVEL_BETWEEN_S1_S0;
                3'b011: decode_level = LEVEL_BETWEEN_S2_S1;
                3'b111: decode_level = LEVEL_ABOVE_S2;
                default: decode_level = LEVEL_BELOW_S0;
            endcase
        end
    endfunction

    always @(posedge clk) begin
        if (reset) begin
            curr_level <= LEVEL_BELOW_S0;
            prev_level <= LEVEL_BELOW_S0;
            dfr_active <= 1'b1;
            fr2 <= 1'b1;
            fr1 <= 1'b1;
            fr0 <= 1'b1;
            dfr <= 1'b1;
        end else begin
            // Register the current level
            curr_level <= decode_level(s);

            // Track previous level for dfr logic
            if (curr_level != prev_level) begin
                // If water level rises, activate dfr
                if (curr_level > prev_level)
                    dfr_active <= 1'b1;
                // If water level falls, deactivate dfr
                else if (curr_level < prev_level)
                    dfr_active <= 1'b0;
                // If unchanged, keep previous dfr_active
                prev_level <= curr_level;
            end

            // Output logic
            case (curr_level)
                LEVEL_ABOVE_S2: begin
                    fr2 <= 1'b0;
                    fr1 <= 1'b0;
                    fr0 <= 1'b0;
                    dfr <= 1'b0;
                end
                LEVEL_BETWEEN_S2_S1: begin
                    fr2 <= 1'b0;
                    fr1 <= 1'b0;
                    fr0 <= 1'b1;
                    dfr <= dfr_active;
                end
                LEVEL_BETWEEN_S1_S0: begin
                    fr2 <= 1'b0;
                    fr1 <= 1'b1;
                    fr0 <= 1'b1;
                    dfr <= dfr_active;
                end
                LEVEL_BELOW_S0: begin
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