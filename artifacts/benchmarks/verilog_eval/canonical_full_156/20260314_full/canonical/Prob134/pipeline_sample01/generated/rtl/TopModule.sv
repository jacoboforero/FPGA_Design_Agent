module TopModule (
    input clk,
    input x,
    input [2:0] y,
    output reg Y0,
    output reg z
);

reg [2:0] next_state;

// Next state wire
always @(*) begin
    case (y)
        3'b000: begin
            if (x == 1'b0)
                next_state = 3'b000;
            else
                next_state = 3'b001;
        end
        3'b001: begin
            if (x == 1'b0)
                next_state = 3'b001;
            else
                next_state = 3'b100;
        end
        3'b010: begin
            if (x == 1'b0)
                next_state = 3'b010;
            else
                next_state = 3'b001;
        end
        3'b011: begin
            if (x == 1'b0)
                next_state = 3'b001;
            else
                next_state = 3'b010;
        end
        3'b100: begin
            if (x == 1'b0)
                next_state = 3'b011;
            else
                next_state = 3'b100;
        end
        default: begin
            next_state = 3'b000;
        end
    endcase
end

// Output wire
always @(*) begin
    case (y)
        3'b011,
        3'b100: z = 1'b1;
        default: z = 1'b0;
    endcase
end

// Y0 output is next_state[0]
always @(*) begin
    Y0 = next_state[0];
end

endmodule