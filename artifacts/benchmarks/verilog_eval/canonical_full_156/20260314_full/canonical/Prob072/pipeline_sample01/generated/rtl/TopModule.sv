module TopModule (
    input  wire mode,
    input  wire too_cold,
    input  wire too_hot,
    input  wire fan_on,
    output wire heater,
    output wire aircon,
    output wire fan
);

assign heater = mode & too_cold;
assign aircon = (~mode) & too_hot;
assign fan = heater | aircon | fan_on;

endmodule