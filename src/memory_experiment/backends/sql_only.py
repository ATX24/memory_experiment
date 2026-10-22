"""Layout B: preferences and operational data are plain Postgres tables; the
agent reaches everything through one read-only sql_query tool."""
from __future__ import annotations

from ..core.backend import MemoryBackend
from ..core.db import CaseDB
from ..core.types import EvalCase, Scenario, ToolSpec
from ._common import create_fact_table, sql_tool


class SqlOnlyBackend(MemoryBackend):
    name = "sql_only"
    description = (
        "Preferences are rows in a preferences(user_id, category, title, content) table beside the "
        "operational tables. One tool: read-only sql_query. Access control is left to the agent's WHERE clause."
    )

    def setup(self, scenario: Scenario, case: EvalCase, db: CaseDB, workdir: str) -> None:
        self.db = db
        self.fact_table = scenario.fact_table_name
        create_fact_table(db, self.fact_table, case.facts)
        self.schema_text = db.describe()

    def tools(self) -> list[ToolSpec]:
        return [sql_tool(self.db.readonly_query)]

    def layout_prompt(self) -> str:
        return (
            f"Everything is in one PostgreSQL database: the user's preferences (table `{self.fact_table}`, "
            "filter by user_id) and the operational data. Query with `sql_query`. Schema:\n\n"
            f"```\n{self.schema_text}\n```"
        )
