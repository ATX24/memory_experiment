"""Memory model B: memory and data are plain Postgres tables behind one sql_query tool."""
from __future__ import annotations

from ..eval.types import ToolSpec
from ._common import create_fact_table, sql_tool
from .base import MemoryModel, MemoryState


class SqlOnly(MemoryModel):
    name = "sql_only"
    description = "Memory is a memory(user_id, category, title, content) table beside the data tables; one read-only sql_query tool. Access control is left to the agent's WHERE clause."
    memory_lives_in = "Postgres table `memory` holding every principal's facts"
    data_lives_in = "Postgres tables, same sql_query tool"

    def load(self, state: MemoryState) -> None:
        self.db = state.db
        self.fact_table = state.fact_table_name
        create_fact_table(state.db, self.fact_table, state.facts)
        self.schema_text = state.db.describe()

    def tools(self) -> list[ToolSpec]:
        return [sql_tool(self.db.readonly_query)]

    def layout_prompt(self) -> str:
        return (
            f"Everything is in one PostgreSQL database: what you know about principals (table `{self.fact_table}`, filter by user_id) and the operational data. Query with `sql_query`. Schema:\n\n```\n{self.schema_text}\n```"
        )
