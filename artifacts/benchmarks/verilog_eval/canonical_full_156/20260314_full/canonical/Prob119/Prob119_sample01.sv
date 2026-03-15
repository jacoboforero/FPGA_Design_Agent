module TopModule (
    input clk,
    input areset,
    input in,
    output reg out
);

    // State encoding
    localparam [1:0] S_A = 2'b00;
    localparam [1:0] S_B = 2'b01;
    localparam [1:0] S_C = 2'b10;
    localparam [1:0] S_D = 2'b11;

    reg [1:0] state, next_state;

    // State register with asynchronous reset to state A
    always @(posedge clk or posedge areset) begin
        if (areset)
            state <= S_A;
        else
            state <= next_state;
    end

    // Next state wire
    always @(*) begin
        case (state)
            S_A: begin
                if (in)
                    next_state = S_B;
                else
                    next_state = S_A;
            end
            S_B: begin
                if (in)
                    next_state = S_B;
                else
                    next_state = S_C;
            end
            S_C: begin
                if (in)
                    next_state = S_D;
                else
                    next_state = S_A;
            end
            S_D: begin
                if (in)
                    next_state = S_B;
                else
                    next_state = S_C;
            end
            default: next_state = S_A;
        endcase
    end

    // Output wire (Moore: depends only on state)
    always @(*) begin
        case (state)
            S_D: out = 1'b1;
            default: out = 1'b0;
        endcase
    end

endmodule