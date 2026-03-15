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
    localparam S_WALK_LEFT  = 2'd0;
    localparam S_WALK_RIGHT = 2'd1;
    localparam S_FALL_LEFT  = 2'd2;
    localparam S_FALL_RIGHT = 2'd3;
    localparam S_DIG_LEFT   = 2'd4;
    localparam S_DIG_RIGHT  = 2'd5;

    reg [2:0] state, next_state;

    // State register with asynchronous reset
    always @(posedge clk or posedge areset) begin
        if (areset)
            state <= S_WALK_LEFT;
        else
            state <= next_state;
    end

    // Next state wire
    always @(*) begin
        case (state)
            S_WALK_LEFT: begin
                if (!ground)
                    next_state = S_FALL_LEFT;
                else if (dig)
                    next_state = S_DIG_LEFT;
                else if (bump_left || bump_right)
                    next_state = S_WALK_RIGHT;
                else
                    next_state = S_WALK_LEFT;
            end
            S_WALK_RIGHT: begin
                if (!ground)
                    next_state = S_FALL_RIGHT;
                else if (dig)
                    next_state = S_DIG_RIGHT;
                else if (bump_left || bump_right)
                    next_state = S_WALK_LEFT;
                else
                    next_state = S_WALK_RIGHT;
            end
            S_FALL_LEFT: begin
                if (ground)
                    next_state = S_WALK_LEFT;
                else
                    next_state = S_FALL_LEFT;
            end
            S_FALL_RIGHT: begin
                if (ground)
                    next_state = S_WALK_RIGHT;
                else
                    next_state = S_FALL_RIGHT;
            end
            S_DIG_LEFT: begin
                if (!ground)
                    next_state = S_FALL_LEFT;
                else
                    next_state = S_DIG_LEFT;
            end
            S_DIG_RIGHT: begin
                if (!ground)
                    next_state = S_FALL_RIGHT;
                else
                    next_state = S_DIG_RIGHT;
            end
            default: next_state = S_WALK_LEFT;
        endcase
    end

    // Output wire (Moore FSM: outputs depend only on state)
    always @(*) begin
        walk_left  = 0;
        walk_right = 0;
        aaah       = 0;
        digging    = 0;
        case (state)
            S_WALK_LEFT:  walk_left  = 1;
            S_WALK_RIGHT: walk_right = 1;
            S_FALL_LEFT,
            S_FALL_RIGHT: aaah       = 1;
            S_DIG_LEFT:   digging    = 1;
            S_DIG_RIGHT:  digging    = 1;
        endcase
    end

endmodule