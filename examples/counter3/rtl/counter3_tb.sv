`timescale 1ns/1ps

module tb_counter3;

reg [2:0] expected_count;
reg expected_rollover;

  reg clk;
  reg rst_n;
  reg en;
  wire [2:0] count;
  wire rollover;

  // Instantiate DUT
  counter3 dut (
    .clk(clk),
    .rst_n(rst_n),
    .en(en),
    .count(count),
    .rollover(rollover)
  );

  // Reference model variables
  reg [2:0] ref_count;
  reg ref_rollover;

  // Cycle counter
  integer cycle;

  // Dump variables
  integer dump_start, dump_end;
  reg dump_enabled;
  reg [2047:0] dump_file;

  // Clock generation: 10 time units period
  initial begin
    clk = 0;
    forever #5 clk = ~clk;
  end

  // Dump control
  initial begin
    dump_enabled = 0;
    dump_start = 0;
    dump_end = 1_000_000; // large default
    dump_file = "dump.vcd";
    if ($test$plusargs("DUMP")) begin
      dump_enabled = 1;
      if (!$value$plusargs("DUMP_FILE=%s", dump_file)) begin
        dump_file = "dump.vcd";
      end
      if (!$value$plusargs("DUMP_START=%d", dump_start)) begin
        dump_start = 0;
      end
      if (!$value$plusargs("DUMP_END=%d", dump_end)) begin
        dump_end = 1_000_000;
      end
    end
  end

  // Dump waveform control
  initial begin
    if (dump_enabled) begin
      $dumpfile(dump_file);
      $dumpvars(0, tb_counter3);
      wait(cycle >= dump_start);
      wait(cycle > dump_end);
      #1 $finish(0);
    end
  end

  // Stimulus generation and reset
  initial begin
    // Initialize inputs
    rst_n = 0;
    en = 0;
    cycle = 0;
    ref_count = 0;
    ref_rollover = 0;

    // Hold reset for some time (at least 1 sampled edge)
    #(12); // > 1 clock cycle (10 units) to cover async reset and 1 post-reset cycle

    rst_n = 1;

    // Wait 1 cycle after reset release for checker gating
    @(posedge clk);
    cycle = cycle + 1;

    // Directed stimulus sequence
    // Cycle 1: en=1 count increments 0->1
    @(negedge clk);
    en = 1;
    @(posedge clk);
    cycle = cycle + 1;

    // Cycle 2: en=1 count increments 1->2
    @(negedge clk);
    en = 1;
    @(posedge clk);
    cycle = cycle + 1;

    // Cycle 3: en=0 hold count=2
    @(negedge clk);
    en = 0;
    @(posedge clk);
    cycle = cycle + 1;

    // Cycle 4: en=1 count increments 2->3
    @(negedge clk);
    en = 1;
    @(posedge clk);
    cycle = cycle + 1;

    // Cycle 5: en=1 count increments 3->4
    @(negedge clk);
    en = 1;
    @(posedge clk);
    cycle = cycle + 1;

    // Cycle 6: en=1 count increments 4->5
    @(negedge clk);
    en = 1;
    @(posedge clk);
    cycle = cycle + 1;

    // Cycle 7: en=1 count increments 5->6
    @(negedge clk);
    en = 1;
    @(posedge clk);
    cycle = cycle + 1;

    // Cycle 8: en=1 count increments 6->7
    @(negedge clk);
    en = 1;
    @(posedge clk);
    cycle = cycle + 1;

    // Cycle 9: en=1 count wraps 7->0 rollover=1
    @(negedge clk);
    en = 1;
    @(posedge clk);
    cycle = cycle + 1;

    // Cycle 10: en=1 count increments 0->1 rollover=0
    @(negedge clk);
    en = 1;
    @(posedge clk);
    cycle = cycle + 1;

    // Cycle 11: en=0 hold count=1 rollover=0
    @(negedge clk);
    en = 0;
    @(posedge clk);
    cycle = cycle + 1;

    // Cycle 12: Apply reset again asynchronously
    rst_n = 0;
    @(posedge clk);
    cycle = cycle + 1;

    // Cycle 13: release reset
    rst_n = 1;
    @(posedge clk);
    cycle = cycle + 1;

    // Cycle 14: en=1 count increments 0->1
    @(negedge clk);
    en = 1;
    @(posedge clk);
    cycle = cycle + 1;

    // Finish test
    $display("PASS cycle=%0d time=%0t count=%0d rollover=%0b", cycle, $time, count, rollover);
    $finish(0);
  end

  // Checker and reference model
  always @(posedge clk) begin
    // Handle reset and checker gating
    #1;
    if (!rst_n) begin
      // During reset expected values forced to zero
      ref_count = 0;
      ref_rollover = 0;
    end else if (cycle <= 1) begin
      // Gate checker for at least 1 sampled edge after reset release
      // Do nothing, keep ref values stable
    end else begin
      // Compute expected_next from previous ref_count and sampled en
      expected_rollover = 0;
      expected_count = ref_count;
      if (en) begin
        if (ref_count == 3'd7) begin
          expected_count = 3'd0;
          expected_rollover = 1;
        end else begin
          expected_count = ref_count + 1;
          expected_rollover = 0;
        end
      end else begin
        expected_count = ref_count;
        expected_rollover = 0;
      end

      // Wait #1 delay before compare
      #1;

      // Compare DUT outputs against expected_next
      if (count !== expected_count) begin
        $display("FAIL count mismatch cycle=%0d time=%0t en=%b count=%0d expected_count=%0d rollover=%b expected_rollover=%b",
          cycle, $time, en, count, expected_count, rollover, expected_rollover);
        $finish(1);
      end
      if (rollover !== expected_rollover) begin
        $display("FAIL rollover mismatch cycle=%0d time=%0t en=%b count=%0d expected_count=%0d rollover=%b expected_rollover=%b",
          cycle, $time, en, count, expected_count, rollover, expected_rollover);
        $finish(1);
      end

      // Commit expected state for next cycle
      ref_count = expected_count;
      ref_rollover = expected_rollover;
    end
  end

endmodule