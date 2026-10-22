from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any

from ..eval.types import Experience, Fact, Table, ToolSpec
from .db import CaseDB


@dataclass
class MemoryState:
    """What a memory model is asked to hold for one run: the principal's facts
    (memory state), the data tables already loaded in `db` (data state), and
    where it may materialise files."""

    user_id: str
    facts: list[Fact]
    tables: list[Table]
    db: CaseDB
    workdir: str
    fact_table_name: str = "memory"
    experiences: list[Experience] | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class MemoryModel(abc.ABC):
    """A memory model = how facts and data are stored and exposed to the agent as tools.

    To add one: subclass in memory_model/<name>.py, implement `load`, `tools`,
    `layout_prompt`, and add it to REGISTRY in memory_model/__init__.py. The driver
    builds the LangGraph agent from `tools()`; `layout_prompt()` is the only
    model-specific text the LLM sees.
    """

    name: str = "base"
    description: str = ""
    memory_lives_in: str = ""
    data_lives_in: str = ""

    def __init__(self, **options: Any):
        self.options = options

    @abc.abstractmethod
    def load(self, state: MemoryState) -> None: ...

    @abc.abstractmethod
    def tools(self) -> list[ToolSpec]: ...

    @abc.abstractmethod
    def layout_prompt(self) -> str: ...

    def unload(self) -> None:  # noqa: B027
        return None

    def spec(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "memory_lives_in": self.memory_lives_in, "data_lives_in": self.data_lives_in, "options": self.options}
