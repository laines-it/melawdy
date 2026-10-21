from __future__ import annotations

import re
from typing import Any

_PLACEHOLDER = re.compile(r"\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}")
_WHEN = re.compile(r"^([a-zA-Z0-9_]+)\s*(==|!=)\s*(\w+)$")


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
    if "||" in expr:
        return any(_when_ok(part.strip(), params) for part in expr.split("||"))
    if "&&" in expr:
        return all(_when_ok(part.strip(), params) for part in expr.split("&&"))
    m = _WHEN.match(expr.strip())
    if not m:
        return False
    field, op, raw = m.groups()
    left = params.get(field)
    if raw in ("true", "false"):
        right = raw == "true"
        left_b = str(left).lower() in ("1", "true", "yes")
        return (left_b is right) if op == "==" else (left_b is not right)
    left_s = "" if left is None else str(left)
    return (left_s == raw) if op == "==" else (left_s != raw)


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