module TopModule (
    input clk,
    input in,
    input reset,
    output reg [7:0] out_byte,
    output reg done
);

    // FSM states
    localparam IDLE  = 2'd0;
    localparam DATA  = 2'd1;
    localparam STOP  = 2'd2;

    reg [1:0] state;
    reg [3:0] bit_cnt;
    reg [7:0] data_shift;

    always @(posedge clk) begin
        if (reset) begin
            state <= IDLE;
            bit_cnt <= 4'd0;
            data_shift <= 8'd0;
            out_byte <= 8'd0;
            done <= 1'b0;
        end else begin
            done <= 1'b0;
            case (state)
                IDLE: begin
                    if (in == 1'b0) begin
                        // Detected start bit, begin sampling data bits next cycle
                        state <= DATA;
                        bit_cnt <= 4'd0;
                    end
                end
                DATA: begin
                    data_shift <= {in, data_shift[7:1]}; // LSB first
                    if (bit_cnt == 4'd7) begin
                        state <= STOP;
                        bit_cnt <= 4'd0;
                        done <= 1'b1;
                    end else begin
                        bit_cnt <= bit_cnt + 4'd1;
                    end
                end
                STOP: begin
                    if (in == 1'b1) begin
                        out_byte <= data_shift;
                        state <= IDLE;
                    end
                    // If stop bit is not 1, stay in STOP until it is
                end
                default: state <= IDLE;
            endcase
        end
    end

endmodule