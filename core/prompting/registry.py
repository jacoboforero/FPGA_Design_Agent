"""
Repo-native prompt registry and rendering helpers.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from string import Template
from typing import Any, Dict, Literal, Mapping, Optional

import yaml
from pydantic import BaseModel, Field

from adapters.llm.gateway import GenerationConfig, Message, MessageRole
from core.runtime.paths import artifacts_root, resolve_resource_path

try:  # Optional dependency
    from jsonschema import ValidationError as JsonSchemaValidationError
    from jsonschema import validate as validate_json_schema
except Exception:  # noqa: BLE001
    JsonSchemaValidationError = None  # type: ignore[assignment]
    validate_json_schema = None  # type: ignore[assignment]

OutputMode = Literal["text", "json_object", "json_schema"]


class PromptSpec(BaseModel):
    prompt_id: str
    version: str = "v1"
    description: Optional[str] = None
    output_mode: OutputMode = "text"
    output_schema_name: Optional[str] = None
    output_schema: Optional[Dict[str, Any]] = None
    prompt_dir: Path
    system_path: Optional[Path] = None
    user_path: Optional[Path] = None


class RenderedPrompt(BaseModel):
    prompt_id: str
    version: str
    prompt_hash: str
    output_mode: OutputMode = "text"
    output_schema_name: Optional[str] = None
    output_schema: Optional[Dict[str, Any]] = None
    messages: list[Message] = Field(default_factory=list)


def _hash_payload(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")).hexdigest()


def _stringify_context(context: Mapping[str, Any]) -> dict[str, str]:
    rendered: dict[str, str] = {}
    for key, value in context.items():
        if value is None:
            rendered[key] = ""
        elif isinstance(value, (str, int, float, bool, Path)):
            rendered[key] = str(value)
        else:
            raise TypeError(
                f"Prompt context '{key}' must be pre-serialized to text; got {type(value).__name__}."
            )
    return rendered


def _render_template(path: Optional[Path], context: Mapping[str, Any]) -> str:
    if path is None or not path.exists():
        return ""
    template = Template(path.read_text(encoding="utf-8"))
    return template.substitute(_stringify_context(context)).strip()


def parse_json_object(text: str) -> Optional[dict[str, Any]]:
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
        return None
    except Exception:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        return None
    return None


def validate_structured_output(
    payload: Optional[dict[str, Any]],
    rendered: RenderedPrompt,
) -> tuple[bool, Optional[str]]:
    if rendered.output_mode == "text":
        return True, None
    if not isinstance(payload, dict):
        return False, "Structured prompt did not return a JSON object."
    if not rendered.output_schema:
        return True, None
    if validate_json_schema is None:
        if rendered.output_mode == "json_schema":
            return False, "jsonschema dependency unavailable for json_schema output validation."
        return True, None
    try:
        validate_json_schema(instance=payload, schema=rendered.output_schema)
    except Exception as exc:  # noqa: BLE001
        if JsonSchemaValidationError is not None and isinstance(exc, JsonSchemaValidationError):
            return False, exc.message
        return False, str(exc)
    return True, None


def build_prompt_metadata(rendered: RenderedPrompt, *, extra: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    payload = {
        "prompt_id": rendered.prompt_id,
        "prompt_version": rendered.version,
        "prompt_hash": rendered.prompt_hash,
        "prompt_output_mode": rendered.output_mode,
    }
    if rendered.output_schema_name:
        payload["prompt_output_schema_name"] = rendered.output_schema_name
    if extra:
        payload.update(extra)
    return payload


def apply_prompt_output_contract(cfg: GenerationConfig, rendered: RenderedPrompt) -> GenerationConfig:
    adjusted = cfg.model_copy(deep=True)
    adjusted.output_mode = rendered.output_mode
    adjusted.output_schema_name = rendered.output_schema_name
    adjusted.output_schema = rendered.output_schema
    return adjusted


def write_prompt_trace(rendered: RenderedPrompt, trace_dir: Optional[Path] = None) -> Path:
    if trace_dir is None:
        trace_dir = (
            artifacts_root()
            / "observability"
            / "prompt_traces"
            / rendered.prompt_id.replace(".", "__")
            / f"{rendered.version}__{uuid.uuid4().hex[:10]}"
        )
    trace_dir.mkdir(parents=True, exist_ok=True)
    messages_payload = [
        {"role": message.role.value, "content": message.content}
        for message in rendered.messages
    ]
    prompt_meta = {
        "prompt_id": rendered.prompt_id,
        "prompt_version": rendered.version,
        "prompt_hash": rendered.prompt_hash,
        "output_mode": rendered.output_mode,
        "output_schema_name": rendered.output_schema_name,
        "output_schema": rendered.output_schema,
    }
    (trace_dir / "prompt_messages.json").write_text(
        json.dumps(messages_payload, indent=2),
        encoding="utf-8",
    )
    (trace_dir / "prompt_meta.json").write_text(
        json.dumps(prompt_meta, indent=2),
        encoding="utf-8",
    )
    return trace_dir


class PromptRegistry:
    def __init__(self, root: Optional[Path] = None):
        self.root = Path(root or resolve_resource_path("prompts")).resolve()
        self._specs_by_id: Optional[dict[str, PromptSpec]] = None

    def _ensure_loaded(self) -> None:
        if self._specs_by_id is not None:
            return
        if not self.root.exists():
            raise FileNotFoundError(f"Prompt root does not exist: {self.root}")
        specs: dict[str, PromptSpec] = {}
        for meta_path in sorted(self.root.rglob("meta.yaml")):
            if "fragments" in meta_path.parts:
                continue
            raw = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
            if not isinstance(raw, dict):
                raise ValueError(f"Prompt metadata must be a mapping: {meta_path}")
            output = raw.get("output") if isinstance(raw.get("output"), dict) else {}
            prompt_id = str(raw.get("id") or "").strip()
            if not prompt_id:
                raise ValueError(f"Prompt metadata missing id: {meta_path}")
            if prompt_id in specs:
                raise ValueError(f"Duplicate prompt id '{prompt_id}' found in {meta_path}")
            prompt_dir = meta_path.parent.resolve()
            system_path = prompt_dir / "system.md"
            user_path = prompt_dir / "user.md"
            if not system_path.exists():
                system_path = None
            if not user_path.exists():
                user_path = None
            if system_path is None and user_path is None:
                raise ValueError(f"Prompt bundle must contain system.md or user.md: {prompt_dir}")
            specs[prompt_id] = PromptSpec(
                prompt_id=prompt_id,
                version=str(raw.get("version") or "v1").strip() or "v1",
                description=str(raw.get("description")).strip() if raw.get("description") is not None else None,
                output_mode=str(output.get("mode") or "text").strip() or "text",
                output_schema_name=(
                    str(output.get("schema_name")).strip()
                    if output.get("schema_name") is not None
                    else None
                ),
                output_schema=output.get("schema") if isinstance(output.get("schema"), dict) else None,
                prompt_dir=prompt_dir,
                system_path=system_path,
                user_path=user_path,
            )
        self._specs_by_id = specs

    def get(self, prompt_id: str) -> PromptSpec:
        self._ensure_loaded()
        assert self._specs_by_id is not None
        if prompt_id not in self._specs_by_id:
            raise KeyError(f"Unknown prompt id: {prompt_id}")
        return self._specs_by_id[prompt_id]

    def list_prompts(self) -> list[PromptSpec]:
        self._ensure_loaded()
        assert self._specs_by_id is not None
        return [self._specs_by_id[key] for key in sorted(self._specs_by_id)]

    def render(self, prompt_id: str, context: Mapping[str, Any]) -> RenderedPrompt:
        spec = self.get(prompt_id)
        system_content = _render_template(spec.system_path, context)
        user_content = _render_template(spec.user_path, context)
        messages: list[Message] = []
        if system_content:
            messages.append(Message(role=MessageRole.SYSTEM, content=system_content))
        if user_content:
            messages.append(Message(role=MessageRole.USER, content=user_content))
        hash_payload = {
            "prompt_id": spec.prompt_id,
            "version": spec.version,
            "output_mode": spec.output_mode,
            "output_schema_name": spec.output_schema_name,
            "output_schema": spec.output_schema,
            "messages": [{"role": item.role.value, "content": item.content} for item in messages],
        }
        return RenderedPrompt(
            prompt_id=spec.prompt_id,
            version=spec.version,
            prompt_hash=_hash_payload(hash_payload),
            output_mode=spec.output_mode,
            output_schema_name=spec.output_schema_name,
            output_schema=spec.output_schema,
            messages=messages,
        )

    def render_fragment(self, fragment_path: str, context: Optional[Mapping[str, Any]] = None) -> str:
        path = (self.root / "fragments" / fragment_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Missing prompt fragment: {path}")
        template = Template(path.read_text(encoding="utf-8"))
        return template.substitute(_stringify_context(context or {})).strip()


_DEFAULT_REGISTRY = PromptRegistry()


def render_prompt(prompt_id: str, context: Mapping[str, Any], *, registry: Optional[PromptRegistry] = None) -> RenderedPrompt:
    active_registry = registry or _DEFAULT_REGISTRY
    return active_registry.render(prompt_id, context)
