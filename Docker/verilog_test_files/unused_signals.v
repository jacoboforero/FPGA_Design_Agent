// This file has unused signals and variables

module unused_signals (
    input  wire       clk,
    input  wire       rst_n,
    input  wire [7:0] data_in,     // Unused input
    output reg  [7:0] data_out
);

    // Error 1: Declared but never used
    wire unused_wire;
    
    // Error 2: Assigned but never read
    reg [7:0] temp_value;
    
    // Error 3: Declared but never assigned
    reg [3:0] never_assigned;
    
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            data_out <= 8'h00;
            temp_value <= 8'h00;  // Assigned but never used
        end else begin
            data_out <= 8'hAA;     // Constant, ignores data_in
            temp_value <= 8'hBB;   // Assigned but never used
        end
    end
    
    // never_assigned is never given a value
    // unused_wire is never connected or used

endmodule
