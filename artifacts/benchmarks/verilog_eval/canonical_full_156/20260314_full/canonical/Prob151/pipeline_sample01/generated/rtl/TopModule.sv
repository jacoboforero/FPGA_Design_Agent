module TopModule (
    input clk,
    input reset,
    input data,
    input done_counting,
    input ack,
    output reg shift_ena,
    output reg counting,
    output reg done
);

    // FSM state encoding
    localparam S_IDLE         = 3'd0;
    localparam S_DETECT_1     = 3'd1;
    localparam S_DETECT_11    = 3'd2;
    localparam S_DETECT_110   = 3'd3;
    localparam S_DETECT_1101  = 3'd4;
    localparam S_SHIFT        = 3'd5;
    localparam S_COUNT        = 3'd6;
    localparam S_DONE         = 3'd7;

    reg [2:0] state, next_state;
    reg [2:0] shift_cnt, next_shift_cnt;

    // FSM state register
    always @(posedge clk) begin
        if (reset) begin
            state <= S_IDLE;
            shift_cnt <= 3'd0;
        end else begin
            state <= next_state;
            shift_cnt <= next_shift_cnt;
        end
    end

    // FSM next state wire and outputs
    always @(*) begin
        // Default assignments
        next_state = state;
        next_shift_cnt = shift_cnt;
        shift_ena = 1'b0;
        counting = 1'b0;
        done = 1'b0;

        case (state)
            S_IDLE: begin
                if (data)
                    next_state = S_DETECT_1;
                else
                    next_state = S_IDLE;
                next_shift_cnt = 3'd0;
            end
            S_DETECT_1: begin
                if (data)
                    next_state = S_DETECT_11;
                else
                    next_state = S_IDLE;
                next_shift_cnt = 3'd0;
            end
            S_DETECT_11: begin
                if (~data)
                    next_state = S_DETECT_110;
                else
                    next_state = S_DETECT_11;
                next_shift_cnt = 3'd0;
            end
            S_DETECT_110: begin
                if (data)
                    next_state = S_DETECT_1101;
                else
                    next_state = S_IDLE;
                next_shift_cnt = 3'd0;
            end
            S_DETECT_1101: begin
                // Pattern 1101 detected, start shifting
                next_state = S_SHIFT;
                next_shift_cnt = 3'd0;
            end
            S_SHIFT: begin
                shift_ena = 1'b1;
                if (shift_cnt == 3'd3) begin
                    // After 4 cycles (shift_cnt 0,1,2,3), assert shift_ena for 4th time, then move to counting next cycle
                    next_state = S_COUNT;
                    next_shift_cnt = 3'd0;
                end else begin
                    next_state = S_SHIFT;
                    next_shift_cnt = shift_cnt + 3'd1;
                end
            end
            S_COUNT: begin
                counting = 1'b1;
                if (done_counting)
                    next_state = S_DONE;
                else
                    next_state = S_COUNT;
                next_shift_cnt = 3'd0;
            end
            S_DONE: begin
                done = 1'b1;
                if (ack)
                    next_state = S_IDLE;
                else
                    next_state = S_DONE;
                next_shift_cnt = 3'd0;
            end
            default: begin
                next_state = S_IDLE;
                next_shift_cnt = 3'd0;
            end
        endcase
    end

endmodule