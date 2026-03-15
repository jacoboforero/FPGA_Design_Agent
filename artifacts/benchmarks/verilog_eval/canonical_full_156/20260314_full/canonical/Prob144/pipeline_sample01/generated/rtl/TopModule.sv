module TopModule (
    input clk,
    input load,
    input [255:0] data,
    output reg [255:0] q
);

    // Internal wire for next state
    reg [255:0] q_next;

    integer row, col;
    integer dr, dc;
    integer nrow, ncol;
    integer idx, nidx;
    integer i, j;
    reg [3:0] neighbor_count;
    reg cell_state;

    // Combinational wire for next state
    always @* begin
        for (row = 0; row < 16; row = row + 1) begin
            for (col = 0; col < 16; col = col + 1) begin
                neighbor_count = 0;
                idx = row * 16 + col;
                // Count neighbors
                for (dr = -1; dr <= 1; dr = dr + 1) begin
                    for (dc = -1; dc <= 1; dc = dc + 1) begin
                        if (!(dr == 0 && dc == 0)) begin
                            // Wrap around (toroidal)
                            nrow = (row + dr + 16) % 16;
                            ncol = (col + dc + 16) % 16;
                            nidx = nrow * 16 + ncol;
                            neighbor_count = neighbor_count + q[nidx];
                        end
                    end
                end
                cell_state = q[idx];
                // Apply rules
                if (neighbor_count == 2)
                    q_next[idx] = cell_state;
                else if (neighbor_count == 3)
                    q_next[idx] = 1'b1;
                else
                    q_next[idx] = 1'b0;
            end
        end
    end

    // Sequential wire for state update
    always @(posedge clk) begin
        if (load)
            q <= data;
        else
            q <= q_next;
    end

endmodule