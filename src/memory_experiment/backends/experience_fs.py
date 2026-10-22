"""Layout D: a database of data rows AND "experiences". An experience is a group
of records (observations about the user + related data rows) that mirrors one
markdown file. The agent traverses experiences with a filesystem interface:

    /EXPERIENCES.md            index: one line per experience with its summary
    /<experience>.md           rendered document: observations, then grouped data rows
    /<experience>/             the experience's members as individual files
    /<experience>/<table>/<pk>.md
    search(query)              substring search across experiences -> paths

Storage: Postgres `experiences(id, path, title, summary)` + `experience_items(experience_id,
kind, category, text, ref_table, ref_id)` beside the operational tables; observations are
items of kind 'observation', data membership is an item of kind 'row' pointing at a table row.
Experience membership comes from Scenario.experiences; when absent, one experience is
derived per fact category (observations only) and one per table (rows only).
"""
from __future__ import annotations

from typing import Any

from psycopg import sql

from ..core.backend import MemoryBackend
from ..core.db import CaseDB
from ..core.render import cell, row_to_markdown, rows_to_markdown
from ..core.types import EvalCase, Experience, Scenario, ToolSpec
from ._common import PATH_SCHEMA


class ExperienceFsBackend(MemoryBackend):
    name = "experience_fs"
    description = (
        "Postgres stores data rows plus 'experiences': groups of observations and related rows that each mirror "
        "one markdown document. The agent traverses experiences via list_dir/read_file/search."
    )

    def setup(self, scenario: Scenario, case: EvalCase, db: CaseDB, workdir: str) -> None:
        self.db = db
        self.user_id = case.user_id
        self.tables = {t.name: t for t in scenario.tables}
        db.conn.execute("CREATE TABLE experiences (id serial primary key, path text unique not null, title text not null, summary text not null default '')")
        db.conn.execute(
            "CREATE TABLE experience_items (id serial primary key, experience_id int references experiences(id), kind text not null, "
            "category text, text text, ref_table text, ref_id text, position int not null)"
        )
        mine = [f for f in case.facts if f.user_id == case.user_id]
        specs = scenario.experiences or self._default_specs(mine, list(self.tables))
        for spec in specs:
            eid = db.query("INSERT INTO experiences (path, title, summary) VALUES (%s, %s, %s) RETURNING id", (spec.path, spec.title, spec.summary))[0]["id"]
            items: list[dict[str, Any]] = []
            pos = 0
            for f in mine:
                if f.category in spec.categories:
                    items.append({"experience_id": eid, "kind": "observation", "category": f.category, "text": (f"{f.title}: " if f.title else "") + f.content, "ref_table": None, "ref_id": None, "position": pos})
                    pos += 1
            for table in spec.tables:
                pk = self.tables[table].primary_key
                for r in db.query(sql.SQL("SELECT * FROM {} ORDER BY {}").format(sql.Identifier(table), sql.Identifier(pk))):
                    if spec.row_filter is None or spec.row_filter(table, r):
                        items.append({"experience_id": eid, "kind": "row", "category": None, "text": None, "ref_table": table, "ref_id": str(r[pk]), "position": pos})
                        pos += 1
            db.insert_rows("experience_items", items)

    @staticmethod
    def _default_specs(facts, tables: list[str]) -> list[Experience]:
        cats = sorted({f.category for f in facts})
        return [Experience(path=c, title=c.replace("_", " ").title(), categories=[c]) for c in cats] + [
            Experience(path=t, title=t.replace("_", " ").title(), tables=[t]) for t in sorted(tables)
        ]

    # ---- queries ---------------------------------------------------------------
    def _experiences(self) -> list[dict[str, Any]]:
        return self.db.query("SELECT * FROM experiences ORDER BY path")

    def _experience(self, path: str) -> dict[str, Any] | None:
        rows = self.db.query("SELECT * FROM experiences WHERE path = %s", (path,))
        return rows[0] if rows else None

    def _items(self, eid: int) -> list[dict[str, Any]]:
        return self.db.query("SELECT * FROM experience_items WHERE experience_id = %s ORDER BY position", (eid,))

    def _row(self, table: str, pk_val: str) -> dict[str, Any] | None:
        pk = self.tables[table].primary_key
        rows = self.db.query(sql.SQL("SELECT * FROM {} WHERE {}::text = %s").format(sql.Identifier(table), sql.Identifier(pk)), (pk_val,))
        return rows[0] if rows else None

    def _render(self, exp: dict[str, Any]) -> str:
        items = self._items(exp["id"])
        lines = [f"# {exp['title']}", ""]
        if exp["summary"]:
            lines += [exp["summary"], ""]
        obs = [i for i in items if i["kind"] == "observation"]
        if obs:
            lines += ["## Observations", ""] + [f"- {i['text']}" for i in obs] + [""]
        by_table: dict[str, list[dict[str, Any]]] = {}
        for i in items:
            if i["kind"] == "row":
                r = self._row(i["ref_table"], i["ref_id"])
                if r is not None:
                    by_table.setdefault(i["ref_table"], []).append(r)
        for table, rows in by_table.items():
            t = self.tables[table]
            lines += [f"## {table}", "", t.description, "", rows_to_markdown(rows), ""]
        return "\n".join(lines)

    # ---- fs ops ------------------------------------------------------------------
    def list_dir(self, path: str) -> str:
        parts = [p for p in path.strip("/").split("/") if p]
        if not parts:
            return "\n".join(["EXPERIENCES.md", *[f"{e['path']}.md" for e in self._experiences()], *[f"{e['path']}/" for e in self._experiences()]])
        exp = self._experience(parts[0])
        if exp is None:
            return f"ERROR: no such directory {path}"
        items = self._items(exp["id"])
        if len(parts) == 1:
            tables = sorted({i["ref_table"] for i in items if i["kind"] == "row"})
            return "\n".join(["observations.md", *[f"{t}/" for t in tables]]) or "(empty)"
        if len(parts) == 2:
            ids = [i["ref_id"] for i in items if i["kind"] == "row" and i["ref_table"] == parts[1]]
            return "\n".join(f"{i}.md" for i in ids) if ids else f"ERROR: no such directory {path}"
        return f"ERROR: no such directory {path}"

    def read_file(self, path: str) -> str:
        parts = [p for p in path.strip("/").split("/") if p]
        if parts == ["EXPERIENCES.md"]:
            return "# Experiences\n\n" + "\n".join(f"- /{e['path']}.md — {e['title']}" + (f": {e['summary']}" if e["summary"] else "") for e in self._experiences()) + "\n"
        if len(parts) == 1 and parts[0].endswith(".md"):
            exp = self._experience(parts[0][:-3])
            return self._render(exp) if exp else f"ERROR: no such file {path}"
        exp = self._experience(parts[0]) if parts else None
        if exp is None:
            return f"ERROR: no such file {path}"
        if len(parts) == 2 and parts[1] == "observations.md":
            obs = [i for i in self._items(exp["id"]) if i["kind"] == "observation"]
            return f"# {exp['title']}: observations\n\n" + "\n".join(f"- {i['text']}" for i in obs) + "\n"
        if len(parts) == 3 and parts[2].endswith(".md") and parts[1] in self.tables:
            member = any(i["kind"] == "row" and i["ref_table"] == parts[1] and i["ref_id"] == parts[2][:-3] for i in self._items(exp["id"]))
            row = self._row(parts[1], parts[2][:-3]) if member else None
            return row_to_markdown(parts[1], row) if row else f"ERROR: no such file {path}"
        return f"ERROR: no such file {path}"

    def search(self, needle: str) -> str:
        n = needle.lower()
        hits: list[str] = []
        for e in self._experiences():
            for i in self._items(e["id"]):
                if i["kind"] == "observation" and n in i["text"].lower():
                    hits.append(f"/{e['path']}.md: {i['text']}")
                elif i["kind"] == "row":
                    r = self._row(i["ref_table"], i["ref_id"])
                    text = " ".join(cell(v) for v in (r or {}).values())
                    if n in text.lower():
                        hits.append(f"/{e['path']}/{i['ref_table']}/{i['ref_id']}.md: {text}")
        return "\n".join(hits[:50]) if hits else "(no matches)"

    def tools(self) -> list[ToolSpec]:
        return [
            ToolSpec("list_dir", "List entries in a directory of the experience filesystem. Root is '/'.", PATH_SCHEMA, lambda a: self.list_dir(a.get("path", "/"))),
            ToolSpec("read_file", "Read a file from the experience filesystem.", PATH_SCHEMA, lambda a: self.read_file(a["path"])),
            ToolSpec("search", "Case-insensitive substring search across all experiences; returns matching paths with a snippet.",
                     {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}, lambda a: self.search(a["query"])),
        ]

    def layout_prompt(self) -> str:
        return (
            "Your memory and data are organised as *experiences*: each experience is one document that groups "
            "observations about the user with the data rows related to them. Browse them as a filesystem:\n"
            "- /EXPERIENCES.md : index of experiences with a one-line summary each\n"
            "- /<experience>.md : the full experience (observations, then related data tables)\n"
            "- /<experience>/observations.md and /<experience>/<table>/<id>.md : individual members\n"
            "Tools: list_dir, read_file, search."
        )
