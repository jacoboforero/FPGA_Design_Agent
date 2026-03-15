module TopModule (
    input         clk,
    input         areset,
    input         predict_valid,
    input  [6:0]  predict_pc,
    output reg    predict_taken,
    output reg [6:0] predict_history,
    input         train_valid,
    input         train_taken,
    input         train_mispredicted,
    input  [6:0]  train_history,
    input  [6:0]  train_pc
);

    // 128-entry, 2-bit saturating counter PHT
    reg [1:0] pht [0:127];

    // 7-bit global history register
    reg [6:0] global_history;
    reg [6:0] global_history_next;

    integer i;

    // Compute indices for prediction and training
    wire [6:0] predict_index = predict_pc ^ global_history;
    wire [6:0] train_index   = train_pc   ^ train_history;

    // Read PHT for prediction
    wire [1:0] pht_predict = pht[predict_index];

    // Output combinational wire for prediction
    always @(*) begin
        // Output the history used for this prediction
        predict_history = global_history;
        // Predict taken if MSB of counter is 1 (2 or 3)
        predict_taken = pht_predict[1];
    end

    // Next value for global_history
    always @(*) begin
        // Default: hold value
        global_history_next = global_history;
        if (train_valid && train_mispredicted) begin
            // On mispredict, recover history to train_history updated with train_taken
            global_history_next = {train_history[5:0], train_taken};
        end else if (predict_valid) begin
            // On prediction, update history with predicted taken
            global_history_next = {global_history[5:0], predict_taken};
        end
        // If both train_valid & train_mispredicted and predict_valid in same cycle,
        // training takes precedence (handled by if-else order)
    end

    // Sequential wire for global_history and PHT
    always @(posedge clk or posedge areset) begin
        if (areset) begin
            global_history <= 7'b0;
            for (i = 0; i < 128; i = i + 1) begin
                pht[i] <= 2'b01; // Weakly not taken (can also use 2'b10 for weakly taken)
            end
        end else begin
            // Update global_history
            global_history <= global_history_next;

            // Train PHT if requested
            if (train_valid) begin
                if (train_taken) begin
                    // Increment saturating counter
                    if (pht[train_index] != 2'b11)
                        pht[train_index] <= pht[train_index] + 2'b01;
                end else begin
                    // Decrement saturating counter
                    if (pht[train_index] != 2'b00)
                        pht[train_index] <= pht[train_index] - 2'b01;
                end
            end
        end
    end

endmodule