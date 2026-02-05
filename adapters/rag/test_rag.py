# I dont have a ranking system for the best 3-5 runs -> add
# Multiple agents writing at once can corrupt JSON, duplicate designs // add a safeguards -> add
# Store full final HDL
#
#
#

#!/usr/bin/env python3
"""
Test script for RAG system integration.

Run this to verify your RAG setup is working correctly.

Usage:
    python3 adapters/rag/test_rag.py
"""
import os
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from adapters.rag.rag_service import VerilogRAGService, init_rag_service


def test_rag_initialization():
    """Test 1: Verify RAG service can be initialized."""
    print("\n" + "=" * 60)
    print("TEST 1: RAG Service Initialization")
    print("=" * 60)

    os.environ["USE_RAG"] = "1"
    rag_service = init_rag_service()

    if rag_service is None:
        print("FAILED: RAG service returned None")
        print("Check the following:")
        print("- USE_RAG=1 is set")
        print("- Ollama is running (ollama list)")
        print("- Required models are installed:")
        print("  * ollama pull llama3")
        print("  * ollama pull nomic-embed-text")
        return False

    print("PASSED: RAG service initialized")
    print(f"Knowledge base: {rag_service.knowledge_base_path}")
    print(f"Memory file: {rag_service.memory_file_path}")
    return rag_service


def test_knowledge_base_loading(rag_service: VerilogRAGService):
    """Test 2: Verify knowledge base is loaded."""
    print("\n" + "=" * 60)
    print("TEST 2: Knowledge Base Loading")
    print("=" * 60)

    if not rag_service.knowledge_base_path.exists():
        print(f"WARNING: Knowledge base file not found: {rag_service.knowledge_base_path}")
        print("Retrieval may be limited.")
        return True

    modules = rag_service.get_available_modules()
    print(f"Loaded {len(modules)} modules from knowledge base")

    if modules:
        print(f"Modules: {', '.join(modules[:5])}")
    else:
        print("No modules detected. Check file format.")

    return True


def test_context_retrieval(rag_service: VerilogRAGService):
    """Test 3: Verify context retrieval works."""
    print("\n" + "=" * 60)
    print("TEST 3: Context Retrieval")
    print("=" * 60)

    queries = ["counter", "flip flop", "module with reset"]
    passed = True

    for query in queries:
        try:
            context, nodes = rag_service.retrieve_context(query, top_k=2)
            print(f"Query: {query}")
            print(f"Retrieved nodes: {len(nodes)}")
            if context:
                print(f"Context length: {len(context)}")
            else:
                print("No context retrieved")
        except Exception as e:
            print(f"FAILED for query '{query}': {e}")
            passed = False

    return passed


def test_memory_operations(rag_service: VerilogRAGService):
    """Test 4: Verify memory operations work."""
    print("\n" + "=" * 60)
    print("TEST 4: Memory Operations")
    print("=" * 60)

    stored = rag_service.get_stored_designs()
    print(f"Stored designs: {len(stored)}")

    test_input = "Create a simple counter"
    test_output = """
module test_counter (
    input logic clk,
    input logic rst_n,
    output logic [3:0] count
);
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) count <= 4'b0;
        else count <= count + 1;
    end
endmodule
"""

    try:
        inserted = rag_service.update_memory(test_input, test_output)
        print("Memory update successful")
        if inserted:
            print(f"Inserted modules: {', '.join(inserted)}")

        if rag_service.memory_file_path.exists():
            print("Memory file exists")
        else:
            print("Memory file not found")

        return True
    except Exception as e:
        print(f"FAILED: {e}")
        return False


def test_prompt_building(rag_service: VerilogRAGService):
    """Test 5: Verify prompt building works."""
    print("\n" + "=" * 60)
    print("TEST 5: Prompt Building")
    print("=" * 60)

    try:
        query = "Create a mod-10 counter"
        prompt = rag_service.build_augmented_prompt(query, top_k=2)
        print("Prompt built successfully")
        print(f"Prompt length: {len(prompt)}")
        print(prompt[:200])
        return True
    except Exception as e:
        print(f"FAILED: {e}")
        return False


def test_integration_with_llm_gateway():
    """Test 6: Verify integration pattern."""
    print("\n" + "=" * 60)
    print("TEST 6: LLM Integration Pattern")
    print("=" * 60)

    try:
        rag_service = init_rag_service()
        if not rag_service:
            print("SKIPPED: RAG not enabled")
            return True

        query = "Create a counter module"
        context, nodes = rag_service.retrieve_context(query, top_k=2)

        if context:
            system_prompt = (
                "You are an RTL Implementation Agent.\n"
                f"Relevant examples:\n{context}\n"
                "Generate synthesizable SystemVerilog."
            )
        else:
            system_prompt = "You are an RTL Implementation Agent."

        print("Integration pattern works")
        print(f"Prompt length: {len(system_prompt)}")
        print(f"Context nodes: {len(nodes)}")
        return True

    except Exception as e:
        print(f"FAILED: {e}")
        return False


def main():
    print("\n" + "=" * 60)
    print("RAG System Test Suite")
    print("=" * 60)

    results = []

    rag_service = test_rag_initialization()
    if not rag_service:
        sys.exit(1)

    results.append(True)
    results.append(test_knowledge_base_loading(rag_service))
    results.append(test_context_retrieval(rag_service))
    results.append(test_memory_operations(rag_service))
    results.append(test_prompt_building(rag_service))
    results.append(test_integration_with_llm_gateway())

    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"Tests passed: {sum(results)}/{len(results)}")

    if all(results):
        print("All tests passed. RAG system is ready.")
    else:
        print("Some tests failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
