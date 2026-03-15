module TopModule (
    input clk,
    input reset,
    input in,
    output reg out
);

    // State encoding
    localparam [1:0] STATE_A = 2'b00;
    localparam [1:0] STATE_B = 2'b01;
    localparam [1:0] STATE_C = 2'b10;
    localparam [1:0] STATE_D = 2'b11;

    reg [1:0] state, next_state;

    // State register with synchronous active-high reset
    always @(posedge clk) begin
        if (reset)
            state <= STATE_A;
        else
            state <= next_state;
    end

    // Next state wire
    always @(*) begin
        case (state)
            STATE_A: begin
                if (in)
                    next_state = STATE_B;
                else
                    next_state = STATE_A;
            end
            STATE_B: begin
                if (in)
                    next_state = STATE_B;
                else
                    next_state = STATE_C;
            end
            STATE_C: begin
                if (in)
                    next_state = STATE_D;
                else
                    next_state = STATE_A;
            end
            STATE_D: begin
                if (in)
                    next_state = STATE_B;
                else
                    next_state = STATE_C;
            end
            default: next_state = STATE_A;
        endcase
    end

    // Output wire (Moore: output depends only on state)
    always @(*) begin
        case (state)
            STATE_D: out = 1'b1;
            default: out = 1'b0;
        endcase
    end

endmodule