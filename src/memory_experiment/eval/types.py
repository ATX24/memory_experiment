from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Table:
    """A data table (operational state). Rows are supplied by the workload / case."""

    name: str
    columns_sql: str
    description: str = ""
    primary_key: str = "id"


@dataclass
class Fact:
    """One remembered item about a principal (memory state). `category` groups facts
    into a topic; `title` is an optional label (e.g. the profile setting name)."""

    user_id: str
    category: str
    content: str
    title: str | None = None


@dataclass
class Experience:
    """Grouping for experience-style memory models: observations from `categories`
    plus rows from `tables` rendered as one document."""

    path: str
    title: str
    categories: list[str] = field(default_factory=list)
    tables: list[str] = field(default_factory=list)
    row_filter: Callable[[str, dict[str, Any]], bool] | None = None
    summary: str = ""


@dataclass
class Case:
    """One unit of work. `expected` is a dict for exact-match grading or free text for
    the rubric judge; `must_not` is the behaviour that fails the case outright."""

    id: str
    prompt: str
    user_id: str
    expected: Any
    must_not: str | None = None
    facts: list[Fact] | None = None  # override the workload's memory state
    rows: dict[str, list[dict[str, Any]]] | None = None  # override/add data rows
    meta: dict[str, Any] = field(default_factory=dict)  # rubric_row, swap_group, blocking, client, ...
    notes: str = ""


@dataclass
class GradeResult:
    score: float
    passed: bool
    reason: str


@dataclass
class Workload:
    """Everything the harness needs: task instructions, preset memory state (facts),
    preset data state (tables + rows), the cases, the answer schema, the grader."""

    name: str
    task_prompt: str
    tables: list[Table]
    answer_schema: dict[str, Any]
    cases: list[Case]
    grader: "Grader"
    facts: list[Fact] = field(default_factory=list)
    rows: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    fact_table_name: str = "memory"
    experiences: list[Experience] | None = None
    description: str = ""

    def facts_for(self, case: Case) -> list[Fact]:
        return case.facts if case.facts is not None else self.facts

    def rows_for(self, case: Case) -> dict[str, list[dict[str, Any]]]:
        merged = {t.name: list(self.rows.get(t.name, [])) for t in self.tables}
        for t, rs in (case.rows or {}).items():
            merged.setdefault(t, []).extend(rs)
        return merged


class Grader:
    """Grades one answer. Subclasses implement `grade`."""

    name: str = "grader"

    async def grade(self, workload: Workload, case: Case, answer: dict[str, Any] | None, final_text: str) -> GradeResult:
        raise NotImplementedError

    def describe(self) -> str:
        return self.name


@dataclass
class ToolSpec:
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
    workload: str
    memory_model: str
    case_id: str
    user_id: str
    trial: int
    score: float
    passed: bool
    grade_reason: str
    expected: Any
    must_not: str | None
    answer: dict[str, Any] | None
    meta: dict[str, Any]
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
