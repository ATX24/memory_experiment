"""Shared rendering so every backend presents facts/rows identically."""
from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from .types import Fact


def cell(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return str(v)
    return str(v)


def rows_to_markdown(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "(no rows)"
    cols = list(rows[0].keys())
    head = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join("---" for _ in cols) + " |"
    body = ["| " + " | ".join(cell(r.get(c)) for c in cols) + " |" for r in rows]
    return "\n".join([head, sep, *body])


def rows_to_json(rows: list[dict[str, Any]]) -> str:
    return json.dumps(rows, default=cell)


def facts_to_markdown(category: str, facts: list[Fact]) -> str:
    lines = [f"# {category.replace('_', ' ').title()}", ""]
    for f in facts:
        lines.append(f"- **{f.title}**: {f.content}" if f.title else f"- {f.content}")
    return "\n".join(lines) + "\n"


def row_to_markdown(table: str, row: dict[str, Any]) -> str:
    lines = [f"# {table} record", ""] + [f"- {k}: {cell(v)}" for k, v in row.items()]
    return "\n".join(lines) + "\n"
