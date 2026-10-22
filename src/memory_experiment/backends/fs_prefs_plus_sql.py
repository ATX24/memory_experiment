"""Layout A: real markdown files on disk for memory (MEMORY.md index + one file
per category, like a Claude Code / "instinct" memory directory) plus a SQL tool
for operational data."""
from __future__ import annotations

import os
from pathlib import Path

from ..core.backend import MemoryBackend
from ..core.db import CaseDB
from ..core.render import facts_to_markdown
from ..core.types import EvalCase, Scenario, ToolSpec
from ._common import PATH_SCHEMA, sql_tool


class FsPrefsPlusSqlBackend(MemoryBackend):
    name = "fs_prefs_plus_sql"
    description = (
        "Preferences are markdown files in a real directory (MEMORY.md index + one file per topic), "
        "read with list_dir/read_file. Operational data is in Postgres behind a read-only sql_query tool."
    )

    def setup(self, scenario: Scenario, case: EvalCase, db: CaseDB, workdir: str) -> None:
        self.db = db
        self.root = (Path(workdir) / "memory").resolve()
        (self.root / "preferences").mkdir(parents=True)
        by_cat: dict[str, list] = {}
        for f in case.facts:
            if f.user_id == case.user_id:  # access control happens here, in the backend
                by_cat.setdefault(f.category, []).append(f)
        index = ["# Memory index", "", "Preference files (one per topic):", ""]
        for cat, facts in sorted(by_cat.items()):
            (self.root / "preferences" / f"{cat}.md").write_text(facts_to_markdown(cat, facts))
            index.append(f"- preferences/{cat}.md ({len(facts)} notes)")
        (self.root / "MEMORY.md").write_text("\n".join(index) + "\n")
        self.schema_text = db.describe()

    def _resolve(self, rel: str) -> Path:
        p = (self.root / rel.lstrip("/").removeprefix("memory/")).resolve()
        if p != self.root and self.root not in p.parents:
            raise PermissionError("path escapes memory directory")
        return p

    def tools(self) -> list[ToolSpec]:
        def list_dir(args):
            p = self._resolve(args.get("path", "/"))
            if not p.is_dir():
                return f"ERROR: no such directory {args.get('path')}"
            return "\n".join((n + "/" if (p / n).is_dir() else n) for n in sorted(os.listdir(p))) or "(empty)"

        def read_file(args):
            p = self._resolve(args["path"])
            return p.read_text() if p.is_file() else f"ERROR: no such file {args['path']}"

        return [
            ToolSpec("list_dir", "List entries in a directory of the memory filesystem. Root is '/'.", PATH_SCHEMA, list_dir),
            ToolSpec("read_file", "Read a file from the memory filesystem.", PATH_SCHEMA, read_file),
            sql_tool(self.db.readonly_query),
        ]

    def layout_prompt(self) -> str:
        return (
            "Your memory about the user is a small filesystem: `/MEMORY.md` is an index and "
            "`/preferences/<topic>.md` files hold the user's preferences (list_dir / read_file).\n\n"
            "Operational data is a PostgreSQL database reachable with `sql_query`. Schema:\n\n"
            f"```\n{self.schema_text}\n```"
        )
