# RAG Quick Start Guide

Get your RAG system up and running in 5 minutes!

## Step 1: Install Dependencies

```bash
# Install llama_index packages
pip install llama-index-core llama-index-llms-ollama llama-index-embeddings-ollama

# Or add to pyproject.toml:
# llama-index-core = "^0.10.0"
# llama-index-llms-ollama = "^0.1.0"
# llama-index-embeddings-ollama = "^0.1.0"
```

## Step 2: Set Up Ollama

```bash
# Install Ollama (if not already installed)
# macOS: brew install ollama
# Linux: curl -fsSL https://ollama.ai/install.sh | sh

# Start Ollama (usually auto-starts)
ollama serve

# Install required models
ollama pull llama3
ollama pull nomic-embed-text

# Verify models are installed
ollama list
```

## Step 3: Create Knowledge Base

```bash
# Copy the example file
cp adapters/rag/verilog_knowledge_base.txt.example verilog_knowledge_base.txt

# Or create your own with Verilog modules in this format:
# // MODULE: module_name
# module module_name (...) ... endmodule
```

## Step 4: Set Environment Variables

```bash
export USE_RAG=1

# Optional: customize paths
export RAG_KNOWLEDGE_BASE=verilog_knowledge_base.txt
export RAG_MEMORY_FILE=verilog_rag_memory.json
```

## Step 5: Run Tests

```bash
# Run the test suite
python3 adapters/rag/test_rag.py
```

You should see:
```
✅ PASSED: RAG service initialized successfully
✅ PASSED: Loaded X modules from knowledge base
✅ PASSED: Context retrieval works
✅ PASSED: Memory operations work
✅ PASSED: Prompt building works
✅ PASSED: Integration pattern works
✅ All tests passed! RAG system is ready to use.
```

## Step 6: Use in Your Agents

```python
from adapters.rag.rag_service import init_rag_service

class YourAgent(AgentWorkerBase):
    def __init__(self, connection_params, stop_event):
        super().__init__(connection_params, stop_event)
        self.rag_service = init_rag_service()  # Add this
    
    async def handle_task(self, task):
        # Retrieve context
        if self.rag_service:
            context, _ = self.rag_service.retrieve_context("your query", top_k=4)
            # Use context in your prompt
        
        # ... generate code ...
        
        # Update memory
        if self.rag_service:
            self.rag_service.update_memory(query, generated_code)
```

## Troubleshooting

**"RAG service returned None"**
- Check `USE_RAG=1` is set: `echo $USE_RAG`
- Verify Ollama is running: `ollama list`
- Check models are installed: `ollama list | grep llama3`

**"Knowledge base file not found"**
- Create the file: `cp adapters/rag/verilog_knowledge_base.txt.example verilog_knowledge_base.txt`
- Or set custom path: `export RAG_KNOWLEDGE_BASE=path/to/your/file.txt`

**Import errors**
- Install packages: `pip install llama-index-core llama-index-llms-ollama llama-index-embeddings-ollama`

**Ollama connection errors**
- Start Ollama: `ollama serve`
- Check it's running: `curl http://localhost:11434/api/tags`

## Next Steps

1. ✅ Run tests to verify setup
2. ✅ Add more modules to your knowledge base
3. ✅ Integrate into your agents (see `example_usage.py`)
4. ✅ Generate some code and watch RAG memory grow!

For more details, see [README.md](README.md).

