from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from uuid import UUID

from core.schemas.specifications import L2Specification, L4Specification, SpecificationDocument, SpecificationState

_DEFAULT_PROFILE = "hybrid_scoreboard"
_STRICT_SYMBOLIC_PROFILE = "strict_tb_acceptance"
_UINT_RE = re.compile(r"^\d(?:_?\d)*$")
_SLICE_SINGLE_RE = re.compile(r"^\[(\d+)\]$")
_SLICE_RANGE_RE = re.compile(r"^\[(\d+):(\d+)\]$")


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    severity: str
    message: str
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationResult:
    errors: List[ValidationIssue] = field(default_factory=list)
    warnings: List[ValidationIssue] = field(default_factory=list)
    profile: str = _DEFAULT_PROFILE


@dataclass(frozen=True)
class _ResolvedWidth:
    numeric: Optional[int] = None
    symbolic: Optional[str] = None

    @property
    def is_numeric(self) -> bool:
        return self.numeric is not None

    @property
    def display(self) -> str:
        if self.numeric is not None:
            return str(self.numeric)
        return str(self.symbolic or "")


def validate_preplan_inputs(
    lock: Dict[str, Any],
    top_specs: Dict[str, SpecificationDocument],
    child_specs: Dict[str, Dict[str, SpecificationDocument]],
    l4: L4Specification,
    execution_policy: Dict[str, Any] | None,
) -> ValidationResult:
    profile = str((execution_policy or {}).get("verification_profile", _DEFAULT_PROFILE))
    result = ValidationResult(profile=profile)

    loaded_docs = _collect_loaded_docs(top_specs=top_specs, child_specs=child_specs, l4=l4)
    _validate_frozen_states(loaded_docs, result)
    expected_spec_id = _resolve_expected_spec_id(lock=lock, top_specs=top_specs, result=result)
    _validate_spec_ids(loaded_docs, expected_spec_id, result)
    _validate_connection_widths(lock=lock, top_specs=top_specs, child_specs=child_specs, l4=l4, result=result)
    return result


def _collect_loaded_docs(
    *,
    top_specs: Dict[str, SpecificationDocument],
    child_specs: Dict[str, Dict[str, SpecificationDocument]],
    l4: L4Specification,
) -> List[tuple[str, SpecificationDocument]]:
    docs: List[tuple[str, SpecificationDocument]] = []
    for level in ("L1", "L2", "L3", "L5"):
        doc = top_specs.get(level)
        if isinstance(doc, SpecificationDocument):
            docs.append((f"top.{level}", doc))
    docs.append(("top.L4", l4))

    for module in sorted(child_specs):
        module_docs = child_specs.get(module, {})
        for level in ("L1", "L2", "L3", "L5"):
            doc = module_docs.get(level)
            if isinstance(doc, SpecificationDocument):
                docs.append((f"{module}.{level}", doc))
    return docs


def _validate_frozen_states(
    docs: List[tuple[str, SpecificationDocument]],
    result: ValidationResult,
) -> None:
    for label, doc in docs:
        if doc.state == SpecificationState.FROZEN:
            continue
        _add_error(
            result,
            code="PLV101",
            message="Specification document is not in FROZEN state.",
            context={"document": label, "state": str(doc.state)},
        )


def _resolve_expected_spec_id(
    *,
    lock: Dict[str, Any],
    top_specs: Dict[str, SpecificationDocument],
    result: ValidationResult,
) -> Optional[UUID]:
    lock_spec_id_raw = lock.get("spec_id")
    if lock_spec_id_raw not in (None, ""):
        try:
            return UUID(str(lock_spec_id_raw))
        except (TypeError, ValueError):
            _add_warning(
                result,
                code="PLV202",
                message="lock.json spec_id is not a valid UUID; falling back to top L1 spec_id.",
                context={"lock_spec_id": str(lock_spec_id_raw)},
            )
    else:
        _add_warning(
            result,
            code="PLV201",
            message="lock.json is missing spec_id; falling back to top L1 spec_id.",
            context={},
        )

    top_l1 = top_specs.get("L1")
    if isinstance(top_l1, SpecificationDocument):
        return top_l1.spec_id

    _add_error(
        result,
        code="PLV203",
        message="Unable to determine expected spec_id (missing top L1 spec).",
        context={},
    )
    return None


def _validate_spec_ids(
    docs: List[tuple[str, SpecificationDocument]],
    expected_spec_id: Optional[UUID],
    result: ValidationResult,
) -> None:
    if expected_spec_id is None:
        return
    for label, doc in docs:
        if doc.spec_id == expected_spec_id:
            continue
        _add_error(
            result,
            code="PLV204",
            message="spec_id mismatch detected across loaded specifications.",
            context={"document": label, "expected": str(expected_spec_id), "actual": str(doc.spec_id)},
        )


def _validate_connection_widths(
    *,
    lock: Dict[str, Any],
    top_specs: Dict[str, SpecificationDocument],
    child_specs: Dict[str, Dict[str, SpecificationDocument]],
    l4: L4Specification,
    result: ValidationResult,
) -> None:
    top_module = str(lock.get("top_module") or lock.get("module_name") or "").strip()
    if not top_module and l4.block_diagram:
        top_module = l4.block_diagram[0].node_id
    if not top_module:
        top_module = "top"

    port_widths: Dict[str, Dict[str, str]] = {}
    top_l2 = top_specs.get("L2")
    if isinstance(top_l2, L2Specification):
        port_widths[top_module] = {sig.name: sig.width_expr for sig in top_l2.signals if sig.name}

    for module, docs in child_specs.items():
        mod_l2 = docs.get("L2")
        if isinstance(mod_l2, L2Specification):
            port_widths[module] = {sig.name: sig.width_expr for sig in mod_l2.signals if sig.name}

    for idx, conn in enumerate(l4.connections, start=1):
        src_width = _resolve_endpoint_width(
            endpoint=conn.src,
            port_widths=port_widths,
            connection_idx=idx,
            side="src",
            result=result,
        )
        dst_width = _resolve_endpoint_width(
            endpoint=conn.dst,
            port_widths=port_widths,
            connection_idx=idx,
            side="dst",
            result=result,
        )
        if src_width is None or dst_width is None:
            continue

        _compare_widths(
            left=src_width,
            right=dst_width,
            result=result,
            connection_idx=idx,
            code_numeric_mismatch="PLV304",
            numeric_message="Source and destination effective widths are incompatible.",
            unresolved_message="Unresolved symbolic width comparability between connection endpoints.",
            context={"connection_index": idx, "src": src_width.display, "dst": dst_width.display},
        )

        if conn.width in (None, ""):
            continue
        declared_width = _resolve_declared_width(str(conn.width))
        if declared_width is None:
            continue
        for endpoint_name, endpoint_width in (("src", src_width), ("dst", dst_width)):
            _compare_widths(
                left=declared_width,
                right=endpoint_width,
                result=result,
                connection_idx=idx,
                code_numeric_mismatch="PLV305",
                numeric_message="connection.width does not match effective endpoint width.",
                unresolved_message="Unresolved symbolic comparability involving connection.width.",
                context={
                    "connection_index": idx,
                    "connection_width": declared_width.display,
                    f"{endpoint_name}_effective": endpoint_width.display,
                    "endpoint": endpoint_name,
                },
            )


def _resolve_endpoint_width(
    *,
    endpoint: Any,
    port_widths: Dict[str, Dict[str, str]],
    connection_idx: int,
    side: str,
    result: ValidationResult,
) -> Optional[_ResolvedWidth]:
    module_ports = port_widths.get(endpoint.node_id)
    if not module_ports:
        return None
    base_expr = module_ports.get(endpoint.port)
    if base_expr is None:
        return None

    base_numeric = _parse_uint(base_expr)
    base_symbolic = _normalize_symbolic(base_expr)
    endpoint_slice = endpoint.slice
    if endpoint_slice in (None, ""):
        if base_numeric is not None:
            return _ResolvedWidth(numeric=base_numeric)
        return _ResolvedWidth(symbolic=base_symbolic)

    slice_text = str(endpoint_slice).strip()
    single_match = _SLICE_SINGLE_RE.fullmatch(slice_text)
    if single_match:
        index = int(single_match.group(1))
        if base_numeric is not None and index >= base_numeric:
            _add_error(
                result,
                code="PLV303",
                message="Slice index is out of range for endpoint base width.",
                context={
                    "connection_index": connection_idx,
                    "side": side,
                    "endpoint": f"{endpoint.node_id}.{endpoint.port}",
                    "slice": slice_text,
                    "base_width": base_numeric,
                },
            )
            return None
        return _ResolvedWidth(numeric=1)

    range_match = _SLICE_RANGE_RE.fullmatch(slice_text)
    if range_match:
        msb = int(range_match.group(1))
        lsb = int(range_match.group(2))
        if msb < lsb:
            _add_error(
                result,
                code="PLV302",
                message="Slice range is invalid (msb < lsb).",
                context={
                    "connection_index": connection_idx,
                    "side": side,
                    "endpoint": f"{endpoint.node_id}.{endpoint.port}",
                    "slice": slice_text,
                },
            )
            return None
        if base_numeric is not None and msb >= base_numeric:
            _add_error(
                result,
                code="PLV303",
                message="Slice range exceeds endpoint base width.",
                context={
                    "connection_index": connection_idx,
                    "side": side,
                    "endpoint": f"{endpoint.node_id}.{endpoint.port}",
                    "slice": slice_text,
                    "base_width": base_numeric,
                },
            )
            return None
        return _ResolvedWidth(numeric=(msb - lsb + 1))

    _add_error(
        result,
        code="PLV301",
        message="Malformed slice expression; expected [idx] or [msb:lsb].",
        context={
            "connection_index": connection_idx,
            "side": side,
            "endpoint": f"{endpoint.node_id}.{endpoint.port}",
            "slice": slice_text,
        },
    )
    return None


def _resolve_declared_width(width_expr: str) -> Optional[_ResolvedWidth]:
    normalized = _normalize_symbolic(width_expr)
    if not normalized:
        return None
    parsed = _parse_uint(normalized)
    if parsed is not None:
        return _ResolvedWidth(numeric=parsed)
    return _ResolvedWidth(symbolic=normalized)


def _compare_widths(
    *,
    left: _ResolvedWidth,
    right: _ResolvedWidth,
    result: ValidationResult,
    connection_idx: int,
    code_numeric_mismatch: str,
    numeric_message: str,
    unresolved_message: str,
    context: Dict[str, Any],
) -> None:
    if left.is_numeric and right.is_numeric:
        if left.numeric == right.numeric:
            return
        _add_error(result, code=code_numeric_mismatch, message=numeric_message, context=context)
        return

    if not left.is_numeric and not right.is_numeric and left.symbolic == right.symbolic:
        return

    severity = "ERROR" if result.profile == _STRICT_SYMBOLIC_PROFILE else "WARNING"
    issue = ValidationIssue(
        code="PLV306",
        severity=severity,
        message=unresolved_message,
        context=context | {"connection_index": connection_idx},
    )
    _append_issue(result, issue)


def _normalize_symbolic(expr: Any) -> str:
    compact = "".join(str(expr).split())
    while _is_wrapped_by_parens(compact):
        compact = compact[1:-1].strip()
    return compact


def _is_wrapped_by_parens(text: str) -> bool:
    if len(text) < 2 or text[0] != "(" or text[-1] != ")":
        return False
    depth = 0
    for idx, ch in enumerate(text):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                return False
        if depth == 0 and idx < len(text) - 1:
            return False
    return depth == 0


def _parse_uint(expr: Any) -> Optional[int]:
    text = _normalize_symbolic(expr).replace("_", "")
    if not _UINT_RE.fullmatch(text):
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _add_error(result: ValidationResult, *, code: str, message: str, context: Dict[str, Any]) -> None:
    _append_issue(result, ValidationIssue(code=code, severity="ERROR", message=message, context=context))


def _add_warning(result: ValidationResult, *, code: str, message: str, context: Dict[str, Any]) -> None:
    _append_issue(result, ValidationIssue(code=code, severity="WARNING", message=message, context=context))


def _append_issue(result: ValidationResult, issue: ValidationIssue) -> None:
    if issue.severity == "ERROR":
        result.errors.append(issue)
    else:
        result.warnings.append(issue)

