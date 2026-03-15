module TopModule (
    input clk,
    input reset,
    input w,
    output reg z
);

    // State encoding
    localparam [2:0] S_A = 3'd0;
    localparam [2:0] S_B = 3'd1;
    localparam [2:0] S_C = 3'd2;
    localparam [2:0] S_D = 3'd3;
    localparam [2:0] S_E = 3'd4;
    localparam [2:0] S_F = 3'd5;

    reg [2:0] state, next_state;

    // State register
    always @(posedge clk) begin
        if (reset)
            state <= S_A;
        else
            state <= next_state;
    end

    // Next state wire
    always @(*) begin
        case (state)
            S_A: begin
                if (w)
                    next_state = S_A;
                else
                    next_state = S_B;
            end
            S_B: begin
                if (w)
                    next_state = S_D;
                else
                    next_state = S_C;
            end
            S_C: begin
                if (w)
                    next_state = S_D;
                else
                    next_state = S_E;
            end
            S_D: begin
                if (w)
                    next_state = S_A;
                else
                    next_state = S_F;
            end
            S_E: begin
                if (w)
                    next_state = S_D;
                else
                    next_state = S_E;
            end
            S_F: begin
                if (w)
                    next_state = S_D;
                else
                    next_state = S_C;
            end
            default: next_state = S_A;
        endcase
    end

    // Output wire
    always @(*) begin
        case (state)
            S_E, S_F: z = 1'b1;
            default:  z = 1'b0;
        endcase
    end

endmodule