from __future__ import annotations

from ..eval.types import ToolSpec
from .render import rows_to_json

PATH_SCHEMA = {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}


def sql_tool(run_query, limit: int = 200) -> ToolSpec:
    def handler(args):
        rows = run_query(args["query"], limit)
        return rows_to_json(rows) if rows else "[] (0 rows)"

    return ToolSpec(
        name="sql_query",
        description=f"Run a read-only SQL query (PostgreSQL) and return up to {limit} rows as JSON. Standard SQL; the schema is in your instructions.",
        input_schema={"type": "object", "properties": {"query": {"type": "string", "description": "A single SELECT statement."}}, "required": ["query"]},
        handler=handler,
    )


def create_fact_table(db, name: str, facts) -> None:
    db.conn.execute(f"CREATE TABLE {name} (id serial primary key, user_id text not null, category text not null, title text, content text not null)")
    db.conn.execute(f"COMMENT ON TABLE {name} IS 'Remembered facts and preferences about principals; filter by user_id.'")
    db.insert_rows(name, [{"user_id": f.user_id, "category": f.category, "title": f.title, "content": f.content} for f in facts])
