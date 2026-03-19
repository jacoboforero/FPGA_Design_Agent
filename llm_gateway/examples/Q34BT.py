"""
Q34BT.py - Simple test for Qwen3:4b with full JSON ModelResponse output

Run from the same directory as gateway.py and adapter_qwen34b.py
"""

import asyncio
import json
from llm_gateway.gateway import Message, MessageRole, GenerationConfig
from llm_gateway.adapters.adapter_qwen34b import Qwen34BLocalGateway


async def main():
    print("Initializing Qwen3:4b gateway...")
    gateway = Qwen34BLocalGateway(ollama_base_url="http://localhost:11434")
    
    print("Generating SystemVerilog counter module...")
    print()
    
    messages = [
        Message(role=MessageRole.USER, content="Write a simple 8-bit counter module in SystemVerilog. ONLY provide output code; DO NOT provide thinking.")
    ]
    
    config = GenerationConfig(
        temperature=0.03,
        max_tokens=30000
    )
    
    response = await gateway.generate(messages, config)
    
    # Convert ModelResponse to dict for JSON serialization
    response_dict = response.model_dump()
    
    # Pretty print the JSON
    print("=" * 80)
    print("FULL MODEL RESPONSE (JSON)")
    print("=" * 80)
    print(json.dumps(response_dict, indent=2, default=str))
    print("=" * 80)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
    except Exception as e:
        print(f"\nError during testing: {e}")
        import traceback
        traceback.print_exc()
