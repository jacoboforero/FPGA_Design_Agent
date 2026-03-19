// Simple 8-bit counter with synchronous reset
// This is a complete, self-contained module for Verilator testing

module simple_counter (
    input  wire       clk,      // Clock input
    input  wire       rst_n,    // Active-low reset
    input  wire       enable,   // Counter enable
    output reg  [7:0] count     // 8-bit counter output
);

    // Counter logic
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            // Reset counter to zero
            count <= 8'h00;
        end else if (enable) begin
            // Increment counter when enabled
            count <= count + 1'b1;
        end
        // If enable is low, count holds its value
    end

endmodule
