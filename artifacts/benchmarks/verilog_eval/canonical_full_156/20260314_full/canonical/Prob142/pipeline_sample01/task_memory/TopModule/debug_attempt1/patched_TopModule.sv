module TopModule (
    input clk,
    input areset,
    input bump_left,
    input bump_right,
    input ground,
    output reg walk_left,
    output reg walk_right,
    output reg aaah
);

    // State encoding
    localparam S_LEFT  = 2'd0;
    localparam S_RIGHT = 2'd1;
    localparam S_FALLL = 2'd2;
    localparam S_FALLR = 2'd3;

    reg [1:0] state, next_state;

    // State register with asynchronous reset
    always @(posedge clk or posedge areset) begin
        if (areset)
            state <= S_LEFT;
        else
            state <= next_state;
    end

    // Next state logic
    always @(*) begin
        case (state)
            S_LEFT: begin
                if (!ground)
                    next_state = S_FALLL;
                else if (bump_left)
                    next_state = S_RIGHT;
                else
                    next_state = S_LEFT;
            end
            S_RIGHT: begin
                if (!ground)
                    next_state = S_FALLR;
                else if (bump_right)
                    next_state = S_LEFT;
                else
                    next_state = S_RIGHT;
            end
            S_FALLL: begin
                if (ground)
                    next_state = S_LEFT;
                else
                    next_state = S_FALLL;
            end
            S_FALLR: begin
                if (ground)
                    next_state = S_RIGHT;
                else
                    next_state = S_FALLR;
            end
            default: next_state = S_LEFT;
        endcase
    end

    // Output logic (Moore FSM: outputs depend only on state)
    always @(*) begin
        case (state)
            S_LEFT: begin
                walk_left  = 1'b1;
                walk_right = 1'b0;
                aaah       = 1'b0;
            end
            S_RIGHT: begin
                walk_left  = 1'b0;
                walk_right = 1'b1;
                aaah       = 1'b0;
            end
            S_FALLL: begin
                walk_left  = 1'b0;
                walk_right = 1'b0;
                aaah       = 1'b1;
            end
            S_FALLR: begin
                walk_left  = 1'b0;
                walk_right = 1'b0;
                aaah       = 1'b1;
            end
            default: begin
                walk_left  = 1'b0;
                walk_right = 1'b0;
                aaah       = 1'b0;
            end
        endcase
    end

endmodule