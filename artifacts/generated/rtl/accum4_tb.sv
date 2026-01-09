`timescale 1ns/1ps

module accum4_tb;
  reg clk;
  reg rst_n;
  reg en;
  reg [3:0] in_data;
  wire [3:0] accum;

  accum4 dut (
    .clk(clk), .rst_n(rst_n), .en(en), .in_data(in_data), .accum(accum)
  );

  initial begin
    $display("Running stub TB for accum4");
    clk = '0;
    rst_n = '0;
    en = '0;
    in_data = '0;
    #5;
    clk = 1'b1;
    #5;
    $display("Observed accum=%h", accum);
    #5;
    $finish;
  end
endmodule