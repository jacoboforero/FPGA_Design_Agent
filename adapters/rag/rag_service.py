"""
Verilog RAG Service - Adapted for FPGA Design Agent system.

Provides retrieval-augmented generation capabilities for Verilog/SystemVerilog
design assistance. Can be used by agents to retrieve relevant context before
calling the LLM gateway.
"""
from __future__ import annotations

import json
import os
import re
from collections import deque
from pathlib import Path
from typing import List, Optional, Tuple

from llama_index.core import Document, PromptTemplate, Settings, VectorStoreIndex
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.llms.ollama import Ollama


# Memory config
SHORT_TERM_WINDOW = 8  # recent turns kept in RAM only

# Default memory file location (can be overridden)
DEFAULT_MEMORY_FILE = "verilog_rag_memory.json"


DEFAULT_KNOWLEDGE_BASE_FILE = "verilog_knowledge_base.txt"

# Prompt template 
CONVERSATIONAL_PROMPT = PromptTemplate(
    """
You are a Verilog/SystemVerilog hardware design assistant.

You have:
- A library of existing modules (from files).
- A library of previously generated/stored designs (long-term memory).
- Recent conversation context (short-term memory).

Guidelines:
- Provide working SystemVerilog code (or Verilog if appropriate).
- Follow style from context modules.
- Include clear headers and brief comments.
- For complex tasks, show how modules connect.
- Keep explanations minimal and focused on design clarity.

Recent conversation + user request:
{query_str}

Relevant context from knowledge base (modules + stored designs):
{context_str}

Now provide the best possible answer:
""".strip()
)


class VerilogRAGService:
    """
    RAG service for Verilog/SystemVerilog design assistance.
    
    Provides context retrieval and memory management for agents.
    Can be initialized once and reused across multiple agent calls.
    """

    def __init__(
        self,
        knowledge_base_path: Optional[str] = None,
        memory_file_path: Optional[str] = None,
        ollama_model: str = "llama3",
        ollama_embedding_model: str = "nomic-embed-text",
        temperature: float = 0.1,
    ):
        """
        Initialize the RAG service.
        
        Args:
            knowledge_base_path: Path to Verilog knowledge base text file
            memory_file_path: Path to JSON file for long-term memory persistence
            ollama_model: Ollama model name for LLM
            ollama_embedding_model: Ollama model name for embeddings
            temperature: Temperature for LLM generation
        """
        # Set up LLM and embeddings
        Settings.llm = Ollama(model=ollama_model, temperature=temperature)
        Settings.embed_model = OllamaEmbedding(model_name=ollama_embedding_model)

        # Set paths
        self.knowledge_base_path = Path(knowledge_base_path or DEFAULT_KNOWLEDGE_BASE_FILE)
        self.memory_file_path = Path(memory_file_path or DEFAULT_MEMORY_FILE)

        # Load knowledge base
        self.base_docs = self._load_verilog_modules_from_txt(self.knowledge_base_path)

        # Load long-term memory
        self.memory_data = self._load_long_term_memory()
        design_docs = self._designs_to_docs(self.memory_data)

        # Build index with base docs + stored designs
        all_docs = self.base_docs + design_docs
        self.index = VectorStoreIndex.from_documents(all_docs)

        # Short-term memory (in-RAM only, per session)
        self.short_term_history: deque = deque(maxlen=SHORT_TERM_WINDOW)

    def _load_long_term_memory(self) -> dict:
        """Load persisted memory from previous runs."""
        if not self.memory_file_path.exists():
            return {"designs": []}

        try:
            with open(self.memory_file_path, "r") as f:
                data = json.load(f)
            if "designs" not in data or not isinstance(data["designs"], list):
                return {"designs": []}
            return data
        except Exception:
            return {"designs": []}

    def _save_long_term_memory(self) -> None:
        """Persist memory dict to disk."""
        try:
            with open(self.memory_file_path, "w") as f:
                json.dump(self.memory_data, f, indent=2)
        except Exception as e:
            print(f"[RAG Memory] Failed to save long-term memory: {e}")

    def _extract_design_summaries(self, user_input: str, assistant_output: str) -> List[dict]:
        """
        Extract important design info from assistant output.
        Covers:
        - module name (with optional parameters)
        - port signature (if present)
        """
        designs = []

        # Pattern 1: module NAME #(params)? (ports) ;
        module_pattern_ports = r"\bmodule\s+([A-Za-z_]\w*)\s*(?:#\s*\(.*?\)\s*)?\(\s*(.*?)\s*\)\s*;"
        modules = re.findall(module_pattern_ports, assistant_output, re.DOTALL)

        # Pattern 2: module NAME ;
        module_pattern_noports = r"\bmodule\s+([A-Za-z_]\w*)\s*;"
        modules_noports = re.findall(module_pattern_noports, assistant_output)

        seen = set()

        # With ports
        for module_name, port_block in modules:
            signature = f"module {module_name}(" + " ".join(port_block.split()) + ");"
            if (module_name, signature) in seen:
                continue
            seen.add((module_name, signature))

            summary_match = re.search(
                rf"\b{re.escape(module_name)}\b[^.]*\.", assistant_output
            )
            summary = (
                summary_match.group(0).strip()
                if summary_match
                else f"{module_name}: Generated HDL module."
            )

            designs.append(
                {
                    "module_name": module_name,
                    "summary": summary,
                    "signature": signature,
                    "tags": ["generated_design", "verilog_rag"],
                }
            )

        # No ports (only if not already captured)
        for module_name in modules_noports:
            signature = f"module {module_name};"
            if any(d["module_name"] == module_name for d in designs):
                continue
            if (module_name, signature) in seen:
                continue
            seen.add((module_name, signature))

            designs.append(
                {
                    "module_name": module_name,
                    "summary": f"{module_name}: Generated HDL module (no explicit ports in header).",
                    "signature": signature,
                    "tags": ["generated_design", "verilog_rag"],
                }
            )

        return designs

    def _designs_to_docs(self, memory_data: dict) -> List[Document]:
        """Convert stored designs into Documents so they are part of RAG context."""
        docs = []
        for d in memory_data.get("designs", []):
            text = (
                f"// STORED DESIGN SUMMARY\n"
                f"// Module: {d['module_name']}\n"
                f"// Summary: {d['summary']}\n"
                f"// Signature: {d['signature']}\n"
            )
            docs.append(
                Document(
                    text=text,
                    metadata={
                        "topic": "stored_design",
                        "module_name": d["module_name"],
                        "tags": ",".join(d.get("tags", [])),
                    },
                )
            )
        return docs

    def _load_verilog_modules_from_txt(self, file_path: Path) -> List[Document]:
        """Load Verilog modules from text file and split into documents."""
        if not file_path.exists():
            print(f"[RAG] Warning: Knowledge base file not found: {file_path}")
            return []

        try:
            with open(file_path, "r") as f:
                content = f.read()

            # Format:
            # // MODULE: name
            # module ... endmodule
            module_pattern = r"// MODULE:\s*(\w+)\s*(module\s+\w+.*?endmodule)"
            matches = re.findall(module_pattern, content, re.DOTALL)

            docs = []
            for module_name, module_code in matches:
                clean_code = module_code.strip()
                docs.append(
                    Document(
                        text=clean_code,
                        metadata={
                            "file_name": str(file_path.name),
                            "topic": "verilog_modules",
                            "tags": module_name,
                            "module_name": module_name,
                        },
                    )
                )

            print(f"[RAG] Loaded {len(docs)} modules from {file_path}")
            return docs

        except Exception as e:
            print(f"[RAG] Error reading knowledge base file: {e}")
            return []

    def _build_augmented_query_for_llm(self, user_input: str) -> str:
        """Short-term memory is appended ONLY for the LLM (not for retrieval)."""
        if not self.short_term_history:
            return f"User: {user_input}"

        history_lines = []
        for turn in self.short_term_history:
            history_lines.append(f"User: {turn['user']}")
            history_lines.append(f"Assistant: {turn['assistant']}")

        history_block = "\n".join(history_lines[-2 * SHORT_TERM_WINDOW :])
        return history_block + f"\nUser: {user_input}"

    def _build_context_str_from_nodes(self, nodes: List, max_chars: int = 6000) -> str:
        """Compact context builder from retrieved nodes."""
        parts = []
        total = 0
        for node in nodes:
            text = node.get_content()
            md = node.metadata or {}
            header = (
                f"// SOURCE topic={md.get('topic','')} "
                f"module={md.get('module_name', md.get('tags','unknown'))}\n"
            )
            chunk = header + text.strip() + "\n"
            if total + len(chunk) > max_chars:
                break
            parts.append(chunk)
            total += len(chunk)
        return "\n".join(parts).strip()

    def retrieve_context(
        self, query: str, top_k: int = 4, include_history: bool = True
    ) -> Tuple[str, List]:
        """
        Retrieve relevant context for a query.
        
        Args:
            query: User query/question
            top_k: Number of top results to retrieve
            include_history: Whether to include short-term conversation history
            
        Returns:
            Tuple of (context_string, retrieved_nodes)
        """
        retriever = self.index.as_retriever(similarity_top_k=top_k)
        nodes = retriever.retrieve(query)
        context_str = self._build_context_str_from_nodes(nodes)
        return context_str, nodes

    def build_augmented_prompt(
        self, user_query: str, context_str: Optional[str] = None, top_k: int = 4
    ) -> str:
        """
        Build an augmented prompt with retrieved context.
        
        Args:
            user_query: The user's query
            context_str: Optional pre-retrieved context (if None, will retrieve)
            top_k: Number of top results to retrieve if context_str is None
            
        Returns:
            Formatted prompt string ready for LLM
        """
        if context_str is None:
            context_str, _ = self.retrieve_context(user_query, top_k=top_k)

        llm_query = self._build_augmented_query_for_llm(user_query)
        prompt = CONVERSATIONAL_PROMPT.format(
            query_str=llm_query, context_str=context_str
        )
        return prompt

    def update_memory(self, user_input: str, assistant_output: str) -> List[str]:
        """
        Store new design summaries to disk AND insert into index immediately.
        
        Args:
            user_input: User's input that led to this output
            assistant_output: Assistant's generated output
            
        Returns:
            List of newly inserted module names
        """
        new_designs = self._extract_design_summaries(user_input, assistant_output)
        if not new_designs:
            return []

        existing = {
            (d["module_name"], d["signature"]) for d in self.memory_data.get("designs", [])
        }
        inserted_modules = []

        for d in new_designs:
            key = (d["module_name"], d["signature"])
            if key in existing:
                continue

            self.memory_data.setdefault("designs", []).append(d)
            existing.add(key)

            # Insert into index now (so retrieval can find it right away)
            doc_text = (
                f"// STORED DESIGN SUMMARY\n"
                f"// Module: {d['module_name']}\n"
                f"// Summary: {d['summary']}\n"
                f"// Signature: {d['signature']}\n"
            )
            doc = Document(
                text=doc_text,
                metadata={
                    "topic": "stored_design",
                    "module_name": d["module_name"],
                    "tags": ",".join(d.get("tags", [])),
                },
            )

            try:
                self.index.insert(doc)
                inserted_modules.append(d["module_name"])
                print(
                    f"[RAG Memory] Stored + indexed design summary for module: {d['module_name']}"
                )
            except Exception as e:
                print(
                    f"[RAG Memory] Stored to JSON but FAILED to index module {d['module_name']}: {e}"
                )

        # Save to disk
        self._save_long_term_memory()

        # Update short-term memory
        self.short_term_history.append({"user": user_input, "assistant": assistant_output})

        return inserted_modules

    def get_available_modules(self) -> List[str]:
        """Get list of available module names from knowledge base."""
        return sorted(
            {doc.metadata.get("module_name", "unknown") for doc in self.base_docs}
        )

    def get_stored_designs(self) -> List[str]:
        """Get list of stored design module names."""
        return sorted(
            {d.get("module_name", "unknown") for d in self.memory_data.get("designs", [])}
        )


def init_rag_service(
    knowledge_base_path: Optional[str] = None,
    memory_file_path: Optional[str] = None,
) -> Optional[VerilogRAGService]:
    """
    Initialize RAG service from environment variables or defaults.
    
    Environment variables:
        USE_RAG: Set to "1" to enable RAG (default: disabled)
        RAG_KNOWLEDGE_BASE: Path to knowledge base file (default: verilog_knowledge_base.txt)
        RAG_MEMORY_FILE: Path to memory file (default: verilog_rag_memory.json)
        OLLAMA_MODEL: Ollama model name (default: llama3)
        OLLAMA_EMBEDDING_MODEL: Ollama embedding model (default: nomic-embed-text)
        OLLAMA_TEMPERATURE: Temperature for LLM (default: 0.1)
    
    Returns:
        VerilogRAGService instance if enabled, None otherwise
    """
    if os.getenv("USE_RAG") != "1":
        return None

    try:
        knowledge_base = knowledge_base_path or os.getenv(
            "RAG_KNOWLEDGE_BASE", DEFAULT_KNOWLEDGE_BASE_FILE
        )
        memory_file = memory_file_path or os.getenv(
            "RAG_MEMORY_FILE", DEFAULT_MEMORY_FILE
        )
        ollama_model = os.getenv("OLLAMA_MODEL", "llama3")
        ollama_embedding = os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
        temperature = float(os.getenv("OLLAMA_TEMPERATURE", "0.1"))

        return VerilogRAGService(
            knowledge_base_path=knowledge_base,
            memory_file_path=memory_file,
            ollama_model=ollama_model,
            ollama_embedding_model=ollama_embedding,
            temperature=temperature,
        )
    except Exception as e:
        print(f"[RAG] Failed to initialize RAG service: {e}")
        return None

