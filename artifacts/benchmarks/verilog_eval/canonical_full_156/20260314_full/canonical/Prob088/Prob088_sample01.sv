module TopModule (
    input clk,
    input areset,
    input x,
    output reg z
);

    // One-hot state encoding
    localparam STATE_A = 2'b01;
    localparam STATE_B = 2'b10;

    reg [1:0] state, next_state;

    // State register with asynchronous active-high reset
    always @(posedge clk or posedge areset) begin
        if (areset)
            state <= STATE_A;
        else
            state <= next_state;
    end

    // Next state wire
    always @(*) begin
        case (state)
            STATE_A: begin
                if (x)
                    next_state = STATE_B;
                else
                    next_state = STATE_A;
            end
            STATE_B: begin
                next_state = STATE_B;
            end
            default: begin
                next_state = STATE_A;
            end
        endcase
    end

    // Output wire (Mealy)
    always @(*) begin
        case (state)
            STATE_A: begin
                if (x)
                    z = 1'b1;
                else
                    z = 1'b0;
            end
            STATE_B: begin
                if (x)
                    z = 1'b0;
                else
                    z = 1'b1;
            end
            default: z = 1'b0;
        endcase
    end

endmodule