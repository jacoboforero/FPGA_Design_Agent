# example_anthropic_gemini.py - Examples using Claude and Gemini

import asyncio
from gateway import Message, MessageRole, GenerationConfig
from gateway.transport import create_transport_by_provider
from gateway.adapters.adapter_anthropic import AnthropicGateway
from gateway.adapters.adapter_gemini import GeminiGateway


async def example_anthropic_claude():
    """Example: Using Anthropic Claude"""
    print("=" * 60)
    print("Example: Anthropic Claude 3.5 Sonnet")
    print("=" * 60)
    
    # Create Anthropic transport
    transport = create_transport_by_provider(
        "anthropic",
        api_key="sk-ant-api03-...",  # Replace with your API key
        anthropic_version="2023-06-01",
    )
    
    # Create Claude gateway
    gateway = AnthropicGateway(
        transport=transport,
        model="claude-3-5-sonnet-20241022",
    )
    
    print(f"Model: {gateway.model_name}")
    print(f"Provider: {gateway.provider}")
    print(f"Supports files: {gateway.supports_files}")
    print()
    
    # Simple generation
    messages = [
        Message(
            role=MessageRole.SYSTEM,
            content="You are a helpful AI assistant specialized in Python programming."
        ),
        Message(
            role=MessageRole.USER,
            content="Write a Python function to calculate the Fibonacci sequence."
        ),
    ]
    
    config = GenerationConfig(
        temperature=0.7,
        max_tokens=1000,
    )
    
    try:
        response = await gateway.generate(messages, config)
        
        print("Response:")
        print(response.content[:500] + "..." if len(response.content) > 500 else response.content)
        print(f"\nTokens - Input: {response.input_tokens}, Output: {response.output_tokens}")
        print(f"Cost: ${response.estimated_cost_usd:.6f}")
        print(f"Finish reason: {response.finish_reason}")
        
    except Exception as e:
        print(f"Error: {e}")


async def example_google_gemini():
    """Example: Using Google Gemini"""
    print("\n" + "=" * 60)
    print("Example: Google Gemini 1.5 Flash")
    print("=" * 60)
    
    # Create Gemini transport
    transport = create_transport_by_provider(
        "gemini",
        api_key="AIza...",  # Replace with your API key
    )
    
    # Create Gemini gateway
    gateway = GeminiGateway(
        transport=transport,
        model="gemini-1.5-flash",
    )
    
    print(f"Model: {gateway.model_name}")
    print(f"Provider: {gateway.provider}")
    print(f"Supports files: {gateway.supports_files}")
    print()
    
    # Simple generation
    messages = [
        Message(
            role=MessageRole.SYSTEM,
            content="You are a creative writing assistant."
        ),
        Message(
            role=MessageRole.USER,
            content="Write a haiku about machine learning."
        ),
    ]
    
    config = GenerationConfig(
        temperature=0.9,
        max_tokens=100,
        top_k=40,
    )
    
    try:
        response = await gateway.generate(messages, config)
        
        print("Response:")
        print(response.content)
        print(f"\nTokens - Input: {response.input_tokens}, Output: {response.output_tokens}")
        print(f"Cost: ${response.estimated_cost_usd:.6f}")
        print(f"Finish reason: {response.finish_reason}")
        
    except Exception as e:
        print(f"Error: {e}")


async def example_multi_provider_comparison():
    """Example: Compare responses from multiple providers"""
    print("\n" + "=" * 60)
    print("Example: Multi-Provider Comparison")
    print("=" * 60)
    
    prompt = "Explain quantum entanglement in one sentence."
    
    providers = [
        {
            "name": "Claude 3.5 Sonnet",
            "transport": create_transport_by_provider(
                "anthropic",
                api_key="sk-ant-...",
            ),
            "gateway_class": AnthropicGateway,
            "model": "claude-3-5-sonnet-20241022",
        },
        {
            "name": "Gemini 1.5 Flash",
            "transport": create_transport_by_provider(
                "gemini",
                api_key="AIza...",
            ),
            "gateway_class": GeminiGateway,
            "model": "gemini-1.5-flash",
        },
    ]
    
    messages = [
        Message(role=MessageRole.USER, content=prompt)
    ]
    
    config = GenerationConfig(temperature=0.7, max_tokens=100)
    
    for provider_config in providers:
        print(f"\n{provider_config['name']}:")
        print("-" * 40)
        
        try:
            gateway = provider_config["gateway_class"](
                transport=provider_config["transport"],
                model=provider_config["model"],
            )
            
            response = await gateway.generate(messages, config)
            
            print(f"Response: {response.content}")
            print(f"Tokens: {response.total_tokens}")
            print(f"Cost: ${response.estimated_cost_usd:.6f}")
            
        except Exception as e:
            print(f"Error: {e}")


async def example_with_file_attachment():
    """Example: Using file attachments with Claude"""
    print("\n" + "=" * 60)
    print("Example: File Analysis with Claude")
    print("=" * 60)
    
    transport = create_transport_by_provider(
        "anthropic",
        api_key="sk-ant-...",
    )
    
    gateway = AnthropicGateway(
        transport=transport,
        model="claude-3-5-sonnet-20241022",
    )
    
    # Simulate a code file
    python_code = """
def calculate_factorial(n):
    if n < 0:
        return None
    result = 1
    for i in range(1, n + 1):
        result *= i
    return result

# Test
print(calculate_factorial(5))
"""
    
    messages = [
        Message(
            role=MessageRole.USER,
            content="Review this Python code and suggest improvements:",
            attachments=[
                {
                    "filename": "factorial.py",
                    "content": python_code,
                }
            ]
        )
    ]
    
    config = GenerationConfig(
        temperature=0.5,
        max_tokens=1000,
    )
    
    try:
        response = await gateway.generate(messages, config)
        
        print("Claude's Review:")
        print(response.content)
        print(f"\nCost: ${response.estimated_cost_usd:.6f}")
        
    except Exception as e:
        print(f"Error: {e}")


async def example_conversation_history():
    """Example: Multi-turn conversation"""
    print("\n" + "=" * 60)
    print("Example: Multi-Turn Conversation with Gemini")
    print("=" * 60)
    
    transport = create_transport_by_provider(
        "gemini",
        api_key="AIza...",
    )
    
    gateway = GeminiGateway(
        transport=transport,
        model="gemini-1.5-flash",
    )
    
    # Build conversation history
    conversation = [
        Message(
            role=MessageRole.SYSTEM,
            content="You are a math tutor helping a student learn algebra."
        ),
        Message(
            role=MessageRole.USER,
            content="What is a quadratic equation?"
        ),
        Message(
            role=MessageRole.ASSISTANT,
            content="A quadratic equation is a polynomial equation of degree 2, typically written as ax² + bx + c = 0, where a, b, and c are constants and a ≠ 0."
        ),
        Message(
            role=MessageRole.USER,
            content="Can you give me an example?"
        ),
    ]
    
    config = GenerationConfig(
        temperature=0.7,
        max_tokens=500,
    )
    
    try:
        response = await gateway.generate(conversation, config)
        
        print("Conversation:")
        for msg in conversation:
            if msg.role != MessageRole.SYSTEM:
                print(f"\n{msg.role.value.upper()}: {msg.content[:100]}...")
        
        print(f"\nASSISTANT: {response.content}")
        print(f"\nTotal tokens: {response.total_tokens}")
        print(f"Cost: ${response.estimated_cost_usd:.6f}")
        
    except Exception as e:
        print(f"Error: {e}")


async def main():
    """Run all examples"""
    print("Anthropic Claude & Google Gemini Examples")
    print("=" * 60)
    print("Note: Replace API keys with your actual keys")
    print()
    
    # Uncomment to run (requires valid API keys)
    # await example_anthropic_claude()
    # await example_google_gemini()
    # await example_multi_provider_comparison()
    # await example_with_file_attachment()
    # await example_conversation_history()
    
    print("\nTo run examples, uncomment them and add your API keys!")


if __name__ == "__main__":
    asyncio.run(main())
