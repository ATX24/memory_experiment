"""Memory model C: everything is in Postgres, but the agent only sees a virtual
filesystem. Paths are addresses; contents are rendered at read time from the
rows the current user may access. Nothing is materialised on disk.

    /memory/MEMORY.md                 index of preference topics
    /memory/topics/<topic>.md    rendered from the memory table (principal-scoped)
    /data/<table>/_schema.md          columns + description
    /data/<table>/all.md              every row as a markdown table
    /data/<table>/<pk>.md             one row
    search(query)                     substring search over facts + rows -> paths
"""
from __future__ import annotations

from typing import Any

from psycopg import sql

from .base import MemoryModel, MemoryState
from .render import facts_to_markdown, row_to_markdown, rows_to_markdown
from ..eval.types import Fact, ToolSpec
from ._common import PATH_SCHEMA, create_fact_table


class VirtualFs(MemoryModel):
    name = "virtual_fs"
    memory_lives_in = "Postgres table `memory`, rendered on read as /memory/<topic>.md (current principal only)"
    data_lives_in = "Postgres tables, rendered on read as /data/<table>/all.md and /data/<table>/<id>.md"
    description = (
        "Postgres holds memory and operational data; the agent only gets list_dir/read_file/search over a "
        "virtual filesystem whose contents are generated from user-scoped queries at read time."
    )

    def load(self, state: MemoryState) -> None:
        db, workdir = state.db, state.workdir
        self.db = db
        self.user_id = state.user_id
        self.tables = {t.name: t for t in state.tables}
        self.fact_table = state.fact_table_name
        create_fact_table(db, self.fact_table, state.facts)

    # ---- data access (always scoped to the current user) ---------------------
    def _facts(self, category: str | None = None) -> list[Fact]:
        q = f"SELECT * FROM {self.fact_table} WHERE user_id = %s" + (" AND category = %s" if category else "") + " ORDER BY id"
        params = (self.user_id, category) if category else (self.user_id,)
        return [Fact(r["user_id"], r["category"], r["content"], r["title"]) for r in self.db.query(q, params)]

    def _categories(self) -> list[str]:
        return sorted({f.category for f in self._facts()})

    def _rows(self, table: str) -> list[dict[str, Any]]:
        pk = self.tables[table].primary_key
        return self.db.query(sql.SQL("SELECT * FROM {} ORDER BY {}").format(sql.Identifier(table), sql.Identifier(pk)))

    def _row(self, table: str, pk_val: str) -> dict[str, Any] | None:
        pk = self.tables[table].primary_key
        rows = self.db.query(
            sql.SQL("SELECT * FROM {} WHERE {}::text = %s").format(sql.Identifier(table), sql.Identifier(pk)), (pk_val,)
        )
        return rows[0] if rows else None

    def _schema_md(self, table: str) -> str:
        t = self.tables[table]
        cols = self.db.query(
            "SELECT column_name, data_type FROM information_schema.columns WHERE table_schema=%s AND table_name=%s ORDER BY ordinal_position",
            (self.db.schema, table),
        )
        lines = [f"# {table}", "", t.description, "", "Columns:"] + [f"- {c['column_name']} ({c['data_type']})" for c in cols]
        lines += ["", f"Files: `all.md` (every row), `<{t.primary_key}>.md` (one row)."]
        return "\n".join(lines) + "\n"

    # ---- virtual fs ops --------------------------------------------------------
    def list_dir(self, path: str) -> str:
        parts = [p for p in path.strip("/").split("/") if p]
        if not parts:
            return "memory/\ndata/"
        if parts == ["memory"]:
            return "MEMORY.md\ntopics/"
        if parts == ["memory", "topics"]:
            return "\n".join(f"{c}.md" for c in self._categories()) or "(empty)"
        if parts == ["data"]:
            return "\n".join(f"{t}/" for t in sorted(self.tables))
        if len(parts) == 2 and parts[0] == "data" and parts[1] in self.tables:
            pk = self.tables[parts[1]].primary_key
            pks = self.db.query(sql.SQL("SELECT {}::text AS pk FROM {} ORDER BY 1").format(sql.Identifier(pk), sql.Identifier(parts[1])))
            return "\n".join(["_schema.md", "all.md", *[f"{r['pk']}.md" for r in pks]])
        return f"ERROR: no such directory {path}"

    def read_file(self, path: str) -> str:
        parts = [p for p in path.strip("/").split("/") if p]
        if parts == ["memory", "MEMORY.md"]:
            return "# Memory index\n\n" + "\n".join(f"- /memory/topics/{c}.md" for c in self._categories()) + "\n"
        if len(parts) == 3 and parts[:2] == ["memory", "topics"] and parts[2].endswith(".md"):
            cat = parts[2][:-3]
            facts = self._facts(cat)
            return facts_to_markdown(cat, facts) if facts else f"ERROR: no such file {path}"
        if len(parts) == 3 and parts[0] == "data" and parts[1] in self.tables and parts[2].endswith(".md"):
            table, leaf = parts[1], parts[2][:-3]
            if leaf == "_schema":
                return self._schema_md(table)
            if leaf == "all":
                return f"# {table} (all rows)\n\n" + rows_to_markdown(self._rows(table)) + "\n"
            row = self._row(table, leaf)
            return row_to_markdown(table, row) if row else f"ERROR: no such file {path}"
        return f"ERROR: no such file {path}"

    def search(self, needle: str) -> str:
        n = needle.lower()
        hits = [f"/memory/topics/{f.category}.md: {f.content}" for f in self._facts() if n in (f.content + " " + (f.title or "")).lower()]
        for table, t in self.tables.items():
            for r in self._rows(table):
                text = " ".join(str(v) for v in r.values())
                if n in text.lower():
                    hits.append(f"/data/{table}/{r[t.primary_key]}.md: {text}")
        return "\n".join(hits[:50]) if hits else "(no matches)"

    def tools(self) -> list[ToolSpec]:
        return [
            ToolSpec("list_dir", "List entries in a directory of the memory/data filesystem. Root is '/'.", PATH_SCHEMA, lambda a: self.list_dir(a.get("path", "/"))),
            ToolSpec("read_file", "Read a file from the memory/data filesystem.", PATH_SCHEMA, lambda a: self.read_file(a["path"])),
            ToolSpec(
                "search",
                "Case-insensitive substring search across all memory and data; returns matching paths with a snippet.",
                {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
                lambda a: self.search(a["query"]),
            ),
        ]

    def layout_prompt(self) -> str:
        tables = "\n".join(f"- /data/{n}/ : {t.description}" for n, t in sorted(self.tables.items()))
        return (
            "All memory and data is a virtual filesystem (contents are generated from the database when read):\n"
            "- /memory/MEMORY.md : index of memory topics\n"
            "- /memory/topics/<topic>.md : what you know about the principal on a topic\n"
            "- /data/<table>/_schema.md : columns; /data/<table>/all.md : every row; /data/<table>/<id>.md : one row\n"
            f"{tables}\n"
            "Tools: list_dir, read_file, search."
        )
