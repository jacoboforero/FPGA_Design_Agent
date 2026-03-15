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

    // State encoding (3 bits for 6 states)
    localparam S_WALK_LEFT  = 3'd0;
    localparam S_WALK_RIGHT = 3'd1;
    localparam S_FALL_LEFT  = 3'd2;
    localparam S_FALL_RIGHT = 3'd3;
    localparam S_DIG_LEFT   = 3'd4;
    localparam S_DIG_RIGHT  = 3'd5;

    reg [2:0] state, next_state;

    // State register with asynchronous reset
    always @(posedge clk or posedge areset) begin
        if (areset)
            state <= S_WALK_LEFT;
        else
            state <= next_state;
    end

    // Next state logic
    always @(*) begin
        case (state)
            S_WALK_LEFT: begin
                if (!ground)
                    next_state = S_FALL_LEFT;
                else if (dig)
                    next_state = S_DIG_LEFT;
                else if (bump_left)
                    next_state = S_WALK_RIGHT;
                else
                    next_state = S_WALK_LEFT;
            end
            S_WALK_RIGHT: begin
                if (!ground)
                    next_state = S_FALL_RIGHT;
                else if (dig)
                    next_state = S_DIG_RIGHT;
                else if (bump_right)
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

    // Output logic (Moore FSM: outputs depend only on state)
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