"""
RAG (Retrieval-Augmented Generation) adapter for the FPGA Design Agent system.

Provides context retrieval from Verilog/SystemVerilog knowledge base.
"""

from adapters.rag.rag_service import VerilogRAGService, init_rag_service

__all__ = ["VerilogRAGService", "init_rag_service"]

