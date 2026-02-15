# Test

Follow these steps to test that your RAG integration is working correctly.

## Prerequisites Check

First, let's verify you have everything needed:

### 1. Check Python
```bash
python3 --version
# Should show Python 3.12 or higher
```

### 2. Check if Ollama is installed
```bash
ollama --version
# If not installed, install it:
# macOS: brew install ollama
# Linux: curl -fsSL https://ollama.ai/install.sh | sh
```

### 3. Check if Ollama is running
```bash
ollama list
# Should show your installed models or an empty list
# If error, start Ollama: ollama serve
```

### 4. Install required Ollama models
```bash
ollama pull llama3
ollama pull nomic-embed-text

# Verify they're installed
ollama list
# Should show:
# llama3
# nomic-embed-text
```

### 5. Install Python dependencies
```bash
pip install llama-index-core llama-index-llms-ollama llama-index-embeddings-ollama
```

## Step-by-Step Testing

### Step 1: Create Knowledge Base File

```bash
# From project root
cd /Users/sammy/code/learning-ai/capstone/cli_capstone/FPGA_Design_Agent

# Copy the example file
cp adapters/rag/verilog_knowledge_base.txt.example verilog_knowledge_base.txt

# Or create your own at the project root with this format:
# // MODULE: module_name
# module module_name (...) ... endmodule
```

### Step 2: Set Environment Variable

```bash
export USE_RAG=1

# Verify it's set
echo $USE_RAG
# Should output: 1
```

### Step 3: Run the Test Script

```bash
# From project root
python3 adapters/rag/test_rag.py
```

## What to Expect

### ✅ Success Output

If everything works, you'll see:

```
============================================================
RAG System Test Suite
============================================================

============================================================
TEST 1: RAG Service Initialization
============================================================
✅ PASSED: RAG service initialized successfully
   Knowledge base: verilog_knowledge_base.txt
   Memory file: verilog_rag_memory.json

============================================================
TEST 2: Knowledge Base Loading
============================================================
✅ PASSED: Loaded 4 modules from knowledge base
   Available modules: counter, dff_en_rstn, mod10_counter, shift_register

============================================================
TEST 3: Context Retrieval
============================================================
✅ Query: 'counter'
   Retrieved 2 nodes
   Context length: 450 chars
✅ Query: 'flip flop'
   Retrieved 2 nodes
   Context length: 320 chars
✅ Query: 'module with reset'
   Retrieved 2 nodes
   Context length: 580 chars

============================================================
TEST 4: Memory Operations
============================================================
   Current stored designs: 0
✅ Memory update successful
   Inserted modules: test_counter
✅ Memory file exists: verilog_rag_memory.json

============================================================
TEST 5: Prompt Building
============================================================
✅ Prompt built successfully
   Query: 'Create a mod-10 counter'
   Prompt length: 1250 chars

============================================================
TEST 6: LLM Gateway Integration Pattern
============================================================
✅ Integration pattern works
   System prompt length: 680 chars
   Retrieved 2 context nodes

============================================================
TEST SUMMARY
============================================================
Tests passed: 6/6
✅ All tests passed! RAG system is ready to use.
```

### ❌ Common Errors and Fixes

#### Error: "RAG service returned None"

**Problem**: RAG service couldn't initialize

**Solutions**:
```bash
# 1. Make sure USE_RAG is set
export USE_RAG=1
echo $USE_RAG  # Should output: 1

# 2. Check Ollama is running
ollama list  # Should not error

# 3. Verify models are installed
ollama list | grep llama3
ollama list | grep nomic-embed-text

# 4. If models missing, install them
ollama pull llama3
ollama pull nomic-embed-text
```

#### Error: "Knowledge base file not found"

**Problem**: Can't find the knowledge base file

**Solutions**:
```bash
# 1. Create the file
cp adapters/rag/verilog_knowledge_base.txt.example verilog_knowledge_base.txt

# 2. Or set custom path
export RAG_KNOWLEDGE_BASE=/path/to/your/file.txt

# 3. Verify file exists
ls -la verilog_knowledge_base.txt
```

#### Error: Import errors (ModuleNotFoundError)

**Problem**: Missing Python packages

**Solutions**:
```bash
# Install required packages
pip install llama-index-core llama-index-llms-ollama llama-index-embeddings-ollama

# Or if using poetry
poetry add llama-index-core llama-index-llms-ollama llama-index-embeddings-ollama
```

#### Error: "Connection refused" or Ollama errors

**Problem**: Ollama server not running

**Solutions**:
```bash
# Start Ollama
ollama serve

# In another terminal, verify it's running
curl http://localhost:11434/api/tags

# Or check with
ollama list
```

## Quick Test Command

Run this single command to test everything at once:

```bash
# Make sure you're in project root
cd /Users/sammy/code/learning-ai/capstone/cli_capstone/FPGA_Design_Agent

# Set environment variable
export USE_RAG=1

# Create knowledge base if it doesn't exist
[ ! -f verilog_knowledge_base.txt ] && cp adapters/rag/verilog_knowledge_base.txt.example verilog_knowledge_base.txt

# Run tests
python3 adapters/rag/test_rag.py
```

## Manual Testing (Alternative)

If you prefer to test manually in Python:

```python
# Start Python REPL
python3

# Then run:
from adapters.rag.rag_service import init_rag_service
import os

# Set environment variable
os.environ["USE_RAG"] = "1"

# Initialize RAG
rag = init_rag_service()
print(f"RAG initialized: {rag is not None}")

# Test retrieval
if rag:
    context, nodes = rag.retrieve_context("counter", top_k=2)
    print(f"Retrieved {len(nodes)} nodes")
    print(f"Context preview: {context[:200]}...")
    
    # Test prompt building
    prompt = rag.build_augmented_prompt("Create a counter")
    print(f"Prompt length: {len(prompt)} chars")
    
    print("✅ All manual tests passed!")
```

## Next Steps After Testing

Once tests pass:

1. ✅ **RAG is working!** You can now integrate it into your agents
2. 📝 See `adapters/rag/example_usage.py` for integration examples
3. 🔧 Add more modules to your knowledge base
4. 🚀 Start using RAG in your agent workers

## Need Help?

If tests are failing:
1. Check the error message - it will tell you what's wrong
2. Verify all prerequisites are installed
3. Make sure Ollama is running and models are installed
4. Check that `USE_RAG=1` is set
5. Verify the knowledge base file exists


