"""
RAG helpers for retrieval and long-term design memory.
"""
from adapters.rag.rag_service import (
    RagRetrieval,
    RagUnavailableError,
    VerilogRAGService,
    archive_final_design,
    retrieve_for_stage,
)

__all__ = [
    "RagRetrieval",
    "RagUnavailableError",
    "VerilogRAGService",
    "archive_final_design",
    "retrieve_for_stage",
]
