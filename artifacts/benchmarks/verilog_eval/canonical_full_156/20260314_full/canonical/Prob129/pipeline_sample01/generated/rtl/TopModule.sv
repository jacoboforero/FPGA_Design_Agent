module TopModule (
    input clk,
    input aresetn,
    input x,
    output reg z
);

    // State encoding
    localparam S0 = 2'b00; // Initial state
    localparam S1 = 2'b01; // Saw '1'
    localparam S2 = 2'b10; // Saw '10'

    reg [1:0] state, next_state;

    // State register with asynchronous active-low reset
    always @(posedge clk or negedge aresetn) begin
        if (!aresetn)
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
                if (x)
                    next_state = S1;
                else
                    next_state = S2;
            end
            S2: begin
                if (x)
                    next_state = S1;
                else
                    next_state = S0;
            end
            default: next_state = S0;
        endcase
    end

    // Output wire (Mealy)
    always @(*) begin
        case (state)
            S0: z = 1'b0;
            S1: z = 1'b0;
            S2: z = x ? 1'b1 : 1'b0;
            default: z = 1'b0;
        endcase
    end

endmodule