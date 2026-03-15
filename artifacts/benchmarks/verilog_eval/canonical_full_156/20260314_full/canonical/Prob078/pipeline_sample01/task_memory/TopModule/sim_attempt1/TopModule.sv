module TopModule (
    input clk,
    input d,
    output reg q
);

reg q_pos;
reg q_neg;
reg clk_last;

always @(posedge clk) begin
    q_pos <= d;
end

always @(negedge clk) begin
    q_neg <= d;
end

always @(posedge clk or negedge clk) begin
    clk_last <= clk;
end

always @(*) begin
    if (clk == 1'b1 && clk_last == 1'b0) begin
        // Rising edge: output q_pos
        q = q_pos;
    end else if (clk == 1'b0 && clk_last == 1'b1) begin
        // Falling edge: output q_neg
        q = q_neg;
    end else begin
        // Hold previous value
        q = q;
    end
end

endmodule