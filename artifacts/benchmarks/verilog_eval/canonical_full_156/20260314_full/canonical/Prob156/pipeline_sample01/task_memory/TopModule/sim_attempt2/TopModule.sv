module TopModule (
    input  clk,
    input  reset,
    input  data,
    output reg [3:0] count,
    output reg counting,
    output reg done,
    input  ack
);

    // FSM states
    localparam S_IDLE      = 3'd0;
    localparam S_DETECT1   = 3'd1;
    localparam S_DETECT11  = 3'd2;
    localparam S_DETECT110 = 3'd3;
    localparam S_LOAD      = 3'd4;
    localparam S_COUNT     = 3'd5;
    localparam S_DONE      = 3'd6;

    reg [2:0] state, next_state;

    // For pattern detection and delay loading
    reg [1:0] load_cnt;         // Counts 0..3 for 4 bits
    reg [3:0] delay_reg;        // Holds loaded delay value

    // For counting
    reg [3:0] remain;           // Remaining count value
    reg [9:0] cycle_cnt;        // Counts 0..999

    // FSM state register
    always @(posedge clk) begin
        if (reset)
            state <= S_IDLE;
        else
            state <= next_state;
    end

    // FSM next state wire
    always @* begin
        case (state)
            S_IDLE: begin
                if (data)
                    next_state = S_DETECT1;
                else
                    next_state = S_IDLE;
            end
            S_DETECT1: begin
                if (data)
                    next_state = S_DETECT11;
                else
                    next_state = S_IDLE;
            end
            S_DETECT11: begin
                if (~data)
                    next_state = S_DETECT110;
                else
                    next_state = S_DETECT11;
            end
            S_DETECT110: begin
                if (data)
                    next_state = S_LOAD;
                else
                    next_state = S_IDLE;
            end
            S_LOAD: begin
                if (load_cnt == 2'd3)
                    next_state = S_COUNT;
                else
                    next_state = S_LOAD;
            end
            S_COUNT: begin
                if ((remain == 4'd0) && (cycle_cnt == 10'd999))
                    next_state = S_DONE;
                else
                    next_state = S_COUNT;
            end
            S_DONE: begin
                if (ack)
                    next_state = S_IDLE;
                else
                    next_state = S_DONE;
            end
            default: next_state = S_IDLE;
        endcase
    end

    // Sequential wire for pattern detection, delay loading, and counting
    always @(posedge clk) begin
        if (reset) begin
            load_cnt   <= 2'd0;
            delay_reg  <= 4'd0;
            remain     <= 4'd0;
            cycle_cnt  <= 10'd0;
            count      <= 4'd0;
            counting   <= 1'b0;
            done       <= 1'b0;
        end else begin
            case (state)
                S_IDLE: begin
                    load_cnt   <= 2'd0;
                    delay_reg  <= 4'd0;
                    remain     <= 4'd0;
                    cycle_cnt  <= 10'd0;
                    count      <= 4'd0;
                    counting   <= 1'b0;
                    done       <= 1'b0;
                end
                S_DETECT1,
                S_DETECT11,
                S_DETECT110: begin
                    load_cnt   <= 2'd0;
                    delay_reg  <= 4'd0;
                    remain     <= 4'd0;
                    cycle_cnt  <= 10'd0;
                    count      <= 4'd0;
                    counting   <= 1'b0;
                    done       <= 1'b0;
                end
                S_LOAD: begin
                    // Shift in 4 bits, MSB first
                    delay_reg <= {delay_reg[2:0], data};
                    if (load_cnt != 2'd3)
                        load_cnt <= load_cnt + 2'd1;
                    else
                        load_cnt <= 2'd0; // Prepare for next time
                    remain    <= remain; // Will be set in S_COUNT
                    cycle_cnt <= 10'd0;
                    count     <= 4'd0;
                    counting  <= 1'b0;
                    done      <= 1'b0;
                end
                S_COUNT: begin
                    counting <= 1'b1;
                    done     <= 1'b0;
                    if (cycle_cnt == 10'd999) begin
                        cycle_cnt <= 10'd0;
                        if (remain != 4'd0)
                            remain <= remain - 4'd1;
                        // else remain stays at 0
                    end else begin
                        cycle_cnt <= cycle_cnt + 10'd1;
                    end
                    count <= remain;
                end
                S_DONE: begin
                    counting  <= 1'b0;
                    done      <= 1'b1;
                    count     <= 4'd0;
                    // Wait for ack, nothing else changes
                end
                default: begin
                    load_cnt   <= 2'd0;
                    delay_reg  <= 4'd0;
                    remain     <= 4'd0;
                    cycle_cnt  <= 10'd0;
                    count      <= 4'd0;
                    counting   <= 1'b0;
                    done       <= 1'b0;
                end
            endcase

            // Special: when entering S_COUNT, load remain from delay_reg (MSB-first fix)
            if ((state == S_LOAD) && (next_state == S_COUNT)) begin
                remain    <= {delay_reg[0], delay_reg[1], delay_reg[2], delay_reg[3]}; // Reverse bits for MSB-first
                count     <= {delay_reg[0], delay_reg[1], delay_reg[2], delay_reg[3]};
                cycle_cnt <= 10'd0;
            end
        end
    end

endmodule