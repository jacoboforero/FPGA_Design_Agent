module TopModule (
    input clk,
    input reset,
    input s,
    input w,
    output reg z
);

    // State encoding
    localparam STATE_A = 1'b0;
    localparam STATE_B = 1'b1;

    reg state;
    reg [1:0] w_count;    // Counts number of w==1 in current 3-cycle window
    reg [1:0] cycle_cnt;  // Counts cycles in current 3-cycle window
    reg pending_z;        // Holds z value to be output in next cycle

    always @(posedge clk) begin
        if (reset) begin
            state     <= STATE_A;
            w_count   <= 2'b00;
            cycle_cnt <= 2'b00;
            z         <= 1'b0;
            pending_z <= 1'b0;
        end else begin
            case (state)
                STATE_A: begin
                    z <= 1'b0;
                    pending_z <= 1'b0;
                    if (s) begin
                        state     <= STATE_B;
                        w_count   <= w ? 2'b01 : 2'b00;
                        cycle_cnt <= 2'b01;
                    end
                end
                STATE_B: begin
                    z <= pending_z;
                    if (cycle_cnt == 2'b11) begin
                        // End of 3-cycle window, compute pending_z for next cycle
                        w_count <= w ? w_count + 1'b1 : w_count;
                        if ((w ? w_count + 1'b1 : w_count) == 2'b10) begin
                            pending_z <= 1'b1;
                        end else begin
                            pending_z <= 1'b0;
                        end
                        // Start next window
                        w_count   <= 2'b00;
                        cycle_cnt <= 2'b01;
                    end else begin
                        // Continue counting in window
                        if (w) begin
                            w_count <= w_count + 1'b1;
                        end
                        cycle_cnt <= cycle_cnt + 1'b1;
                        pending_z <= 1'b0;
                    end
                end
                default: begin
                    state     <= STATE_A;
                    w_count   <= 2'b00;
                    cycle_cnt <= 2'b00;
                    z         <= 1'b0;
                    pending_z <= 1'b0;
                end
            endcase
        end
    end

endmodule