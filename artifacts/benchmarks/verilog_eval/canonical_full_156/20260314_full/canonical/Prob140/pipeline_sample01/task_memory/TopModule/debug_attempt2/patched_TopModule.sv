module TopModule (
    input clk,
    input reset,
    input in,
    output reg disc,
    output reg flag,
    output reg err
);

    // State encoding for Moore FSM
    localparam S0 = 3'd0; // Last input was 0, 0 consecutive 1s
    localparam S1 = 3'd1; // 1 consecutive 1
    localparam S2 = 3'd2; // 2 consecutive 1s
    localparam S3 = 3'd3; // 3 consecutive 1s
    localparam S4 = 3'd4; // 4 consecutive 1s
    localparam S5 = 3'd5; // 5 consecutive 1s
    localparam S6 = 3'd6; // 6 consecutive 1s
    localparam S7 = 3'd7; // 7 or more consecutive 1s (error)

    reg [2:0] state, next_state;
    reg [2:0] prev_state;

    // Output wire (Moore: depends only on state, but 'err' is pulse on S6->S7 transition)
    always @ (posedge clk) begin
        if (reset) begin
            disc <= 1'b0;
            flag <= 1'b0;
            err  <= 1'b0;
        end else begin
            // Default outputs
            disc <= 1'b0;
            flag <= 1'b0;
            err  <= 1'b0;
            case (state)
                // S0-S4: no output
                S5: begin
                    if (!in)
                        disc <= 1'b1; // 0111110 detected
                end
                S6: begin
                    if (!in)
                        flag <= 1'b1; // 01111110 detected
                end
                S7: begin
                    if (prev_state == S6)
                        err <= 1'b1; // Pulse 'err' only on S6->S7 transition
                end
                default: ;
            endcase
        end
    end

    // State register and prev_state tracking
    always @ (posedge clk) begin
        if (reset) begin
            state <= S0;
            prev_state <= S0;
        end else begin
            prev_state <= state;
            state <= next_state;
        end
    end

    // Next state wire
    always @ (*) begin
        case (state)
            S0: begin
                if (in)
                    next_state = S1;
                else
                    next_state = S0;
            end
            S1: begin
                if (in)
                    next_state = S2;
                else
                    next_state = S0;
            end
            S2: begin
                if (in)
                    next_state = S3;
                else
                    next_state = S0;
            end
            S3: begin
                if (in)
                    next_state = S4;
                else
                    next_state = S0;
            end
            S4: begin
                if (in)
                    next_state = S5;
                else
                    next_state = S0;
            end
            S5: begin
                if (in)
                    next_state = S6;
                else
                    next_state = S0; // 0111110: disc
            end
            S6: begin
                if (in)
                    next_state = S7;
                else
                    next_state = S0; // 01111110: flag
            end
            S7: begin
                if (in)
                    next_state = S7; // Remain in error state while 1s continue
                else
                    next_state = S0;
            end
            default: next_state = S0;
        endcase
    end

endmodule