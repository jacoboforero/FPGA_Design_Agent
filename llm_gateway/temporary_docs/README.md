

# =============================================================================
# README.md
"""
# LLM Gateway

Unified interface for multiple LLM providers with transport abstraction.

## Features

- 🔌 **Transport Layer**: Separate communication protocol from model logic
- 🤖 **Multiple Providers**: OpenAI, Anthropic, local (Ollama, HuggingFace)
- 🔄 **Easy Switching**: Change hosting without changing model code
- 📦 **Auto-Discovery**: Add new transports by creating new files
- 🎯 **Type Safe**: Full Pydantic validation and type hints

## Quick Start

```python
from gateway import create_transport_by_provider
from gateway.adapters import Qwen34BLocalGateway

# Create transport
transport = create_transport_by_provider(
    "ollama",
    base_url="http://localhost:11434"
)

# Create model adapter
gateway = Qwen34BLocalGateway(transport=transport)

# Use it
from gateway import Message, MessageRole

messages = [
    Message(role=MessageRole.USER, content="Hello!")
]

response = await gateway.generate(messages)
print(response.content)
```

## Installation

```bash
# Basic installation
pip install -e .

# With development tools
pip install -e ".[dev]"

# With specific provider support
pip install -e ".[openai]"
pip install -e ".[all]"
```

## Architecture

```
Transport Layer (How to talk to servers)
    ↓
Model Adapters (How to work with specific models)
    ↓
Your Application
```

## Adding a New Transport

Create `gateway/transport/transport_myservice.py`:

```python
from .base import TransportProtocol

class MyServiceTransport(TransportProtocol):
    # Implement abstract methods
    pass
```

That's it! Auto-discovered and ready to use.

## Documentation

See `docs/` directory for:
- Architecture overview
- Adding transports guide
- Adding adapters guide
- API reference

## License

MIT
"""