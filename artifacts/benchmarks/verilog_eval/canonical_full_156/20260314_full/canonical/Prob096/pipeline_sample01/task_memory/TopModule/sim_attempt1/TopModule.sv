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

    reg [1:0] state;
    reg found;

    always @(posedge clk) begin
        if (reset) begin
            state <= S0;
            found <= 1'b0;
        end else begin
            if (!found) begin
                case (state)
                    S0: begin
                        if (data)
                            state <= S1;
                        else
                            state <= S0;
                    end
                    S1: begin
                        if (data)
                            state <= S2;
                        else
                            state <= S0;
                    end
                    S2: begin
                        if (!data)
                            state <= S3;
                        else
                            state <= S2;
                    end
                    S3: begin
                        if (data) begin
                            found <= 1'b1;
                            state <= S0; // state doesn't matter after found, but reset to S0
                        end else begin
                            state <= S0;
                        end
                    end
                    default: state <= S0;
                endcase
            end
        end
    end

    always @(posedge clk) begin
        if (reset)
            start_shifting <= 1'b0;
        else if (found)
            start_shifting <= 1'b1;
    end

endmodule