module TopModule (
    input clk,
    input reset,
    input [7:0] in,
    output reg done
);

    // FSM states
    localparam IDLE  = 2'd0;
    localparam BYTE1 = 2'd1;
    localparam BYTE2 = 2'd2;
    localparam BYTE3 = 2'd3;

    reg [1:0] state;
    reg [1:0] next_state;

    // FSM next state wire
    always @(*) begin
        case (state)
            IDLE: begin
                if (in[3] == 1'b1)
                    next_state = BYTE1;
                else
                    next_state = IDLE;
            end
            BYTE1: next_state = BYTE2;
            BYTE2: next_state = BYTE3;
            BYTE3: begin
                if (in[3] == 1'b1)
                    next_state = BYTE1;
                else
                    next_state = IDLE;
            end
            default: next_state = IDLE;
        endcase
    end

    // FSM state register and done signal
    always @(posedge clk) begin
        if (reset) begin
            state <= IDLE;
            done <= 1'b0;
        end else begin
            state <= next_state;
            // done is asserted for one cycle after the third byte is received
            if (state == BYTE2)
                done <= 1'b1;
            else
                done <= 1'b0;
        end
    end

endmodule