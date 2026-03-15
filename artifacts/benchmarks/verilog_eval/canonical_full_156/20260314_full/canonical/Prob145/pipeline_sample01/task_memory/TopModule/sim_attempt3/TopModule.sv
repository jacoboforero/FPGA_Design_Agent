module TopModule (
    input clock,
    input a,
    output reg p,
    output reg q
);

    reg a_prev;

    always @(posedge clock) begin
        // p is a pulse: high for one clock when a transitions 0->1
        p <= (~a_prev) & a;

        // q is set when a==1, reset when a==0 and q was previously 1
        if (a)
            q <= 1'b1;
        else if (q)
            q <= 1'b0;

        a_prev <= a;
    end

    initial begin
        p = 1'b0;
        q = 1'b0;
        a_prev = 1'b0;
    end

endmodule