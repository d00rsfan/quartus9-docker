module smoke(input wire clk, output reg [3:0] led);
    always @(posedge clk)
        led <= led + 1'b1;
endmodule
