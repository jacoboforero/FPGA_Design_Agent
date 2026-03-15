module TopModule (
    input clk,
    input reset,
    input x,
    output reg z
);

    reg [2:0] state, next_state;

    // State register with synchronous reset
    always @(posedge clk) begin
        if (reset)
            state <= 3'b000;
        else
            state <= next_state;
    end

    // Next state wire
    always @(*) begin
        case (state)
            3'b000: begin
                if (x == 1'b0)
                    next_state = 3'b000;
                else
                    next_state = 3'b001;
            end
            3'b001: begin
                if (x == 1'b0)
                    next_state = 3'b001;
                else
                    next_state = 3'b100;
            end
            3'b010: begin
                if (x == 1'b0)
                    next_state = 3'b010;
                else
                    next_state = 3'b001;
            end
            3'b011: begin
                if (x == 1'b0)
                    next_state = 3'b001;
                else
                    next_state = 3'b010;
            end
            3'b100: begin
                if (x == 1'b0)
                    next_state = 3'b011;
                else
                    next_state = 3'b100;
            end
            default: next_state = 3'b000;
        endcase
    end

    // Output wire
    always @(*) begin
        case (state)
            3'b011,
            3'b100: z = 1'b1;
            default: z = 1'b0;
        endcase
    end

endmodule