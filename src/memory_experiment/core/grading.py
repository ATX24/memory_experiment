from __future__ import annotations

from typing import Any


def _norm(v: Any) -> Any:
    return v.strip().lower() if isinstance(v, str) else v


def default_grader(expected: dict[str, Any], answer: dict[str, Any] | None) -> tuple[float, str]:
    """All expected keys must match (case-insensitive for strings). Score 1 or 0;
    notes list the mismatching keys so partial failures are visible."""
    if answer is None:
        return 0.0, "no structured answer"
    bad = [f"{k}: expected {v!r}, got {answer.get(k)!r}" for k, v in expected.items() if _norm(answer.get(k)) != _norm(v)]
    return (1.0, "ok") if not bad else (0.0, "; ".join(bad))
