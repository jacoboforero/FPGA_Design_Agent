"""
test_qwen_gateway.py - Test script for Qwen3:4b local gateway

Run from the same directory as gateway.py and adapter_qwen34b.py

Requirements:
- Ollama running locally with qwen3:4b pulled
- httpx installed: pip install httpx
"""

import asyncio
from adapters.llm.gateway import Message, MessageRole, GenerationConfig
from adapters.llm.adapter_qwen34b import Qwen34BLocalGateway


async def main():
    print("Initializing Qwen3:4b gateway...")
    gateway = Qwen34BLocalGateway(ollama_base_url="http://localhost:11434")
    
    print(f"Model: {gateway.model_name}")
    print(f"Provider: {gateway.provider}")
    print(f"Supports files: {gateway.supports_files}")
    print()
    
    # Test 1: Simple generation
    print("Test 1: Simple SystemVerilog generation")
    print("-" * 50)
    messages = [
        Message(role=MessageRole.USER, content="Write a simple 8-bit counter module in SystemVerilog")
    ]
    
    config = GenerationConfig(
        temperature=0.7,
        max_tokens=500
    )
    
    response = await gateway.generate(messages, config)
    
    print(f"Generated content:\n{response.content}\n")
    print(f"Input tokens: {response.input_tokens}")
    print(f"Output tokens: {response.output_tokens}")
    print(f"Total tokens: {response.total_tokens}")
    print(f"Cost: ${response.estimated_cost_usd}")
    print(f"Finish reason: {response.finish_reason}")
    print(f"Timestamp: {response.timestamp}")
    print()
    
    # Test 2: With system prompt
    print("Test 2: With system prompt")
    print("-" * 50)
    messages = [
        Message(role=MessageRole.SYSTEM, content="You are an expert SystemVerilog designer. Write clean, well-commented code."),
        Message(role=MessageRole.USER, content="Create a simple UART transmitter")
    ]
    
    response = await gateway.generate(messages)
    print(f"Generated content (first 200 chars):\n{response.content[:200]}...")
    print(f"Total tokens: {response.total_tokens}")
    print()
    
    # Test 3: With file attachment (simulated)
    print("Test 3: With file attachment")
    print("-" * 50)
    
    # Simulate a SystemVerilog file
    sv_code = """module broken_counter(
    input wire clk,
    input wire rst,
    output reg [7:0] count
);
    always @(posedge clk) begin
        if (rst)
            count <= 8'b0;
        else
            count <= count + 1;  // Missing non-blocking assignment
    end
endmodule"""
    
    messages = [
        Message(
            role=MessageRole.USER,
            content="Review this SystemVerilog code and suggest improvements:",
            attachments=[
                {"filename": "counter.sv", "content": sv_code}
            ]
        )
    ]
    
    response = await gateway.generate(messages)
    print(f"Review response (first 300 chars):\n{response.content[:300]}...")
    print(f"Total tokens: {response.total_tokens}")
    print()
    
    print("All tests completed successfully!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
    except Exception as e:
        print(f"\nError during testing: {e}")
        import traceback
        traceback.print_exc()
