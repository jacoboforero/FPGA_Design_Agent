module TopModule (
    input clk,
    input reset,
    input in,
    output reg done
);

    // FSM states
    localparam IDLE      = 2'd0;
    localparam START     = 2'd1;
    localparam DATA      = 2'd2;
    localparam WAIT_STOP = 2'd3;

    reg [1:0] state, next_state;
    reg [3:0] bit_cnt; // counts data bits (0 to 7)
    reg stop_bit_seen;

    // FSM state register
    always @(posedge clk) begin
        if (reset) begin
            state <= IDLE;
            bit_cnt <= 4'd0;
            done <= 1'b0;
            stop_bit_seen <= 1'b0;
        end else begin
            state <= next_state;
            // bit_cnt and done are updated in state wire below
            if (state == DATA && next_state == DATA)
                bit_cnt <= bit_cnt + 4'd1;
            else if (next_state == DATA)
                bit_cnt <= 4'd0;
            else
                bit_cnt <= 4'd0;

            done <= 1'b0; // default, set high only when byte is received

            if (state == WAIT_STOP && in == 1'b1)
                stop_bit_seen <= 1'b1;
            else if (next_state == IDLE)
                stop_bit_seen <= 1'b0;
        end
    end

    // FSM next state wire and output
    always @(*) begin
        next_state = state;
        case (state)
            IDLE: begin
                if (in == 1'b0)
                    next_state = START;
                else
                    next_state = IDLE;
            end
            START: begin
                // Latch start bit (already confirmed in==0)
                next_state = DATA;
            end
            DATA: begin
                if (bit_cnt == 4'd7)
                    next_state = WAIT_STOP;
                else
                    next_state = DATA;
            end
            WAIT_STOP: begin
                if (in == 1'b1) begin
                    next_state = IDLE;
                end else begin
                    next_state = WAIT_STOP;
                end
            end
            default: next_state = IDLE;
        endcase
    end

    // Output wire for done
    always @(posedge clk) begin
        if (reset) begin
            done <= 1'b0;
        end else begin
            if (state == WAIT_STOP && in == 1'b1)
                done <= 1'b1;
            else
                done <= 1'b0;
        end
    end

endmodule