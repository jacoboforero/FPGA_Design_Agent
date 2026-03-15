module TopModule (
    input  wire        clk,
    input  wire        reset,
    input  wire [7:0]  in,
    output reg  [23:0] out_bytes,
    output reg         done
);

    // FSM states
    localparam S_IDLE  = 2'd0;
    localparam S_B1    = 2'd1;
    localparam S_B2    = 2'd2;
    localparam S_B3    = 2'd3;

    reg [1:0] state;
    reg [7:0] byte1, byte2, byte3;

    always @(posedge clk) begin
        if (reset) begin
            state     <= S_IDLE;
            byte1     <= 8'd0;
            byte2     <= 8'd0;
            byte3     <= 8'd0;
            out_bytes <= 24'd0;
            done      <= 1'b0;
        end else begin
            done <= 1'b0;
            case (state)
                S_IDLE: begin
                    if (in[3]) begin
                        byte1 <= in;
                        state <= S_B1;
                    end
                end
                S_B1: begin
                    byte2 <= in;
                    state <= S_B2;
                end
                S_B2: begin
                    byte3 <= in;
                    state <= S_B3;
                end
                S_B3: begin
                    out_bytes <= {byte1, byte2, byte3};
                    done <= 1'b1;
                    if (in[3]) begin
                        byte1 <= in;
                        state <= S_B1;
                    end else begin
                        state <= S_IDLE;
                    end
                end
                default: state <= S_IDLE;
            endcase
        end
    end

endmodule