"""Memory model A: real markdown files for memory + a SQL tool for data."""
from __future__ import annotations

import os
from pathlib import Path

from ..eval.types import ToolSpec
from ._common import PATH_SCHEMA, sql_tool
from .base import MemoryModel, MemoryState
from .render import facts_to_markdown


class FsPrefsPlusSql(MemoryModel):
    name = "fs_prefs_plus_sql"
    description = "Memory is markdown files in a real directory (MEMORY.md index + one file per topic) read with list_dir/read_file; data is Postgres behind a read-only sql_query tool."
    memory_lives_in = "real markdown files on disk (/MEMORY.md, /memory/<topic>.md), current principal only"
    data_lives_in = "Postgres tables, reached with sql_query"

    def load(self, state: MemoryState) -> None:
        self.db = state.db
        self.root = (Path(state.workdir) / "memory").resolve()
        (self.root / "memory").mkdir(parents=True)
        by_cat: dict[str, list] = {}
        for f in state.facts:
            if f.user_id == state.user_id:  # access control happens here, in the backend
                by_cat.setdefault(f.category, []).append(f)
        index = ["# Memory index", "", "Topic files (one per topic):", ""]
        for cat, facts in sorted(by_cat.items()):
            (self.root / "memory" / f"{cat}.md").write_text(facts_to_markdown(cat, facts))
            index.append(f"- memory/{cat}.md ({len(facts)} notes)")
        (self.root / "MEMORY.md").write_text("\n".join(index) + "\n")
        self.schema_text = state.db.describe()

    def _resolve(self, rel: str) -> Path:
        p = (self.root / rel.lstrip("/")).resolve()
        if p != self.root and self.root not in p.parents:
            raise PermissionError("path escapes memory directory")
        return p

    def tools(self) -> list[ToolSpec]:
        def list_dir(a):
            p = self._resolve(a.get("path", "/"))
            if not p.is_dir():
                return f"ERROR: no such directory {a.get('path')}"
            return "\n".join((n + "/" if (p / n).is_dir() else n) for n in sorted(os.listdir(p))) or "(empty)"

        def read_file(a):
            p = self._resolve(a["path"])
            return p.read_text() if p.is_file() else f"ERROR: no such file {a['path']}"

        return [
            ToolSpec("list_dir", "List entries in a directory of the memory filesystem. Root is '/'.", PATH_SCHEMA, list_dir),
            ToolSpec("read_file", "Read a file from the memory filesystem.", PATH_SCHEMA, read_file),
            sql_tool(self.db.readonly_query),
        ]

    def layout_prompt(self) -> str:
        return (
            "Your memory about the principal is a small filesystem: `/MEMORY.md` is an index and `/memory/<topic>.md` files hold what you know (list_dir / read_file).\n\n"
            f"Operational data is a PostgreSQL database reachable with `sql_query`. Schema:\n\n```\n{self.schema_text}\n```"
        )
