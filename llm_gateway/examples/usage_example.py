# example_usage.py - Examples of using the transport system

import asyncio
from transport_registry import (
    create_transport_by_provider,
    list_transports,
)


async def example_ollama():
    """Example: Using Ollama transport for local models"""
    print("=" * 60)
    print("Example 1: Ollama Local Transport")
    print("=" * 60)
    
    # Create transport
    transport = create_transport_by_provider(
        "ollama",
        base_url="http://localhost:11434",
        timeout=300.0
    )
    
    print(f"Transport: {transport.transport_name}")
    print(f"Supports streaming: {transport.supports_streaming}")
    print()
    
    # Make a call
    messages = [
        {"role": "user", "content": "Write a haiku about Python"}
    ]
    
    options = {
        "temperature": 0.7,
        "max_tokens": 100,
    }
    
    try:
        response = await transport.call_chat_completion(
            model_id="qwen3:4b",
            messages=messages,
            options=options,
        )
        
        print("Response:")
        print(response["message"]["content"])
        print(f"\nTokens - Input: {response['prompt_eval_count']}, "
              f"Output: {response['eval_count']}")
        
    except Exception as e:
        print(f"Error: {e}")


async def example_huggingface():
    """Example: Using HuggingFace transport for TGI/vLLM servers"""
    print("\n" + "=" * 60)
    print("Example 2: HuggingFace TGI/vLLM Transport")
    print("=" * 60)
    
    transport = create_transport_by_provider(
        "huggingface",
        base_url="http://localhost:8080",
        timeout=300.0
    )
    
    print(f"Transport: {transport.transport_name}")
    print()
    
    messages = [
        {"role": "user", "content": "Explain quantum computing in one sentence"}
    ]
    
    options = {
        "temperature": 0.7,
        "max_tokens": 50,
    }
    
    try:
        response = await transport.call_chat_completion(
            model_id="meta-llama/Llama-3-8b-instruct",
            messages=messages,
            options=options,
        )
        
        print("Response:")
        print(response["choices"][0]["message"]["content"])
        print(f"\nTokens: {response['usage']}")
        
    except Exception as e:
        print(f"Error: {e}")


async def example_openai():
    """Example: Using OpenAI transport"""
    print("\n" + "=" * 60)
    print("Example 3: OpenAI External API Transport")
    print("=" * 60)
    
    # Note: Replace with actual API key
    API_KEY = "sk-your-api-key-here"
    
    transport = create_transport_by_provider(
        "openai",
        api_key=API_KEY,
        organization="org-your-org-id",  # Optional
    )
    
    print(f"Transport: {transport.transport_name}")
    print()
    
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What is the capital of France?"}
    ]
    
    options = {
        "temperature": 0.3,
        "max_tokens": 50,
    }
    
    try:
        response = await transport.call_chat_completion(
            model_id="gpt-5-nano",
            messages=messages,
            options=options,
        )
        
        print("Response:")
        print(response["choices"][0]["message"]["content"])
        print(f"\nModel: {response['model']}")
        print(f"Tokens: {response['usage']}")
        
    except Exception as e:
        print(f"Error: {e}")


async def example_switching_transports():
    """Example: Same model, different transports"""
    print("\n" + "=" * 60)
    print("Example 4: Same Model (DeepSeek), Different Transports")
    print("=" * 60)
    
    # DeepSeek on Ollama
    ollama = create_transport_by_provider(
        "ollama",
        base_url="http://localhost:11434"
    )
    
    # DeepSeek on HuggingFace
    hf = create_transport_by_provider(
        "huggingface",
        base_url="http://localhost:8080"
    )
    
    messages = [
        {"role": "user", "content": "Write a function to calculate factorial"}
    ]
    
    print("Option A: DeepSeek via Ollama")
    try:
        response = await ollama.call_chat_completion(
            model_id="deepseek-coder:6.7b",
            messages=messages,
        )
        print(f"✓ Transport: {ollama.transport_name}")
        print(f"  Response length: {len(response['message']['content'])} chars")
    except Exception as e:
        print(f"✗ Error: {e}")
    
    print("\nOption B: DeepSeek via HuggingFace")
    try:
        response = await hf.call_chat_completion(
            model_id="deepseek-ai/deepseek-coder-6.7b-instruct",
            messages=messages,
        )
        print(f"✓ Transport: {hf.transport_name}")
        print(f"  Response length: {len(response['choices'][0]['message']['content'])} chars")
    except Exception as e:
        print(f"✗ Error: {e}")


def example_list_transports():
    """Example: List all available transports"""
    print("\n" + "=" * 60)
    print("Example 5: List All Available Transports")
    print("=" * 60)
    
    transports = list_transports()
    print(f"Found {len(transports)} transport(s):")
    for transport in transports:
        print(f"  - {transport}")


async def main():
    """Run all examples"""
    print("Transport System Usage Examples")
    print("=" * 60)
    print("Note: Some examples require running services:")
    print("  - Ollama: http://localhost:11434")
    print("  - HuggingFace TGI/vLLM: http://localhost:8080")
    print("  - OpenAI: Valid API key")
    print()
    
    # List available transports first
    example_list_transports()
    
    # Run examples (comment out if services aren't running)
    await example_ollama()
    # await example_huggingface()
    # await example_openai()
    # await example_switching_transports()


if __name__ == "__main__":
    asyncio.run(main())
