module counter3 (
    input clk,
    input rst_n,
    input en,
    output reg [2:0] count,
    output reg rollover
);

always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        count <= 3'b000;
        rollover <= 1'b0;
    end else begin
        if (en) begin
            if (count == 3'b111) begin
                count <= 3'b000;
                rollover <= 1'b1;
            end else begin
                count <= count + 1'b1;
                rollover <= 1'b0;
            end
        end else begin
            // hold count and rollover low
            count <= count;
            rollover <= 1'b0;
        end
    end
end

endmodule