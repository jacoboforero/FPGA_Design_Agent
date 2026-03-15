module TopModule (
    input clk,
    input resetn,
    input x,
    input y,
    output reg f,
    output reg g
);

    // FSM state encoding
    localparam [2:0]
        S_A           = 3'd0, // Reset state
        S_F_PULSE     = 3'd1, // f=1 for one cycle after resetn deasserted
        S_WAIT_X1     = 3'd2, // Wait for x==1
        S_WAIT_X0     = 3'd3, // Wait for x==0 (after x==1)
        S_WAIT_X2     = 3'd4, // Wait for x==1 (after x==1,0)
        S_G1_WAIT_Y   = 3'd5, // g=1, wait for y==1 up to 2 cycles
        S_G1_PERM     = 3'd6, // g=1 permanently
        S_G0_PERM     = 3'd7; // g=0 permanently

    reg [2:0] state, next_state;
    reg [1:0] y_wait_cnt;

    // Next state logic
    always @(*) begin
        next_state = state;
        case (state)
            S_A: begin
                if (resetn)
                    next_state = S_F_PULSE;
            end
            S_F_PULSE: begin
                next_state = S_WAIT_X1;
            end
            S_WAIT_X1: begin
                if (x)
                    next_state = S_WAIT_X0;
            end
            S_WAIT_X0: begin
                if (!x)
                    next_state = S_WAIT_X2;
            end
            S_WAIT_X2: begin
                if (x)
                    next_state = S_G1_WAIT_Y;
            end
            S_G1_WAIT_Y: begin
                if (y)
                    next_state = S_G1_PERM;
                else if (y_wait_cnt == 2'd2)
                    next_state = S_G0_PERM;
            end
            S_G1_PERM: begin
                // Remain here until reset
            end
            S_G0_PERM: begin
                // Remain here until reset
            end
            default: next_state = S_A;
        endcase
    end

    // State, counter, and output registers
    always @(posedge clk) begin
        if (!resetn) begin
            state <= S_A;
            y_wait_cnt <= 2'd0;
            f <= 1'b0;
            g <= 1'b0;
        end else begin
            state <= next_state;

            // y_wait_cnt logic: reset on entering S_G1_WAIT_Y, increment while in S_G1_WAIT_Y
            if (state != S_G1_WAIT_Y && next_state == S_G1_WAIT_Y) begin
                y_wait_cnt <= 2'd0;
            end else if (state == S_G1_WAIT_Y && next_state == S_G1_WAIT_Y && !y) begin
                y_wait_cnt <= y_wait_cnt + 2'd1;
            end else begin
                y_wait_cnt <= 2'd0;
            end

            // Registered outputs
            case (next_state)
                S_F_PULSE: begin
                    f <= 1'b1;
                    g <= 1'b0;
                end
                S_G1_WAIT_Y: begin
                    f <= 1'b0;
                    g <= 1'b1;
                end
                S_G1_PERM: begin
                    f <= 1'b0;
                    g <= 1'b1;
                end
                S_G0_PERM: begin
                    f <= 1'b0;
                    g <= 1'b0;
                end
                default: begin
                    f <= 1'b0;
                    g <= 1'b0;
                end
            endcase
        end
    end

endmodule