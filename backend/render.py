from __future__ import annotations

import re
from typing import Any

_PLACEHOLDER = re.compile(r"\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}")
_WHEN_PART = re.compile(
    r"^([a-zA-Z0-9_]+)\s*(==|!=|>=|<=|>|<)\s*([\w]+)$"
)


def _lookup(params: dict[str, Any], path: str) -> str:
    cur: Any = params
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return "__________"
        cur = cur[part]
    if cur is None or cur == "":
        return "__________"
    return str(cur)


def _when_ok(expr: str | None, params: dict[str, Any]) -> bool:
    if not expr:
        return True

    for part in expr.split("&&"):
        m = _WHEN_PART.match(part.strip())
        if not m:
            return False

        field, op, raw = m.groups()
        left = params.get(field)

        if op in ("==", "!="):
            if raw in ("true", "false"):
                right = raw == "true"
                left_b = str(left).lower() in ("1", "true", "yes")
                equal = left_b is right
            else:
                left_s = "" if left is None else str(left)
                equal = left_s == raw

            if op == "==" and not equal:
                return False
            if op == "!=" and equal:
                return False
            continue

        try:
            left_n = float(left)
            right_n = float(raw)
        except (TypeError, ValueError):
            return False

        if op == ">=" and not left_n >= right_n:
            return False
        if op == "<=" and not left_n <= right_n:
            return False
        if op == ">" and not left_n > right_n:
            return False
        if op == "<" and not left_n < right_n:
            return False

    return True


def render_structure(structure: dict[str, Any] | None, params: dict[str, Any]) -> str:
    blocks = (structure or {}).get("blocks") or []
    parts: list[str] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        if not _when_ok(block.get("when"), params):
            continue
        tpl = block.get("template") or ""
        parts.append(_PLACEHOLDER.sub(lambda m: _lookup(params, m.group(1)), tpl))
    return "\n\n".join(parts)


def render_flat_body(body: str, params: dict[str, Any]) -> str:
    return _PLACEHOLDER.sub(lambda m: _lookup(params, m.group(1)), body or "")