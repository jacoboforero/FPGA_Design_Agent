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

    reg [1:0] state, next_state;
    reg [7:0] byte1, byte2, byte3;

    // FSM state register
    always @(posedge clk) begin
        if (reset) begin
            state <= S_IDLE;
        end else begin
            state <= next_state;
        end
    end

    // FSM next state wire and datapath
    always @(*) begin
        next_state = state;
        case (state)
            S_IDLE: begin
                if (in[3]) begin
                    next_state = S_B1;
                end
            end
            S_B1: begin
                next_state = S_B2;
            end
            S_B2: begin
                next_state = S_B3;
            end
            S_B3: begin
                if (in[3]) begin
                    next_state = S_B1;
                end else begin
                    next_state = S_IDLE;
                end
            end
            default: next_state = S_IDLE;
        endcase
    end

    // Datapath and outputs
    always @(posedge clk) begin
        if (reset) begin
            byte1     <= 8'd0;
            byte2     <= 8'd0;
            byte3     <= 8'd0;
            out_bytes <= 24'd0;
            done      <= 1'b0;
        end else begin
            done <= 1'b0;
            case (state)
                S_IDLE: begin
                    // Wait for in[3]==1
                    if (in[3]) begin
                        byte1 <= in;
                    end
                end
                S_B1: begin
                    byte2 <= in;
                end
                S_B2: begin
                    byte3 <= in;
                end
                S_B3: begin
                    out_bytes <= {byte1, byte2, byte3};
                    done      <= 1'b1;
                    // Prepare for next message if in[3]==1
                    if (in[3]) begin
                        byte1 <= in;
                    end
                end
            endcase
        end
    end

endmodule