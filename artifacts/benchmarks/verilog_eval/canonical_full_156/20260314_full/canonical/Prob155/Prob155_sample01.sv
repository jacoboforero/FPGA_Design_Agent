module TopModule (
    input clk,
    input areset,
    input bump_left,
    input bump_right,
    input ground,
    input dig,
    output reg walk_left,
    output reg walk_right,
    output reg aaah,
    output reg digging
);

    // State encoding
    localparam [2:0]
        S_WALK_LEFT   = 3'd0,
        S_WALK_RIGHT  = 3'd1,
        S_FALL_LEFT   = 3'd2,
        S_FALL_RIGHT  = 3'd3,
        S_DIG_LEFT    = 3'd4,
        S_DIG_RIGHT   = 3'd5,
        S_SPLATTER    = 3'd6;

    reg [2:0] state, next_state;
    reg [4:0] fall_count, next_fall_count; // 5 bits to count up to 20+

    // Next state wire
    always @(*) begin
        next_state = state;
        next_fall_count = fall_count;

        case (state)
            S_WALK_LEFT: begin
                if (!ground) begin
                    next_state = S_FALL_LEFT;
                    next_fall_count = 5'd0;
                end else if (dig) begin
                    next_state = S_DIG_LEFT;
                end else if ((bump_left && !bump_right) || (bump_left && bump_right)) begin
                    next_state = S_WALK_RIGHT;
                end else begin
                    next_state = S_WALK_LEFT;
                end
            end

            S_WALK_RIGHT: begin
                if (!ground) begin
                    next_state = S_FALL_RIGHT;
                    next_fall_count = 5'd0;
                end else if (dig) begin
                    next_state = S_DIG_RIGHT;
                end else if ((bump_right && !bump_left) || (bump_left && bump_right)) begin
                    next_state = S_WALK_LEFT;
                end else begin
                    next_state = S_WALK_RIGHT;
                end
            end

            S_DIG_LEFT: begin
                if (!ground) begin
                    next_state = S_FALL_LEFT;
                    next_fall_count = 5'd0;
                end else begin
                    next_state = S_DIG_LEFT;
                end
            end

            S_DIG_RIGHT: begin
                if (!ground) begin
                    next_state = S_FALL_RIGHT;
                    next_fall_count = 5'd0;
                end else begin
                    next_state = S_DIG_RIGHT;
                end
            end

            S_FALL_LEFT: begin
                if (ground) begin
                    if (fall_count > 5'd19) begin
                        next_state = S_SPLATTER;
                    end else begin
                        next_state = S_WALK_LEFT;
                    end
                    next_fall_count = fall_count; // Don't care, but keep value
                end else begin
                    next_state = S_FALL_LEFT;
                    if (fall_count != 5'd31) // saturate at max value
                        next_fall_count = fall_count + 5'd1;
                end
            end

            S_FALL_RIGHT: begin
                if (ground) begin
                    if (fall_count > 5'd19) begin
                        next_state = S_SPLATTER;
                    end else begin
                        next_state = S_WALK_RIGHT;
                    end
                    next_fall_count = fall_count; // Don't care, but keep value
                end else begin
                    next_state = S_FALL_RIGHT;
                    if (fall_count != 5'd31)
                        next_fall_count = fall_count + 5'd1;
                end
            end

            S_SPLATTER: begin
                next_state = S_SPLATTER;
                next_fall_count = fall_count;
            end

            default: begin
                next_state = S_WALK_LEFT;
                next_fall_count = 5'd0;
            end
        endcase
    end

    // State and fall counter registers
    always @(posedge clk or posedge areset) begin
        if (areset) begin
            state <= S_WALK_LEFT;
            fall_count <= 5'd0;
        end else begin
            state <= next_state;
            fall_count <= next_fall_count;
        end
    end

    // Output wire (Moore FSM: outputs depend only on state)
    always @(*) begin
        walk_left  = 1'b0;
        walk_right = 1'b0;
        aaah       = 1'b0;
        digging    = 1'b0;
        case (state)
            S_WALK_LEFT:  walk_left  = 1'b1;
            S_WALK_RIGHT: walk_right = 1'b1;
            S_DIG_LEFT:   digging    = 1'b1;
            S_DIG_RIGHT:  digging    = 1'b1;
            S_FALL_LEFT:  aaah       = 1'b1;
            S_FALL_RIGHT: aaah       = 1'b1;
            S_SPLATTER: begin
                walk_left  = 1'b0;
                walk_right = 1'b0;
                aaah       = 1'b0;
                digging    = 1'b0;
            end
            default: begin
                walk_left  = 1'b0;
                walk_right = 1'b0;
                aaah       = 1'b0;
                digging    = 1'b0;
            end
        endcase
    end

endmodule