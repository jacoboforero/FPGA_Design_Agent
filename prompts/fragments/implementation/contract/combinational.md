Combinational contract: do not use edge-triggered always blocks (no posedge/negedge). Implement with continuous assign and/or $always_keyword only, with zero internal cycle-to-cycle state.
