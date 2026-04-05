from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from core.observability.emitter import emit_runtime_event
from core.runtime.config import RagStageConfig, get_runtime_config
from core.runtime.paths import rag_artifacts_root, resolve_rag_workspace_path, resolve_resource_path

_MODULE_BLOCK_RE = re.compile(r"\bmodule\s+([A-Za-z_]\w*)\b.*?\bendmodule\b", re.DOTALL)
_MODULE_HEADER_WITH_PORTS_RE = re.compile(
    r"\bmodule\s+([A-Za-z_]\w*)\s*(?:#\s*\(.*?\)\s*)?\(\s*(.*?)\s*\)\s*;",
    re.DOTALL,
)
_MODULE_HEADER_NO_PORTS_RE = re.compile(r"\bmodule\s+([A-Za-z_]\w*)\s*;", re.DOTALL)
_KB_MODULE_RE = re.compile(r"// MODULE:\s*(\w+)\s*(module\s+\w+.*?endmodule)", re.DOTALL)

_SERVICE_LOCK = threading.RLock()
_SERVICE_INSTANCE: Optional["VerilogRAGService"] = None
_SERVICE_KEY: Optional[tuple[Any, ...]] = None


class RagUnavailableError(RuntimeError):
    """Raised when the configured RAG backend cannot be used."""


@dataclass(frozen=True)
class RagHit:
    module_name: str
    topic: str
    score: float
    summary: str = ""
    rtl_hash: str = ""


@dataclass
class RagRetrieval:
    context_text: str
    hits: list[RagHit] = field(default_factory=list)


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def _short_hash(text: str, n: int = 16) -> str:
    return _hash_text(text)[:n]


def _json_dumps(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True)


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        try:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
        except Exception:
            pass


def _extract_module_signature(rtl: str, module_name: str) -> str:
    match = re.search(
        rf"\bmodule\s+{re.escape(module_name)}\b\s*(?:#\s*\(.*?\)\s*)?\(\s*(.*?)\s*\)\s*;",
        rtl,
        flags=re.DOTALL,
    )
    if match:
        port_block = " ".join(match.group(1).split())
        return f"module {module_name}({port_block});"
    match = re.search(rf"\bmodule\s+{re.escape(module_name)}\b\s*;", rtl)
    if match:
        return f"module {module_name};"
    return f"module {module_name}(/* ports unknown */);"


def _guess_summary(module_name: str, rtl: str) -> str:
    lowered = rtl.lower()
    if "always_ff" in lowered or "posedge" in lowered or "negedge" in lowered:
        return f"{module_name}: sequential RTL with explicit clock/reset behavior."
    if "always_comb" in lowered or "assign " in lowered:
        return f"{module_name}: combinational RTL focused on direct signal transformation."
    if "case" in lowered:
        return f"{module_name}: control-oriented RTL with case-driven behavior."
    return f"{module_name}: reusable RTL implementation."


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    omitted = len(text) - limit
    return f"{text[:limit]}\n// [truncated {omitted} char(s)]"


def _module_names_from_hits(hits: list[RagHit]) -> list[str]:
    seen: list[str] = []
    for hit in hits:
        if hit.module_name and hit.module_name not in seen:
            seen.append(hit.module_name)
    return seen


def _themes_from_hits(hits: list[RagHit]) -> list[str]:
    themes: list[str] = []
    for hit in hits:
        topic = hit.topic.strip()
        if topic and topic not in themes:
            themes.append(topic)
    return themes


def _stage_guidance_summary(stage: str, hit_count: int, module_names: list[str]) -> str:
    if hit_count <= 0:
        return ""
    module_text = ", ".join(module_names[:3])
    if len(module_names) > 3:
        module_text += ", and related designs"
    if stage == "implementation":
        return f"I consulted {hit_count} prior design example(s), including {module_text}, to guide interface shape, reset handling, and RTL structure."
    if stage == "testbench":
        return f"I consulted {hit_count} prior design example(s), including {module_text}, to align timing, checker ordering, and self-check structure."
    if stage == "debug":
        return f"I consulted {hit_count} prior design example(s), including {module_text}, to compare failure patterns and choose a more targeted patch."
    return f"I consulted {hit_count} prior design example(s), including {module_text}, to guide this step."


def _runtime_metadata(stage: str, *, mode: str, used: bool, degraded: bool = False, skip_reason: str | None = None,
                      hit_count: int = 0, retrieved_module_names: Optional[list[str]] = None, themes: Optional[list[str]] = None,
                      applied_guidance_summary: str | None = None, stored_module_names: Optional[list[str]] = None) -> dict[str, Any]:
    return {
        "used": used,
        "mode": mode,
        "stage": stage,
        "degraded": degraded,
        "skip_reason": skip_reason,
        "hit_count": int(hit_count),
        "retrieved_module_names": list(retrieved_module_names or []),
        "themes": list(themes or []),
        "applied_guidance_summary": applied_guidance_summary or "",
        "stored_module_names": list(stored_module_names or []),
    }


def _rag_enabled_for_execution(execution_policy: dict[str, Any] | None = None) -> tuple[bool, str | None]:
    cfg = get_runtime_config().rag
    if not cfg.enabled:
        return False, "disabled"
    policy = execution_policy if isinstance(execution_policy, dict) else {}
    is_benchmark = (
        bool(policy.get("benchmark_mode"))
        or str(policy.get("run_kind", "")).strip().lower() == "benchmark"
        or bool(str(policy.get("benchmark_flow_mode", "")).strip())
    )
    if is_benchmark and not bool(cfg.allow_benchmark):
        return False, "benchmark_disabled"
    return True, None


def _stage_config(stage: str) -> RagStageConfig:
    cfg = get_runtime_config().rag
    stage_cfg = getattr(cfg, stage, None)
    if isinstance(stage_cfg, RagStageConfig):
        return stage_cfg
    raise RagUnavailableError(f"Unknown RAG retrieval stage '{stage}'.")


def _import_llama_index(embedding_provider: str) -> tuple[Any, Any, Any, Any]:
    try:
        from llama_index.core import Document, Settings, VectorStoreIndex
        from llama_index.core.llms.mock import MockLLM
        from llama_index.core.schema import NodeWithScore
    except Exception as exc:  # noqa: BLE001
        raise RagUnavailableError(
            "RAG dependencies missing. Install llama-index and the embedding packages before enabling RAG."
        ) from exc

    if embedding_provider == "openai":
        try:
            from llama_index.embeddings.openai import OpenAIEmbedding
        except Exception as exc:  # noqa: BLE001
            raise RagUnavailableError(
                "OpenAI embedding support missing. Install llama-index-embeddings-openai."
            ) from exc
        return Document, Settings, VectorStoreIndex, (NodeWithScore, OpenAIEmbedding, MockLLM)

    if embedding_provider == "ollama":
        try:
            from llama_index.embeddings.ollama import OllamaEmbedding
        except Exception as exc:  # noqa: BLE001
            raise RagUnavailableError(
                "Ollama embedding support missing. Install llama-index-embeddings-ollama."
            ) from exc
        return Document, Settings, VectorStoreIndex, (NodeWithScore, OllamaEmbedding, MockLLM)

    raise RagUnavailableError(f"Unsupported RAG embedding provider '{embedding_provider}'.")


class VerilogRAGService:
    def __init__(
        self,
        *,
        knowledge_base_path: Path,
        memory_file_path: Path,
        embedding_provider: str,
        openai_embedding_model: str,
        stored_rtl_embed_max_chars: int,
    ) -> None:
        provider = str(embedding_provider or "openai").strip().lower()
        if provider == "openai" and not os.getenv("OPENAI_API_KEY"):
            raise RagUnavailableError("OPENAI_API_KEY missing for OpenAI-backed RAG.")

        self.knowledge_base_path = knowledge_base_path.resolve()
        self.memory_file_path = memory_file_path.resolve()
        self.embedding_provider = provider
        self.openai_embedding_model = openai_embedding_model
        self.stored_rtl_embed_max_chars = max(500, int(stored_rtl_embed_max_chars))
        self._lock = threading.RLock()

        Document, Settings, VectorStoreIndex, provider_modules = _import_llama_index(provider)
        self._Document = Document
        self._Settings = Settings
        self._VectorStoreIndex = VectorStoreIndex
        self._NodeWithScore = provider_modules[0]
        self._embedding_cls = provider_modules[1]
        self._mock_llm_cls = provider_modules[2]

        # LlamaIndex prints noisy MockLLM fallback messages when Settings.llm is None.
        # Set an explicit mock LLM instead; retrieval never uses it, but the setting
        # keeps the library quiet during vector index and retriever setup.
        self._Settings.llm = self._mock_llm_cls()  # type: ignore[assignment,call-arg]
        if provider == "openai":
            self._Settings.embed_model = self._embedding_cls(  # type: ignore[call-arg]
                model=self.openai_embedding_model,
                api_key=os.getenv("OPENAI_API_KEY"),
            )
        else:
            self._Settings.embed_model = self._embedding_cls(model_name="nomic-embed-text")  # type: ignore[call-arg]

        self.memory_file_path.parent.mkdir(parents=True, exist_ok=True)
        self._memory_mtime = self._memory_file_mtime()
        self.base_docs = self._load_knowledge_base()
        self.memory_data = self._load_memory_data()
        self.index = None
        self._rebuild_index()
        emit_runtime_event(
            runtime="rag",
            event_type="service_initialized",
            payload={
                "knowledge_base_path": str(self.knowledge_base_path),
                "memory_file_path": str(self.memory_file_path),
                "embedding_provider": self.embedding_provider,
                "openai_embedding_model": self.openai_embedding_model,
            },
        )

    def _memory_file_mtime(self) -> float | None:
        try:
            return self.memory_file_path.stat().st_mtime
        except FileNotFoundError:
            return None
        except Exception:
            return None

    def _load_knowledge_base(self) -> list[Any]:
        if not self.knowledge_base_path.exists():
            emit_runtime_event(
                runtime="rag",
                event_type="knowledge_base_missing",
                payload={"knowledge_base_path": str(self.knowledge_base_path)},
            )
            return []
        content = self.knowledge_base_path.read_text(encoding="utf-8", errors="ignore")
        docs: list[Any] = []
        for module_name, module_code in _KB_MODULE_RE.findall(content):
            docs.append(
                self._Document(
                    text=module_code.strip(),
                    metadata={
                        "topic": "verilog_modules",
                        "module_name": module_name,
                        "summary": _guess_summary(module_name, module_code),
                        "rtl_hash": _short_hash(module_code),
                    },
                )
            )
        return docs

    def _load_memory_data(self) -> dict[str, Any]:
        if not self.memory_file_path.exists():
            return {"schema_version": "1", "designs": []}
        try:
            payload = json.loads(self.memory_file_path.read_text(encoding="utf-8"))
        except Exception:
            emit_runtime_event(
                runtime="rag",
                event_type="memory_load_failed",
                payload={"memory_file_path": str(self.memory_file_path)},
            )
            return {"schema_version": "1", "designs": []}
        designs = payload.get("designs") if isinstance(payload, dict) else None
        if not isinstance(designs, list):
            return {"schema_version": "1", "designs": []}
        return {"schema_version": str(payload.get("schema_version") or "1"), "designs": designs}

    def _design_to_document(self, record: dict[str, Any]) -> Any:
        module_name = str(record.get("module_name") or "unknown")
        summary = str(record.get("summary") or _guess_summary(module_name, str(record.get("rtl") or ""))).strip()
        signature = str(record.get("signature") or _extract_module_signature(str(record.get("rtl") or ""), module_name))
        interface_signals = record.get("interface_signals") if isinstance(record.get("interface_signals"), list) else []
        verification = record.get("verification") if isinstance(record.get("verification"), dict) else {}
        tb_text = str(record.get("tb_text") or "")
        rtl_text = str(record.get("rtl") or "")
        lines = [
            "// STORED DESIGN",
            f"// Module: {module_name}",
            f"// Summary: {summary}",
            f"// Signature: {signature}",
            f"// RTL_HASH: {record.get('rtl_hash', '')}",
        ]
        if interface_signals:
            lines.append("// Interface:")
            for signal in interface_signals[:24]:
                if not isinstance(signal, dict):
                    continue
                lines.append(
                    f"// - {signal.get('direction', 'signal')} {signal.get('name', 'unnamed')} width={signal.get('width', 1)}"
                )
        if verification:
            lines.append("// Verification:")
            goals = verification.get("test_goals")
            if isinstance(goals, list):
                for goal in goals[:12]:
                    lines.append(f"// - {str(goal)}")
        if tb_text.strip():
            lines.append("// Testbench excerpt:")
            lines.append(_clip(tb_text.strip(), min(3000, self.stored_rtl_embed_max_chars // 3)))
        lines.append("// RTL:")
        lines.append(_clip(rtl_text.strip(), self.stored_rtl_embed_max_chars))
        text = "\n".join(lines).strip()
        return self._Document(
            text=text,
            metadata={
                "topic": "stored_design",
                "module_name": module_name,
                "summary": summary,
                "rtl_hash": str(record.get("rtl_hash") or ""),
            },
        )

    def _rebuild_index(self) -> None:
        docs = list(self.base_docs)
        for record in self.memory_data.get("designs", []):
            if not isinstance(record, dict):
                continue
            docs.append(self._design_to_document(record))
        if not docs:
            self.index = None
            return
        self.index = self._VectorStoreIndex.from_documents(docs)

    def refresh_if_needed(self) -> None:
        with self._lock:
            current_mtime = self._memory_file_mtime()
            if current_mtime == self._memory_mtime:
                return
            self.memory_data = self._load_memory_data()
            self._memory_mtime = current_mtime
            self._rebuild_index()

    def retrieve_context(
        self,
        *,
        query: str,
        top_k: int,
        retrieve_multiple: int,
        max_chars: int,
    ) -> RagRetrieval:
        self.refresh_if_needed()
        with self._lock:
            if not query.strip() or self.index is None:
                return RagRetrieval(context_text="", hits=[])
            candidate_k = max(top_k, top_k * max(1, retrieve_multiple))
            retriever = self.index.as_retriever(similarity_top_k=candidate_k)
            raw_hits = retriever.retrieve(query)
            hits: list[RagHit] = []
            chunks: list[str] = []
            total_chars = 0
            for raw_hit in raw_hits:
                node = raw_hit.node if isinstance(raw_hit, self._NodeWithScore) else raw_hit
                metadata = getattr(node, "metadata", {}) or {}
                content = str(node.get_content()).strip()
                hit = RagHit(
                    module_name=str(metadata.get("module_name") or "unknown"),
                    topic=str(metadata.get("topic") or ""),
                    score=float(getattr(raw_hit, "score", 0.0) or 0.0),
                    summary=str(metadata.get("summary") or ""),
                    rtl_hash=str(metadata.get("rtl_hash") or ""),
                )
                header = (
                    f"// SOURCE topic={hit.topic} module={hit.module_name} rtl_hash={hit.rtl_hash}\n"
                )
                chunk = header + content + "\n"
                if total_chars + len(chunk) > max_chars:
                    break
                hits.append(hit)
                chunks.append(chunk)
                total_chars += len(chunk)
                if len(hits) >= top_k:
                    break
            return RagRetrieval(context_text="\n".join(chunks).strip(), hits=hits)

    def store_design_record(self, record: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            module_name = str(record.get("module_name") or "").strip() or str(record.get("node_id") or "unknown")
            rtl_text = str(record.get("rtl") or "").strip()
            if not rtl_text:
                raise ValueError("RAG archive record missing RTL text.")
            rtl_hash = str(record.get("rtl_hash") or _short_hash(rtl_text))
            signature = str(record.get("signature") or _extract_module_signature(rtl_text, module_name))
            summary = str(record.get("summary") or _guess_summary(module_name, rtl_text))
            prepared = {
                "module_name": module_name,
                "summary": summary,
                "signature": signature,
                "rtl": rtl_text,
                "rtl_hash": rtl_hash,
                "rtl_sha256": str(record.get("rtl_sha256") or _hash_text(rtl_text)),
                "tb_text": str(record.get("tb_text") or ""),
                "tb_sha256": str(record.get("tb_sha256") or _hash_text(str(record.get("tb_text") or ""))),
                "node_id": str(record.get("node_id") or module_name),
                "run_id": str(record.get("run_id") or ""),
                "attempt": record.get("attempt"),
                "interface_signals": record.get("interface_signals") if isinstance(record.get("interface_signals"), list) else [],
                "verification": record.get("verification") if isinstance(record.get("verification"), dict) else {},
                "tags": list(record.get("tags") or ["generated_design", "passing_design", "verilog_rag"]),
            }

            designs = self.memory_data.setdefault("designs", [])
            existing = None
            for idx, item in enumerate(designs):
                if not isinstance(item, dict):
                    continue
                if item.get("module_name") == module_name and item.get("rtl_hash") == rtl_hash:
                    existing = idx
                    break
            inserted = existing is None
            if inserted:
                designs.append(prepared)
            else:
                designs[existing] = prepared

            _atomic_write_json(
                self.memory_file_path,
                {"schema_version": "1", "designs": designs},
            )
            self._memory_mtime = self._memory_file_mtime()
            if inserted:
                self._rebuild_index()
            return {
                "inserted": inserted,
                "module_name": module_name,
                "rtl_hash": rtl_hash,
            }


def _service_key_from_config() -> tuple[Any, ...]:
    cfg = get_runtime_config().rag
    return (
        resolve_resource_path(cfg.knowledge_base_path),
        resolve_rag_workspace_path(cfg.memory_file),
        str(cfg.embedding_provider or "openai").strip().lower(),
        str(cfg.openai_embedding_model or "text-embedding-3-small").strip(),
        int(cfg.stored_rtl_embed_max_chars),
    )


def _build_service() -> VerilogRAGService:
    cfg = get_runtime_config().rag
    return VerilogRAGService(
        knowledge_base_path=resolve_resource_path(cfg.knowledge_base_path),
        memory_file_path=resolve_rag_workspace_path(cfg.memory_file),
        embedding_provider=str(cfg.embedding_provider or "openai").strip().lower(),
        openai_embedding_model=str(cfg.openai_embedding_model or "text-embedding-3-small").strip(),
        stored_rtl_embed_max_chars=int(cfg.stored_rtl_embed_max_chars),
    )


def _get_service() -> VerilogRAGService:
    global _SERVICE_INSTANCE, _SERVICE_KEY
    key = _service_key_from_config()
    with _SERVICE_LOCK:
        if _SERVICE_INSTANCE is None or _SERVICE_KEY != key:
            _SERVICE_INSTANCE = _build_service()
            _SERVICE_KEY = key
        return _SERVICE_INSTANCE


def retrieve_for_stage(
    stage: str,
    query: str,
    *,
    execution_policy: Optional[dict[str, Any]] = None,
) -> tuple[str, dict[str, Any]]:
    enabled, reason = _rag_enabled_for_execution(execution_policy)
    if not enabled:
        return "", _runtime_metadata(stage, mode="retrieve", used=False, skip_reason=reason)

    stage_cfg = _stage_config(stage)
    if not stage_cfg.enabled:
        return "", _runtime_metadata(stage, mode="retrieve", used=False, skip_reason="stage_disabled")

    cfg = get_runtime_config().rag
    try:
        service = _get_service()
        retrieval = service.retrieve_context(
            query=query,
            top_k=max(1, int(stage_cfg.top_k)),
            retrieve_multiple=max(1, int(stage_cfg.retrieve_multiple)),
            max_chars=max(500, int(stage_cfg.max_context_chars)),
        )
    except RagUnavailableError as exc:
        emit_runtime_event(
            runtime="rag",
            event_type="retrieve_unavailable",
            payload={"stage": stage, "reason": str(exc)},
        )
        if cfg.fail_open:
            return "", _runtime_metadata(
                stage,
                mode="retrieve",
                used=False,
                degraded=True,
                skip_reason=str(exc),
            )
        raise
    except Exception as exc:  # noqa: BLE001
        emit_runtime_event(
            runtime="rag",
            event_type="retrieve_failed",
            payload={"stage": stage, "reason": str(exc)},
        )
        if cfg.fail_open:
            return "", _runtime_metadata(
                stage,
                mode="retrieve",
                used=False,
                degraded=True,
                skip_reason=f"retrieval_error:{exc}",
            )
        raise RagUnavailableError(f"RAG retrieval failed for stage '{stage}': {exc}") from exc

    module_names = _module_names_from_hits(retrieval.hits)
    themes = _themes_from_hits(retrieval.hits)
    used = bool(retrieval.context_text.strip()) and bool(retrieval.hits)
    metadata = _runtime_metadata(
        stage,
        mode="retrieve",
        used=used,
        hit_count=len(retrieval.hits),
        retrieved_module_names=module_names,
        themes=themes,
        applied_guidance_summary=_stage_guidance_summary(stage, len(retrieval.hits), module_names),
        skip_reason=None if used else "no_relevant_hits",
    )
    emit_runtime_event(
        runtime="rag",
        event_type="retrieve_completed",
        payload={
            "stage": stage,
            "used": used,
            "hit_count": len(retrieval.hits),
            "retrieved_module_names": module_names,
        },
    )
    return retrieval.context_text, metadata


def archive_final_design(
    *,
    stage: str,
    record: dict[str, Any],
    execution_policy: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    enabled, reason = _rag_enabled_for_execution(execution_policy)
    if not enabled:
        return _runtime_metadata(stage, mode="archive", used=False, skip_reason=reason)

    cfg = get_runtime_config().rag
    if not cfg.finalizer.enabled:
        return _runtime_metadata(stage, mode="archive", used=False, skip_reason="stage_disabled")

    try:
        service = _get_service()
        result = service.store_design_record(record)
    except RagUnavailableError as exc:
        emit_runtime_event(
            runtime="rag",
            event_type="archive_unavailable",
            payload={"stage": stage, "reason": str(exc)},
        )
        if cfg.fail_open:
            return _runtime_metadata(
                stage,
                mode="archive",
                used=False,
                degraded=True,
                skip_reason=str(exc),
            )
        raise
    except Exception as exc:  # noqa: BLE001
        emit_runtime_event(
            runtime="rag",
            event_type="archive_failed",
            payload={"stage": stage, "reason": str(exc)},
        )
        if cfg.fail_open:
            return _runtime_metadata(
                stage,
                mode="archive",
                used=False,
                degraded=True,
                skip_reason=f"archive_error:{exc}",
            )
        raise RagUnavailableError(f"RAG archive failed for stage '{stage}': {exc}") from exc

    stored = [str(result["module_name"])] if result.get("module_name") else []
    summary = (
        f"I captured this passing design in memory for future runs."
        if result.get("inserted")
        else "I checked this passing design against memory and found it already represented."
    )
    metadata = _runtime_metadata(
        stage,
        mode="archive",
        used=True,
        stored_module_names=stored,
        applied_guidance_summary=summary,
    )
    emit_runtime_event(
        runtime="rag",
        event_type="archive_completed",
        payload={
            "stage": stage,
            "stored_module_names": stored,
            "inserted": bool(result.get("inserted")),
        },
    )
    return metadata


def default_archive_root() -> Path:
    return resolve_rag_workspace_path(get_runtime_config().rag.archive_root)


def default_memory_file() -> Path:
    return resolve_rag_workspace_path(get_runtime_config().rag.memory_file)


def default_knowledge_base_path() -> Path:
    return resolve_resource_path(get_runtime_config().rag.knowledge_base_path)
