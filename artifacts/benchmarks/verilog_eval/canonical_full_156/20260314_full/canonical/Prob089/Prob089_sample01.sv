module TopModule (
    input clk,
    input areset,
    input x,
    output reg z
);

    // State encoding
    localparam S0 = 1'b0; // Before first '1' seen
    localparam S1 = 1'b1; // After first '1' seen

    reg state, next_state;

    // State register with async reset
    always @(posedge clk or posedge areset) begin
        if (areset)
            state <= S0;
        else
            state <= next_state;
    end

    // Next state wire
    always @(*) begin
        case (state)
            S0: begin
                if (x)
                    next_state = S1;
                else
                    next_state = S0;
            end
            S1: begin
                next_state = S1;
            end
            default: next_state = S0;
        endcase
    end

    // Output wire (Moore)
    always @(posedge clk or posedge areset) begin
        if (areset)
            z <= 1'b0;
        else begin
            case (state)
                S0: z <= x;
                S1: z <= ~x;
                default: z <= 1'b0;
            endcase
        end
    end

endmodule