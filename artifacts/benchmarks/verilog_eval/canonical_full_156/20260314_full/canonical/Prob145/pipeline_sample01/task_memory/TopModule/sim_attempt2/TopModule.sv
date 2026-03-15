module TopModule (
    input clock,
    input a,
    output reg p,
    output reg q
);

    always @(posedge clock) begin
        // p is 1 on posedge clock if a==1, else 0
        p <= a;

        // q is set to 1 if a==1, stays 1 until a==0, then resets to 0
        if (a)
            q <= 1'b1;
        else
            q <= 1'b0;
    end

    initial begin
        p = 1'b0;
        q = 1'b0;
    end

endmodule