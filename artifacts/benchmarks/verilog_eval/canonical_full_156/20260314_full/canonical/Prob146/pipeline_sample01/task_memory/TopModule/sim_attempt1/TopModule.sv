module TopModule (
    input clk,
    input in,
    input reset,
    output reg [7:0] out_byte,
    output reg done
);

    // FSM states
    localparam IDLE     = 2'd0;
    localparam START    = 2'd1;
    localparam DATA     = 2'd2;
    localparam STOP     = 2'd3;

    reg [1:0] state, next_state;
    reg [2:0] bit_cnt;
    reg [7:0] data_shift;

    // FSM state register and outputs
    always @(posedge clk) begin
        if (reset) begin
            state <= IDLE;
            bit_cnt <= 3'd0;
            data_shift <= 8'd0;
            out_byte <= 8'd0;
            done <= 1'b0;
        end else begin
            state <= next_state;
            case (state)
                IDLE: begin
                    done <= 1'b0;
                    if (in == 1'b0) begin
                        // Detected start bit
                        bit_cnt <= 3'd0;
                    end
                end
                START: begin
                    // Latch start bit, prepare for data
                    done <= 1'b0;
                end
                DATA: begin
                    // Shift in data bits, LSB first
                    data_shift <= {in, data_shift[7:1]};
                    bit_cnt <= bit_cnt + 3'd1;
                    done <= 1'b0;
                end
                STOP: begin
                    if (in == 1'b1) begin
                        // Valid stop bit
                        out_byte <= data_shift;
                        done <= 1'b1;
                    end else begin
                        done <= 1'b0;
                    end
                end
                default: begin
                    done <= 1'b0;
                end
            endcase
        end
    end

    // FSM next state wire
    always @(*) begin
        case (state)
            IDLE: begin
                if (in == 1'b0)
                    next_state = START;
                else
                    next_state = IDLE;
            end
            START: begin
                // Move to DATA state on next clock
                next_state = DATA;
            end
            DATA: begin
                if (bit_cnt == 3'd7)
                    next_state = STOP;
                else
                    next_state = DATA;
            end
            STOP: begin
                if (in == 1'b1)
                    next_state = IDLE;
                else
                    next_state = STOP;
            end
            default: next_state = IDLE;
        endcase
    end

endmodule