Task:
- DUT module: $node_id
- Required TB module: $tb_module
- Port list:
$port_lines

- DUT input ports (TB may drive): $dut_inputs
- DUT output ports (observe-only, TB must never drive): $dut_outputs
- DUT inout ports (avoid driving unless explicitly required): $dut_inouts

Normalized testbench contract:
$tb_contract_summary

Behavior summary:
$behavior

Verification summary:
$verification_summary

Generate the full testbench now.
