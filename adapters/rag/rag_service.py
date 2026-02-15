""""
Verilog RAG Service - Adapted for FPGA Design Agent system.

Provides retrieval-augmented generation capabilities for Verilog/SystemVerilog
design assistance. Can be used by agents to retrieve relevant context before
calling the LLM gateway.

This version supports:
- OpenAI embeddings (recommended)
- Optional Ollama embeddings ONLY if explicitly requested

Important:
- This RAG service does NOT generate with an LLM. It only RETRIEVES context.
- Your agent LLM calls are handled by your LLM gateway (OpenAI/Groq/etc).
"""
from __future__ import annotations

import json
import os
import re
from collections import deque
from pathlib import Path
from typing import Any, List, Optional, Tuple

from llama_index.core import Document, PromptTemplate, Settings, VectorStoreIndex
from llama_index.core.schema import NodeWithScore

# Optional: OpenAI embeddings (used when OPENAI_API_KEY / RAG_EMBEDDING_PROVIDER=openai)
try:
    from llama_index.embeddings.openai import OpenAIEmbedding
except Exception:
    OpenAIEmbedding = None  # type: ignore[misc, assignment]

# Optional: Ollama embeddings (ONLY if RAG_EMBEDDING_PROVIDER=ollama)
try:
    from llama_index.embeddings.ollama import OllamaEmbedding
except Exception:
    OllamaEmbedding = None  # type: ignore[misc, assignment]


# Memory config
SHORT_TERM_WINDOW = 8  # recent turns kept in RAM only

# Default memory file location (can be overridden)
DEFAULT_MEMORY_FILE = "verilog_rag_memory.json"
DEFAULT_KNOWLEDGE_BASE_FILE = "verilog_knowledge_base.txt"

# Ranking: topic boost for preferred source types (higher = prefer in ranking)
RANK_TOPIC_BOOST = {"stored_design": 1.2, "verilog_modules": 1.0}

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

    This class:
    - Loads a static knowledge base (verilog_knowledge_base.txt)
    - Loads persisted memory summaries (verilog_rag_memory.json)
    - Builds a vector index over both
    - Retrieves relevant context for a query
    - Updates memory (JSON + in-process index insert)
    """

    def __init__(
        self,
        knowledge_base_path: Optional[str] = None,
        memory_file_path: Optional[str] = None,
        *,
        embedding_provider: str = "openai",
        openai_api_key: Optional[str] = None,
        openai_embedding_model: str = "text-embedding-3-small",
        ollama_embedding_model: str = "nomic-embed-text",
        rank_topic_boost: Optional[dict] = None,
    ):
        self.rank_topic_boost = rank_topic_boost or dict(RANK_TOPIC_BOOST)

        provider = (embedding_provider or "openai").strip().lower()

        # IMPORTANT: This RAG service only needs embeddings.
        # We explicitly disable any LLM inside LlamaIndex so it never tries Ollama.
        Settings.llm = None  # type: ignore[assignment]

        if provider == "openai":
            api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "RAG embedding provider is openai but OPENAI_API_KEY is not set."
                )
            if OpenAIEmbedding is None:
                raise RuntimeError(
                    "OpenAIEmbedding not available. Install: llama-index-embeddings-openai"
                )

            Settings.embed_model = OpenAIEmbedding(
                model=openai_embedding_model,
                api_key=api_key,
            )
            print(
                f"[RAG] Embeddings provider=openai model={openai_embedding_model}"
            )

        elif provider == "ollama":
            if OllamaEmbedding is None:
                raise RuntimeError(
                    "OllamaEmbedding not available. Install: llama-index-embeddings-ollama"
                )
            Settings.embed_model = OllamaEmbedding(model_name=ollama_embedding_model)
            print(
                f"[RAG] Embeddings provider=ollama model={ollama_embedding_model}"
            )

        else:
            raise RuntimeError(
                f"Unknown RAG_EMBEDDING_PROVIDER='{provider}'. Use 'openai' or 'ollama'."
            )

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
        try:
            with open(self.memory_file_path, "w") as f:
                json.dump(self.memory_data, f, indent=2)
        except Exception as e:
            print(f"[RAG Memory] Failed to save long-term memory: {e}")

    def _extract_design_summaries(self, user_input: str, assistant_output: str) -> List[dict]:
        designs = []

        module_pattern_ports = r"\bmodule\s+([A-Za-z_]\w*)\s*(?:#\s*\(.*?\)\s*)?\(\s*(.*?)\s*\)\s*;"
        modules = re.findall(module_pattern_ports, assistant_output, re.DOTALL)

        module_pattern_noports = r"\bmodule\s+([A-Za-z_]\w*)\s*;"
        modules_noports = re.findall(module_pattern_noports, assistant_output)

        seen = set()

        for module_name, port_block in modules:
            signature = f"module {module_name}(" + " ".join(port_block.split()) + ");"
            if (module_name, signature) in seen:
                continue
            seen.add((module_name, signature))

            summary_match = re.search(rf"\b{re.escape(module_name)}\b[^.]*\.", assistant_output)
            summary = summary_match.group(0).strip() if summary_match else f"{module_name}: Generated HDL module."

            designs.append(
                {
                    "module_name": module_name,
                    "summary": summary,
                    "signature": signature,
                    "tags": ["generated_design", "verilog_rag"],
                }
            )

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
        if not file_path.exists():
            print(f"[RAG] Warning: Knowledge base file not found: {file_path}")
            return []

        try:
            with open(file_path, "r") as f:
                content = f.read()

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
        if not self.short_term_history:
            return f"User: {user_input}"

        history_lines = []
        for turn in self.short_term_history:
            history_lines.append(f"User: {turn['user']}")
            history_lines.append(f"Assistant: {turn['assistant']}")

        history_block = "\n".join(history_lines[-2 * SHORT_TERM_WINDOW :])
        return history_block + f"\nUser: {user_input}"

    def _build_context_str_from_nodes(self, nodes: List, max_chars: int = 6000) -> str:
        parts = []
        total = 0
        for node in nodes:
            n = node.node if isinstance(node, NodeWithScore) else node
            text = n.get_content()
            md = n.metadata or {}
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

    def _rank_nodes(self, node_scores: List[NodeWithScore], top_k: int) -> List[NodeWithScore]:
        def rank_key(nsw: NodeWithScore) -> Tuple[float, str]:
            score = getattr(nsw, "score", None)
            sim = float(score) if score is not None else 0.0
            topic = (nsw.node.metadata or {}).get("topic", "")
            boost = self.rank_topic_boost.get(topic, 1.0)
            return (-(sim * boost), topic)

        sorted_nodes = sorted(node_scores, key=rank_key)
        return sorted_nodes[:top_k]

    def retrieve_context(
        self,
        query: str,
        top_k: int = 4,
        include_history: bool = True,
        retrieve_multiple: int = 2,
    ) -> Tuple[str, List]:
        candidate_k = max(top_k, top_k * retrieve_multiple)
        retriever = self.index.as_retriever(similarity_top_k=candidate_k)
        node_scores = retriever.retrieve(query)

        if node_scores and not isinstance(node_scores[0], NodeWithScore):
            node_scores = [
                n if isinstance(n, NodeWithScore) else NodeWithScore(node=n, score=1.0)
                for n in node_scores
            ]

        ranked = self._rank_nodes(node_scores, top_k)
        context_str = self._build_context_str_from_nodes(ranked)
        return context_str, ranked

    def build_augmented_prompt(self, user_query: str, context_str: Optional[str] = None, top_k: int = 4) -> str:
        if context_str is None:
            context_str, _ = self.retrieve_context(user_query, top_k=top_k)

        llm_query = self._build_augmented_query_for_llm(user_query)
        prompt = CONVERSATIONAL_PROMPT.format(query_str=llm_query, context_str=context_str)
        return prompt

    def update_memory(self, user_input: str, assistant_output: str) -> List[str]:
        new_designs = self._extract_design_summaries(user_input, assistant_output)
        if not new_designs:
            return []

        existing = {(d["module_name"], d["signature"]) for d in self.memory_data.get("designs", [])}
        inserted_modules = []

        for d in new_designs:
            key = (d["module_name"], d["signature"])
            if key in existing:
                continue

            self.memory_data.setdefault("designs", []).append(d)
            existing.add(key)

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
                print(f"[RAG Memory] Stored + indexed design summary for module: {d['module_name']}")
            except Exception as e:
                print(f"[RAG Memory] Stored to JSON but FAILED to index module {d['module_name']}: {e}")

        self._save_long_term_memory()
        self.short_term_history.append({"user": user_input, "assistant": assistant_output})
        return inserted_modules

    def get_available_modules(self) -> List[str]:
        return sorted({doc.metadata.get("module_name", "unknown") for doc in self.base_docs})

    def get_stored_designs(self) -> List[str]:
        return sorted({d.get("module_name", "unknown") for d in self.memory_data.get("designs", [])})


def init_rag_service(
    knowledge_base_path: Optional[str] = None,
    memory_file_path: Optional[str] = None,
) -> Optional[VerilogRAGService]:
    if os.getenv("USE_RAG") != "1":
        return None

    knowledge_base = knowledge_base_path or os.getenv("RAG_KNOWLEDGE_BASE", DEFAULT_KNOWLEDGE_BASE_FILE)
    memory_file = memory_file_path or os.getenv("RAG_MEMORY_FILE", DEFAULT_MEMORY_FILE)

    provider = (os.getenv("RAG_EMBEDDING_PROVIDER") or "openai").strip().lower()
    openai_key = os.getenv("OPENAI_API_KEY")

    if provider == "openai" and not openai_key:
        raise RuntimeError("USE_RAG=1 and RAG_EMBEDDING_PROVIDER=openai but OPENAI_API_KEY is missing.")

    return VerilogRAGService(
        knowledge_base_path=knowledge_base,
        memory_file_path=memory_file,
        embedding_provider=provider,
        openai_api_key=openai_key or None,
        openai_embedding_model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
        ollama_embedding_model=os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text"),
    )
