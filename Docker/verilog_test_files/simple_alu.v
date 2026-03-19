// Simple 8-bit ALU (Arithmetic Logic Unit)
// Demonstrates combinational logic

module simple_alu (
    input  wire [7:0] a,          // First operand
    input  wire [7:0] b,          // Second operand
    input  wire [2:0] op,         // Operation select
    output reg  [7:0] result,     // ALU result
    output reg        zero_flag   // Result is zero
);

    // Operation encoding
    localparam OP_ADD = 3'b000;
    localparam OP_SUB = 3'b001;
    localparam OP_AND = 3'b010;
    localparam OP_OR  = 3'b011;
    localparam OP_XOR = 3'b100;
    localparam OP_NOT = 3'b101;
    localparam OP_SLL = 3'b110;  // Shift left logical
    localparam OP_SRL = 3'b111;  // Shift right logical

    // Combinational ALU logic
    always @(*) begin
        case (op)
            OP_ADD: result = a + b;
            OP_SUB: result = a - b;
            OP_AND: result = a & b;
            OP_OR:  result = a | b;
            OP_XOR: result = a ^ b;
            OP_NOT: result = ~a;
            OP_SLL: result = a << b[2:0];
            OP_SRL: result = a >> b[2:0];
            default: result = 8'h00;
        endcase
        
        // Set zero flag
        zero_flag = (result == 8'h00);
    end

endmodule
