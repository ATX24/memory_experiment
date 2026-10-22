from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Table:
    """A domain table whose rows change per eval case (operational data)."""

    name: str
    columns_sql: str  # body of CREATE TABLE, e.g. "id text primary key, qty int"
    description: str = ""
    primary_key: str = "id"


@dataclass
class Fact:
    """A single remembered preference / fact about a user.

    Facts are the unit of *memory*. Every backend receives the same facts and
    decides how to present them (markdown file, table row, virtual file).
    """

    user_id: str
    category: str  # groups facts into one "document" (e.g. "travel", "scheduling")
    content: str
    title: str | None = None


@dataclass
class EvalCase:
    id: str
    prompt: str
    rows: dict[str, list[dict[str, Any]]]  # table name -> rows for this case
    facts: list[Fact]
    expected: dict[str, Any]
    user_id: str = "user"
    tags: list[str] = field(default_factory=list)
    notes: str = ""


Grader = Callable[[dict[str, Any], "dict[str, Any] | None"], tuple[float, str]]


@dataclass
class Scenario:
    """Everything the harness needs to run one task family. Lives OUTSIDE the
    repo (see --scenario); the harness assumes nothing beyond this structure."""

    name: str
    task_prompt: str  # domain instructions shared by all backends
    tables: list[Table]
    answer_schema: dict[str, Any]  # JSON schema for the agent's final structured answer
    cases: list[EvalCase]
    grader: Grader | None = None
    fact_table_name: str = "preferences"  # table name when facts are stored relationally


@dataclass
class ToolSpec:
    """A tool a backend exposes to the agent. `handler` is sync and returns text."""

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], str]


@dataclass
class ToolCallRecord:
    name: str
    args: dict[str, Any]
    duration_ms: float
    result_chars: int
    error: bool = False


@dataclass
class AgentResult:
    answer: dict[str, Any] | None
    final_text: str
    model_calls: int
    wall_ms: float
    model_ms: float
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    tool_calls: list[ToolCallRecord]
    error: str | None = None


@dataclass
class RunRecord:
    scenario: str
    backend: str
    case_id: str
    trial: int
    score: float
    grade_notes: str
    expected: dict[str, Any]
    answer: dict[str, Any] | None
    model_calls: int
    wall_ms: float
    model_ms: float
    tool_ms: float
    tool_call_count: int
    tool_result_chars: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    tool_calls: list[dict[str, Any]]
    final_text: str
    error: str | None
    model: str
    tags: list[str]
