module TopModule (
    input clk,
    input reset,
    input in,
    output reg done
);

    // FSM states
    localparam IDLE      = 2'd0;
    localparam DATA      = 2'd1;
    localparam WAIT_STOP = 2'd2;
    localparam DONE      = 2'd3;

    reg [1:0] state;
    reg [3:0] bit_cnt;

    always @(posedge clk) begin
        if (reset) begin
            state <= IDLE;
            bit_cnt <= 4'd0;
            done <= 1'b0;
        end else begin
            case (state)
                IDLE: begin
                    done <= 1'b0;
                    bit_cnt <= 4'd0;
                    if (in == 1'b0) begin
                        state <= DATA;
                        bit_cnt <= 4'd0;
                    end else begin
                        state <= IDLE;
                    end
                end
                DATA: begin
                    done <= 1'b0;
                    bit_cnt <= bit_cnt + 4'd1;
                    if (bit_cnt == 4'd7) begin
                        state <= WAIT_STOP;
                    end else begin
                        state <= DATA;
                    end
                end
                WAIT_STOP: begin
                    done <= 1'b0;
                    if (in == 1'b1) begin
                        state <= DONE;
                    end else begin
                        state <= WAIT_STOP;
                    end
                end
                DONE: begin
                    done <= 1'b1;
                    state <= IDLE;
                    bit_cnt <= 4'd0;
                end
                default: begin
                    state <= IDLE;
                    done <= 1'b0;
                    bit_cnt <= 4'd0;
                end
            endcase
        end
    end

endmodule