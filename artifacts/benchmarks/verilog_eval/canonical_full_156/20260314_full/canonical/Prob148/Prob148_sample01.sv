module TopModule (
    input clk,
    input resetn,
    input [2:0] r,
    output reg [2:0] g
);

    // State encoding
    localparam [1:0] S_A = 2'd0;
    localparam [1:0] S_B = 2'd1;
    localparam [1:0] S_C = 2'd2;
    localparam [1:0] S_D = 2'd3;

    reg [1:0] state, next_state;

    // State register with synchronous active-low reset
    always @(posedge clk) begin
        if (!resetn)
            state <= S_A;
        else
            state <= next_state;
    end

    // Next state logic
    always @(*) begin
        case (state)
            S_A: begin
                if (r[0])
                    next_state = S_B;
                else if (r[1])
                    next_state = S_C;
                else if (r[2])
                    next_state = S_D;
                else
                    next_state = S_A;
            end
            S_B: begin
                if (r[0])
                    next_state = S_B;
                else
                    next_state = S_A;
            end
            S_C: begin
                if (r[1])
                    next_state = S_C;
                else
                    next_state = S_A;
            end
            S_D: begin
                if (r[2])
                    next_state = S_D;
                else
                    next_state = S_A;
            end
            default: next_state = S_A;
        endcase
    end

    // Output logic
    always @(*) begin
        case (state)
            S_B: g = 3'b001;
            S_C: g = 3'b010;
            S_D: g = 3'b100;
            default: g = 3'b000;
        endcase
    end

endmodule