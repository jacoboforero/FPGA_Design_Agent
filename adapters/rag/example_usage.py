"""
Example: How agents can use the RAG service.

This shows how to integrate RAG into agent workers.
"""
from __future__ import annotations

from adapters.rag.rag_service import VerilogRAGService, init_rag_service
from adapters.llm.gateway import Message, MessageRole, GenerationConfig


async def example_agent_with_rag():
    """
    Example of how an agent worker can use RAG.
    
    This pattern can be used in:
    - agents/implementation/worker.py
    - agents/testbench/worker.py
    - agents/spec_helper/worker.py
    """
    # Initialize RAG service (typically done once in __init__)
    rag_service = init_rag_service()
    
    # If RAG is not enabled, rag_service will be None
    if not rag_service:
        print("RAG not enabled. Set USE_RAG=1 to enable.")
        return
    
    # Example: Implementation agent needs to generate RTL
    user_query = "Create a mod-10 counter with enable and reset"
    
    # Option 1: Get context and build your own prompt
    context_str, retrieved_nodes = rag_service.retrieve_context(user_query, top_k=4)
    
    # Use context in your system/user prompts
    system_prompt = (
        "You are an RTL Implementation Agent. Generate synthesizable SystemVerilog.\n"
        f"Here are relevant examples from the knowledge base:\n{context_str}\n"
        "Rules: use always_ff for sequential logic, always_comb for combinational."
    )
    
    user_prompt = f"Module name: counter_mod10\n{user_query}"
    
    # Option 2: Use the built-in prompt builder
    # augmented_prompt = rag_service.build_augmented_prompt(user_query)
    # Then use this prompt with your LLM gateway
    
    # After generating code with LLM, update RAG memory
    generated_code = """
    module counter_mod10 (
        input logic clk,
        input logic rst_n,
        input logic en,
        output logic [3:0] count
    );
        always_ff @(posedge clk or negedge rst_n) begin
            if (!rst_n) count <= 4'b0;
            else if (en) count <= (count == 9) ? 4'b0 : count + 1;
        end
    endmodule
    """
    
    # Store the generated design in RAG memory
    inserted_modules = rag_service.update_memory(user_query, generated_code)
    print(f"Stored modules: {inserted_modules}")


def example_integration_with_implementation_worker():
    """
    Example showing how to modify ImplementationWorker to use RAG.
    
    This would go in agents/implementation/worker.py
    """
    # In __init__:
    # self.rag_service = init_rag_service()
    
    # In _llm_generate_impl method:
    """
    async def _llm_generate_impl(self, ctx, node_id: str) -> Tuple[str, str]:
        iface = ctx["interface"]["signals"]
        port_lines = []
        for sig in iface:
            dir_kw = sig["direction"].lower()
            name = sig["name"]
            width = sig.get("width", 1)
            port_lines.append(...)
        
        # Use RAG to get relevant context
        user_query = f"Module name: {node_id}\nPorts:\n" + "\\n".join(f"- {p}" for p in port_lines)
        
        if self.rag_service:
            context_str, _ = self.rag_service.retrieve_context(user_query, top_k=4)
            system = (
                "You are an RTL Implementation Agent. Generate synthesizable SystemVerilog.\\n"
                f"Relevant examples:\\n{context_str}\\n"
                "Rules: use always_ff for sequential logic..."
            )
        else:
            system = (
                "You are an RTL Implementation Agent. Generate synthesizable SystemVerilog.\\n"
                "Rules: use always_ff for sequential logic..."
            )
        
        user = user_query + "\\nImplement a simple passthrough/placeholder consistent with interface."
        
        msgs = [
            Message(role=MessageRole.SYSTEM, content=system),
            Message(role=MessageRole.USER, content=user),
        ]
        cfg = GenerationConfig(temperature=0.2, max_tokens=600)
        resp = await self.gateway.generate(messages=msgs, config=cfg)
        
        # Update RAG memory with generated code
        if self.rag_service:
            self.rag_service.update_memory(user_query, resp.content)
        
        return resp.content, f"LLM generation via {resp.provider}/{resp.model_name}"
    """


if __name__ == "__main__":
    import asyncio
    
    print("RAG Integration Example")
    print("=" * 60)
    asyncio.run(example_agent_with_rag())

