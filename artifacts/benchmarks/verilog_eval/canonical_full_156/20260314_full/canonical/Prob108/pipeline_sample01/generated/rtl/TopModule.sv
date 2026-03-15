module TopModule (
    input        clk,
    input        load,
    input  [511:0] data,
    output reg [511:0] q
);

    integer i;
    reg [511:0] next_q;

    always @* begin
        // Compute next_q based on Rule 90
        // Boundaries: q[-1]=0, q[512]=0
        next_q[0] = 0 ^ q[1];
        for (i = 1; i < 511; i = i + 1) begin
            next_q[i] = q[i-1] ^ q[i+1];
        end
        next_q[511] = q[510] ^ 0;
    end

    always @(posedge clk) begin
        if (load) begin
            q <= data;
        end else begin
            q <= next_q;
        end
    end

endmodule