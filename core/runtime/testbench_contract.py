from __future__ import annotations

from typing import Any, Dict, Iterable


_CLOCK_NAME_CANDIDATES = ("clk", "clock", "i_clk", "aclk")
_RESET_NAME_CANDIDATES = ("rst_n", "reset_n", "rst", "reset", "aresetn", "areset")
_NO_RESET_MARKERS = (
    "no reset",
    "without reset",
    "none (combinational",
    "reset not used",
)


def extract_reset_semantics(behavior_text: object) -> str | None:
    for line in str(behavior_text or "").splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("reset:"):
            return stripped.split(":", 1)[1].strip() or None
    return None


def _first_clocking_item(raw_clocking: object) -> dict[str, Any]:
    if isinstance(raw_clocking, dict):
        return raw_clocking
    if isinstance(raw_clocking, list):
        for entry in raw_clocking:
            if isinstance(entry, dict):
                return entry
    return {}


def _normalized_signal_entries(interface_signals: object) -> list[dict[str, Any]]:
    if not isinstance(interface_signals, list):
        return []
    return [item for item in interface_signals if isinstance(item, dict)]


def _signal_name_map(interface_signals: object) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in _normalized_signal_entries(interface_signals):
        name = str(item.get("name") or "").strip()
        if name:
            out[name.lower()] = name
    return out


def _infer_signal_by_semantics(interface_signals: object, keyword: str) -> str | None:
    for item in _normalized_signal_entries(interface_signals):
        name = str(item.get("name") or "").strip()
        semantics = str(item.get("semantics") or "").strip().lower()
        if name and keyword in semantics:
            return name
    return None


def _infer_named_signal(interface_signals: object, candidates: Iterable[str]) -> str | None:
    lowered = _signal_name_map(interface_signals)
    for candidate in candidates:
        if candidate in lowered:
            return lowered[candidate]
    for item in _normalized_signal_entries(interface_signals):
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        lowered_name = name.lower()
        for candidate in candidates:
            if lowered_name == candidate or lowered_name.endswith(f"_{candidate}"):
                return name
    return None


def _infer_clock_name(interface_signals: object) -> str | None:
    return _infer_signal_by_semantics(interface_signals, "clock") or _infer_named_signal(
        interface_signals, _CLOCK_NAME_CANDIDATES
    )


def _infer_reset_name(interface_signals: object) -> str | None:
    return _infer_signal_by_semantics(interface_signals, "reset") or _infer_named_signal(
        interface_signals, _RESET_NAME_CANDIDATES
    )


def _text_indicates_no_reset(text: object) -> bool:
    lowered = str(text or "").strip().lower()
    if not lowered:
        return False
    return any(marker in lowered for marker in _NO_RESET_MARKERS)


def normalize_testbench_contract(
    raw_contract: object,
    *,
    interface_signals: object,
    raw_clocking: object = None,
    module_contract: object = None,
    reset_semantics: object = None,
) -> Dict[str, Any]:
    contract = dict(raw_contract) if isinstance(raw_contract, dict) else {}
    clocking = _first_clocking_item(raw_clocking)
    signal_names = _signal_name_map(interface_signals)

    module_style = ""
    if isinstance(module_contract, dict):
        module_style = str(module_contract.get("style") or "").strip().lower()

    inferred_clock_name = _infer_clock_name(interface_signals)
    inferred_reset_name = _infer_reset_name(interface_signals)
    clock_name = str(contract.get("clock_name") or clocking.get("clock_name") or inferred_clock_name or "").strip() or None
    reset_name = str(contract.get("reset_name") or clocking.get("reset_name") or inferred_reset_name or "").strip() or None

    if clock_name and signal_names and clock_name.lower() not in signal_names:
        clock_name = inferred_clock_name
    if reset_name and signal_names and reset_name.lower() not in signal_names:
        reset_name = inferred_reset_name

    no_reset = _text_indicates_no_reset(reset_semantics)
    has_clock_signal = clock_name is not None

    timing_style = str(contract.get("timing_style") or "").strip().lower()
    if timing_style not in {"combinational", "clocked"}:
        if module_style == "combinational":
            timing_style = "combinational"
        elif module_style == "integration" and not has_clock_signal and not clocking:
            timing_style = "combinational"
        elif has_clock_signal:
            timing_style = "clocked"
        else:
            timing_style = "combinational"

    requires_clock_raw = contract.get("requires_clock")
    requires_clock = bool(requires_clock_raw) if requires_clock_raw is not None else timing_style == "clocked"
    if not requires_clock:
        clock_name = None

    if requires_clock and not clock_name:
        clock_name = inferred_clock_name or "clk"

    clock_polarity = None
    sample_edge = None
    drive_edge = None
    if requires_clock:
        clock_polarity = str(contract.get("clock_polarity") or clocking.get("clock_polarity") or "POSEDGE").upper()
        sample_edge = "negedge" if clock_polarity == "NEGEDGE" else "posedge"
        drive_edge = "posedge" if sample_edge == "negedge" else "negedge"

    requires_reset_raw = contract.get("requires_reset")
    if requires_reset_raw is not None:
        requires_reset = bool(requires_reset_raw)
    elif timing_style == "combinational" or no_reset:
        requires_reset = False
    else:
        requires_reset = reset_name is not None

    if not requires_reset:
        reset_name = None

    reset_polarity = None
    reset_is_async = None
    reset_active_expr = None
    if requires_reset:
        reset_polarity = str(
            contract.get("reset_polarity")
            or clocking.get("reset_polarity")
            or ("ACTIVE_LOW" if str(reset_name or "").lower().endswith("_n") else "ACTIVE_HIGH")
        ).upper()
        reset_is_async_raw = contract.get("reset_is_async")
        if reset_is_async_raw is None:
            reset_is_async_raw = clocking.get("reset_is_async")
        reset_is_async = True if reset_is_async_raw is None else bool(reset_is_async_raw)
        reset_active_low = reset_polarity in {"ACTIVE_LOW", "LOW", "0"}
        reset_active_expr = f"!{reset_name}" if reset_active_low else reset_name

    mode = str(contract.get("mode") or "").strip().lower()
    if mode not in {"combinational_no_reset", "clocked_no_reset", "clocked_reset"}:
        if timing_style == "combinational":
            mode = "combinational_no_reset"
        elif requires_reset:
            mode = "clocked_reset"
        else:
            mode = "clocked_no_reset"

    checker_style = str(contract.get("checker_style") or "").strip().lower()
    if checker_style not in {"combinational_settle", "sampled_scoreboard"}:
        checker_style = "combinational_settle" if mode == "combinational_no_reset" else "sampled_scoreboard"

    post_reset_settle_cycles = contract.get("post_reset_settle_cycles")
    if post_reset_settle_cycles is None:
        post_reset_settle_cycles = 1 if mode == "clocked_reset" else 0

    return {
        "mode": mode,
        "timing_style": timing_style,
        "checker_style": checker_style,
        "requires_clock": requires_clock,
        "clock_name": clock_name,
        "clock_polarity": clock_polarity,
        "sample_edge": sample_edge,
        "drive_edge": drive_edge,
        "requires_reset": requires_reset,
        "reset_name": reset_name,
        "reset_polarity": reset_polarity,
        "reset_is_async": reset_is_async,
        "reset_active_expr": reset_active_expr,
        "post_reset_settle_cycles": int(post_reset_settle_cycles),
    }


def build_testbench_contract(
    *,
    interface_signals: object,
    raw_clocking: object,
    module_contract: object,
    reset_semantics: object,
) -> Dict[str, Any]:
    return normalize_testbench_contract(
        None,
        interface_signals=interface_signals,
        raw_clocking=raw_clocking,
        module_contract=module_contract,
        reset_semantics=reset_semantics,
    )
