"""
Lightweight testbench sanitizer for Verilog-2001 compatibility and race avoidance.
"""
from __future__ import annotations

import re

_PROC_START_RE = re.compile(r"^\s*(always|initial)\b", re.IGNORECASE)
_POS_EDGE_RE = re.compile(r"^\s*always\s*@\(\s*posedge\b", re.IGNORECASE)
_DECL_RE = re.compile(r"^\s*(reg|integer|wire|logic)\b")
_BEGIN_RE = re.compile(r"\bbegin\b")
_END_RE = re.compile(r"\bend\b")
_CHECK_RE = re.compile(r"\b(if\s*\(|\$display\s*\(|\$finish\s*\()", re.IGNORECASE)
_DUMPFILE_TARGET_BITS = 2048
_DUMPFILE_NAMES = ("dumpfile", "dump_file", "dump_file_str")


def sanitize_testbench(source: str, *, align_split_ref_checker: bool = False) -> str:
    text = _fix_binary_literal_widths(source)
    lines = text.splitlines()
    lines = _hoist_declarations(lines)
    lines = _widen_dumpfile_regs(lines)
    lines = _insert_check_delay(lines)
    if align_split_ref_checker:
        lines = _align_split_ref_checker_delay(lines)
    return "\n".join(lines)


def _fix_binary_literal_widths(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        width = int(match.group(1))
        base = match.group(2)
        digits = match.group(3)
        digit_count = len(digits.replace("_", ""))
        if digit_count > width:
            return f"{digit_count}'{base}{digits}"
        return match.group(0)

    return re.sub(r"(\d+)\'([bB])([01xXzZ_]+)", repl, text)


def _hoist_declarations(lines: list[str]) -> list[str]:
    hoisted: list[str] = []
    out: list[str] = []
    module_started = False
    module_header_done = False
    module_header_end_idx = None

    in_proc = False
    proc_depth = 0
    single_stmt = False

    for idx, line in enumerate(lines):
        stripped = line.strip()

        if not module_started and stripped.startswith("module "):
            module_started = True
        if module_started and not module_header_done:
            if stripped.endswith(";") and ("module " in stripped):
                module_header_done = True
                module_header_end_idx = len(out)
            elif ");" in stripped:
                module_header_done = True
                module_header_end_idx = len(out)

        if not in_proc and _PROC_START_RE.match(stripped):
            in_proc = True
            proc_depth = 0
            single_stmt = True

        if in_proc and _DECL_RE.match(stripped):
            decl = stripped.rstrip(";") + ";"
            if decl not in hoisted:
                hoisted.append(decl)
            continue

        out.append(line)

        if in_proc:
            begin_count = len(_BEGIN_RE.findall(line))
            end_count = len(_END_RE.findall(line))
            proc_depth += begin_count - end_count

            if single_stmt:
                if begin_count > 0:
                    single_stmt = False
                else:
                    # Single-statement always/initial; end after this line.
                    if _PROC_START_RE.match(stripped) or proc_depth <= 0:
                        in_proc = False
                        single_stmt = False
            else:
                if proc_depth <= 0 and end_count > 0:
                    in_proc = False

    if hoisted and module_header_end_idx is not None:
        insert_at = module_header_end_idx + 1
        return out[:insert_at] + [""] + hoisted + [""] + out[insert_at:]
    return out


def _insert_check_delay(lines: list[str]) -> list[str]:
    out: list[str] = []
    in_posedge = False
    depth = 0
    inserted = False
    saw_delay = False

    for line in lines:
        stripped = line.strip()
        if _POS_EDGE_RE.match(stripped):
            in_posedge = True
            depth = 0
            inserted = False
            saw_delay = False

        if in_posedge:
            begin_count = len(_BEGIN_RE.findall(line))
            end_count = len(_END_RE.findall(line))
            depth += begin_count - end_count
            if "#" in line:
                saw_delay = True
            if not inserted and not saw_delay and _CHECK_RE.search(line):
                out.append("    #1;")
                inserted = True

        out.append(line)

        if in_posedge and depth <= 0 and _END_RE.search(line):
            in_posedge = False

    return out


def _align_split_ref_checker_delay(lines: list[str]) -> list[str]:
    """Repair a common debug-patch race without changing initial TB generation.

    Some LLM patches keep the reference model and checker in separate sample-edge
    blocks. If the reference block updates ref_* with nonblocking assignments
    after a #1 settle delay, a checker block with the same #1 delay samples stale
    ref_* values and reports a persistent one-cycle DUT-ahead mismatch. In the
    debug path, align the checker one timestep later so the reference NBA has
    committed before comparison.
    """

    regions = _line_regions(lines)
    ref_update_regions: dict[str, set[int]] = {}
    ref_nba_re = re.compile(r"\b(ref_[A-Za-z_][A-Za-z0-9_]*)\b\s*<=")
    ref_compare_re = re.compile(r"(?:!==|!=)\s*(ref_[A-Za-z_][A-Za-z0-9_]*)")

    for region in regions:
        sensitivity = region["sensitivity"]
        if "posedge" not in sensitivity:
            continue
        text = "\n".join(lines[region["start"] : region["end"]])
        refs = set(ref_nba_re.findall(text))
        if refs:
            for ref in refs:
                ref_update_regions.setdefault(ref, set()).add(region["start"])

    if not ref_update_regions:
        return lines

    out = list(lines)
    for region in regions:
        sensitivity = region["sensitivity"]
        if "posedge" not in sensitivity:
            continue
        text = "\n".join(lines[region["start"] : region["end"]])
        lowered = text.lower()
        if "$finish(1" not in lowered and "fail" not in lowered:
            continue
        compared_refs = set(ref_compare_re.findall(text))
        if not compared_refs:
            continue
        split_refs = {
            ref
            for ref in compared_refs
            if any(start != region["start"] for start in ref_update_regions.get(ref, set()))
        }
        if not split_refs:
            continue

        compare_line = None
        for idx in range(region["start"], region["end"]):
            if ref_compare_re.search(lines[idx]):
                compare_line = idx
                break
        if compare_line is None:
            continue

        delay_line = None
        for idx in range(region["start"], compare_line):
            if re.search(r"#\s*1\s*;", lines[idx]):
                delay_line = idx
        if delay_line is not None:
            out[delay_line] = re.sub(r"#\s*1\s*;", "#2;", out[delay_line], count=1)
        else:
            indent = re.match(r"^(\s*)", lines[compare_line]).group(1)
            out.insert(compare_line, f"{indent}#2;")
            return out

    return out


def _line_regions(lines: list[str]) -> list[dict]:
    regions: list[dict] = []
    idx = 0
    while idx < len(lines):
        stripped = lines[idx].strip()
        match = _PROC_START_RE.match(stripped)
        if not match:
            idx += 1
            continue
        start = idx
        sensitivity = ""
        sens_match = re.search(r"@\(([^)]*)\)", lines[idx])
        if sens_match:
            sensitivity = sens_match.group(1).lower()
        if "begin" not in stripped.lower() and stripped.endswith(";"):
            regions.append({"start": start, "end": start + 1, "sensitivity": sensitivity})
            idx += 1
            continue
        depth = len(_BEGIN_RE.findall(lines[start])) - len(_END_RE.findall(lines[start]))
        seen_begin = bool(len(_BEGIN_RE.findall(lines[start])))
        end = start + 1
        while end < len(lines):
            if seen_begin and depth <= 0:
                break
            begin_count = len(_BEGIN_RE.findall(lines[end]))
            end_count = len(_END_RE.findall(lines[end]))
            depth += begin_count - end_count
            if begin_count:
                seen_begin = True
            end += 1
        regions.append({"start": start, "end": end, "sensitivity": sensitivity})
        idx = end
    return regions


def _widen_dumpfile_regs(lines: list[str]) -> list[str]:
    out: list[str] = []
    target_msb = _DUMPFILE_TARGET_BITS - 1
    width_re = re.compile(r"^\s*reg\s*(\[[^]]+\])?\s*([A-Za-z_][A-Za-z0-9_]*)\b(.*)$")
    numeric_width_re = re.compile(r"\[(\d+)\s*:\s*(\d+)\]")

    for line in lines:
        match = width_re.match(line)
        if not match:
            out.append(line)
            continue
        width_decl, name, rest = match.group(1), match.group(2), match.group(3)
        if name not in _DUMPFILE_NAMES:
            out.append(line)
            continue
        replace_width = False
        if width_decl is None:
            replace_width = True
        else:
            width_match = numeric_width_re.search(width_decl)
            if width_match:
                msb = int(width_match.group(1))
                lsb = int(width_match.group(2))
                width = msb - lsb + 1
                if width < _DUMPFILE_TARGET_BITS:
                    replace_width = True
            else:
                replace_width = False
        if replace_width:
            indent = line[: line.find("reg")]
            out.append(f"{indent}reg [{target_msb}:0] {name}{rest}")
        else:
            out.append(line)
    return out
