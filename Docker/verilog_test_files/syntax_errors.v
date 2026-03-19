// This file has intentional syntax errors

module syntax_errors (
    input  wire clk,
    input  wire rst_n,
    output reg [7:0] data
);

    // Error 1: Missing semicolon
    reg [7:0] temp

    // Error 2: Missing 'begin' keyword
    always @(posedge clk)
        if (rst_n)
            data <= 8'hFF;
        else
            data <= 8'h00;
        // Missing 'end' here

    // Error 3: Unterminated comment
    /* This comment never closes

endmodule
