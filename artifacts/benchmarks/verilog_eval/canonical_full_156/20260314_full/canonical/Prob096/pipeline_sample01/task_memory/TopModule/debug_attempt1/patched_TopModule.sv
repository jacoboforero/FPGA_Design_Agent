module TopModule (
    input clk,
    input reset,
    input data,
    output reg start_shifting
);

    // FSM state encoding
    localparam S0 = 2'd0; // No match yet
    localparam S1 = 2'd1; // Matched '1'
    localparam S2 = 2'd2; // Matched '11'
    localparam S3 = 2'd3; // Matched '110'

    reg [1:0] state, next_state;

    // Output pulse logic
    reg start_shifting_next;

    always @(*) begin
        next_state = state;
        start_shifting_next = 1'b0;
        case (state)
            S0: begin
                if (data)
                    next_state = S1;
                else
                    next_state = S0;
            end
            S1: begin
                if (data)
                    next_state = S2;
                else
                    next_state = S0;
            end
            S2: begin
                if (!data)
                    next_state = S3;
                else
                    next_state = S2;
            end
            S3: begin
                if (data) begin
                    start_shifting_next = 1'b1;
                    next_state = S1; // allow overlapping sequences
                end else begin
                    next_state = S0;
                end
            end
            default: next_state = S0;
        endcase
    end

    always @(posedge clk) begin
        if (reset) begin
            state <= S0;
            start_shifting <= 1'b0;
        end else begin
            state <= next_state;
            start_shifting <= start_shifting_next;
        end
    end

endmodule